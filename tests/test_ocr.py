"""Tests for pluggable OCR engine abstraction."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from adam.extract.ocr import (
    BaseOcrEngine,
    NullOcrEngine,
    OcrResult,
    PaddleOcrEngine,
    TesseractOcrEngine,
    get_ocr_engine,
)


SAMPLE_TSV_OUTPUT = """level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext
1\t1\t0\t0\t0\t0\t0\t0\t1000\t1500\t-1\t
2\t1\t1\t0\t0\t0\t50\t60\t400\t100\t-1\t
3\t1\t1\t1\t0\t0\t50\t60\t400\t100\t-1\t
4\t1\t1\t1\t1\t0\t50\t60\t400\t40\t-1\t
5\t1\t1\t1\t1\t1\t50\t60\t180\t40\t90.0\tGOVERNMENT
5\t1\t1\t1\t1\t2\t240\t60\t50\t40\t95.0\tOF
5\t1\t1\t1\t1\t3\t300\t60\t150\t40\t92.0\tUTTARAKHAND
4\t1\t1\t1\t2\t0\t50\t110\t350\t40\t-1\t
5\t1\t1\t1\t2\t1\t50\t110\t200\t40\t88.0\tशासनादेश
5\t1\t1\t1\t2\t2\t260\t110\t100\t40\t85.0\tसंख्या
2\t1\t2\t0\t0\t0\t50\t250\t500\t50\t-1\t
3\t1\t2\t1\t0\t0\t50\t250\t500\t50\t-1\t
4\t1\t2\t1\t1\t0\t50\t250\t500\t50\t-1\t
5\t1\t2\t1\t1\t1\t50\t250\t120\t50\t94.0\tDehradun
5\t1\t2\t1\t1\t2\t180\t250\t100\t50\t96.0\tDated
"""


def test_ocr_result_dataclass():
    """Verify OcrResult initialization, fields, and confidence clamping."""
    res = OcrResult(
        text="Sample Text",
        confidence=0.85,
        blocks=[
            {
                "block_type": "text",
                "text": "Sample Text",
                "bbox": [10.0, 20.0, 100.0, 50.0],
                "reading_order": 0,
                "confidence": 0.85,
            }
        ],
    )
    assert res.text == "Sample Text"
    assert res.confidence == 0.85
    assert len(res.blocks) == 1
    assert res.blocks[0]["block_type"] == "text"
    assert res.blocks[0]["bbox"] == [10.0, 20.0, 100.0, 50.0]
    assert res.blocks[0]["reading_order"] == 0

    # Test confidence clamping
    res_high = OcrResult(text="", confidence=1.5)
    assert res_high.confidence == 1.0

    res_low = OcrResult(text="", confidence=-0.5)
    assert res_low.confidence == 0.0


def test_base_ocr_engine_is_abstract():
    """Ensure BaseOcrEngine cannot be instantiated directly."""
    with pytest.raises(TypeError):
        BaseOcrEngine()  # type: ignore


def test_null_ocr_engine():
    """Verify NullOcrEngine availability and null output."""
    engine = NullOcrEngine()
    assert engine.is_available() is True

    result = engine.ocr_page_image(b"dummy image bytes")
    assert isinstance(result, OcrResult)
    assert result.text == ""
    assert result.confidence == 0.0
    assert result.blocks == []


def test_tesseract_engine_availability():
    """Verify TesseractOcrEngine availability check via shutil.which."""
    engine = TesseractOcrEngine()
    with patch("shutil.which", return_value="/usr/bin/tesseract"):
        assert engine.is_available() is True

    with patch("shutil.which", return_value=None):
        assert engine.is_available() is False


def test_tesseract_tsv_parsing():
    """Verify TSV parsing into blocks, lines, bboxes, and confidence."""
    engine = TesseractOcrEngine()
    result = engine._parse_tsv(SAMPLE_TSV_OUTPUT)

    assert isinstance(result, OcrResult)
    assert len(result.blocks) == 2

    # Block 1
    b1 = result.blocks[0]
    assert b1["block_type"] == "text"
    assert "GOVERNMENT OF UTTARAKHAND" in b1["text"]
    assert "शासनादेश संख्या" in b1["text"]
    assert b1["bbox"] == [50.0, 60.0, 450.0, 160.0]
    assert b1["reading_order"] == 0
    # Average of 0.90, 0.95, 0.92, 0.88, 0.85 = 0.90
    assert round(b1["confidence"], 2) == 0.90

    # Block 2
    b2 = result.blocks[1]
    assert b2["block_type"] == "text"
    assert b2["text"] == "Dehradun Dated"
    assert b2["bbox"] == [50.0, 250.0, 550.0, 300.0]
    assert b2["reading_order"] == 1
    # Average of 0.94, 0.96 = 0.95
    assert round(b2["confidence"], 2) == 0.95

    # Overall full text and confidence
    assert "GOVERNMENT OF UTTARAKHAND" in result.text
    assert "Dehradun Dated" in result.text
    # Total words: 7. sum = 0.90 + 0.95 + 0.92 + 0.88 + 0.85 + 0.94 + 0.96 = 6.40
    # 6.40 / 7 = 0.9143
    assert 0.91 <= result.confidence <= 0.92


def test_tesseract_tsv_parsing_empty():
    """Verify TSV parsing on empty text or header only."""
    engine = TesseractOcrEngine()
    empty_res = engine._parse_tsv("")
    assert empty_res.text == ""
    assert empty_res.confidence == 0.0
    assert empty_res.blocks == []

    header_only = engine._parse_tsv("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n")
    assert header_only.text == ""
    assert header_only.confidence == 0.0
    assert header_only.blocks == []


def test_tesseract_ocr_page_image_execution():
    """Test full ocr_page_image invocation with mocked subprocess."""
    engine = TesseractOcrEngine()

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = SAMPLE_TSV_OUTPUT
    mock_proc.stderr = ""

    with patch.object(engine, "is_available", return_value=True):
        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            result = engine.ocr_page_image(b"\x89PNGfakeimagebytes", languages=["hin", "eng"])

            assert mock_run.called
            args, kwargs = mock_run.call_args
            cmd = args[0]
            assert cmd[0] == "tesseract"
            assert "-l" in cmd
            lang_idx = cmd.index("-l") + 1
            assert "hin" in cmd[lang_idx]
            assert "--oem" in cmd
            assert "--psm" in cmd
            assert cmd[-1] == "tsv"

            assert "GOVERNMENT OF UTTARAKHAND" in result.text
            assert len(result.blocks) == 2


def test_tesseract_subprocess_errors_handled():
    """Test graceful handling of subprocess errors and timeouts."""
    engine = TesseractOcrEngine()

    with patch.object(engine, "is_available", return_value=True):
        # 1. Non-zero exit code
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "Error opening data file"
        with patch("subprocess.run", return_value=mock_proc):
            res = engine.ocr_page_image(b"fakebytes")
            assert res.text == ""
            assert res.confidence == 0.0
            assert res.blocks == []

        # 2. TimeoutExpired
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="tesseract", timeout=10)):
            res = engine.ocr_page_image(b"fakebytes")
            assert res.text == ""
            assert res.confidence == 0.0
            assert res.blocks == []

        # 3. FileNotFoundError
        with patch("subprocess.run", side_effect=FileNotFoundError("tesseract not found")):
            res = engine.ocr_page_image(b"fakebytes")
            assert res.text == ""
            assert res.confidence == 0.0

    # 4. Empty image bytes
    res = engine.ocr_page_image(b"")
    assert res.text == ""
    assert res.confidence == 0.0


def test_paddle_ocr_engine_availability():
    """Test PaddleOcrEngine is_available check."""
    engine = PaddleOcrEngine()

    with patch("builtins.__import__", side_effect=ImportError("No module named paddleocr")):
        assert engine.is_available() is False

    with patch.object(PaddleOcrEngine, "is_available", return_value=True):
        assert engine.is_available() is True


def test_paddle_ocr_polygon_parsing():
    """Verify PaddleOCR output parsing with standard 4-point polygon format."""
    engine = PaddleOcrEngine()

    raw_paddle_output = [
        [
            [
                [[10.0, 20.0], [150.0, 20.0], [150.0, 60.0], [10.0, 60.0]],
                ("उत्तराखंड शासन", 0.98),
            ],
            [
                [[10.0, 70.0], [200.0, 70.0], [200.0, 100.0], [10.0, 100.0]],
                ("Finance Department", 0.94),
            ],
        ]
    ]

    result = engine._parse_paddle_output(raw_paddle_output)
    assert len(result.blocks) == 2

    assert result.blocks[0]["text"] == "उत्तराखंड शासन"
    assert result.blocks[0]["bbox"] == [10.0, 20.0, 150.0, 60.0]
    assert result.blocks[0]["reading_order"] == 0
    assert result.blocks[0]["confidence"] == 0.98

    assert result.blocks[1]["text"] == "Finance Department"
    assert result.blocks[1]["bbox"] == [10.0, 70.0, 200.0, 100.0]
    assert result.blocks[1]["reading_order"] == 1
    assert result.blocks[1]["confidence"] == 0.94

    assert "उत्तराखंड शासन\nFinance Department" == result.text
    assert result.confidence == 0.96


def test_paddle_ocr_dict_parsing():
    """Verify PaddleOCR parsing with JSON/dictionary format."""
    engine = PaddleOcrEngine()

    raw_dict_output = [
        {"transcription": "शासनादेश", "confidence": 0.95, "bbox": [50.0, 50.0, 250.0, 90.0]},
        {"text": "Order No 123", "score": 0.89, "points": [[50.0, 100.0], [200.0, 100.0], [200.0, 140.0], [50.0, 140.0]]},
    ]

    result = engine._parse_paddle_output(raw_dict_output)
    assert len(result.blocks) == 2
    assert result.blocks[0]["text"] == "शासनादेश"
    assert result.blocks[0]["bbox"] == [50.0, 50.0, 250.0, 90.0]
    assert result.blocks[1]["text"] == "Order No 123"
    assert result.blocks[1]["bbox"] == [50.0, 100.0, 200.0, 140.0]


def test_paddle_ocr_page_image_execution():
    """Verify PaddleOcrEngine execution when engine is available and mock returns result."""
    engine = PaddleOcrEngine()

    mock_paddle_instance = MagicMock()
    mock_paddle_instance.ocr.return_value = [
        [
            [
                [[0.0, 0.0], [50.0, 0.0], [50.0, 20.0], [0.0, 20.0]],
                ("Test Text", 0.90),
            ]
        ]
    ]

    with patch.object(engine, "is_available", return_value=True):
        with patch.object(engine, "_get_paddle_instance", return_value=mock_paddle_instance):
            result = engine.ocr_page_image(b"dummybytes", languages=["hin"])
            assert result.text == "Test Text"
            assert result.confidence == 0.90
            assert len(result.blocks) == 1


def test_paddle_ocr_graceful_failures():
    """Verify PaddleOcrEngine gracefully handles uninstalled library and runtime exceptions."""
    engine = PaddleOcrEngine()

    # When not available
    with patch.object(engine, "is_available", return_value=False):
        res = engine.ocr_page_image(b"dummy")
        assert res.text == ""
        assert res.confidence == 0.0

    # When exception raised during OCR
    with patch.object(engine, "is_available", return_value=True):
        with patch.object(engine, "_get_paddle_instance", side_effect=RuntimeError("CUDA out of memory")):
            res = engine.ocr_page_image(b"dummy")
            assert res.text == ""
            assert res.confidence == 0.0


def test_get_ocr_engine_factory(monkeypatch):
    """Verify engine selection priority: Tesseract -> PaddleOCR -> Null."""
    monkeypatch.delenv("ADAM_OCR_ENGINE", raising=False)
    # 1. Tesseract available -> select Tesseract
    with patch.object(TesseractOcrEngine, "is_available", return_value=True):
        with patch.object(PaddleOcrEngine, "is_available", return_value=True):
            engine = get_ocr_engine()
            assert isinstance(engine, TesseractOcrEngine)

    # 2. Tesseract unavailable, Paddle available -> select Paddle
    with patch.object(TesseractOcrEngine, "is_available", return_value=False):
        with patch.object(PaddleOcrEngine, "is_available", return_value=True):
            engine = get_ocr_engine()
            assert isinstance(engine, PaddleOcrEngine)

    # 3. Neither available -> fallback to Null
    with patch.object(TesseractOcrEngine, "is_available", return_value=False):
        with patch.object(PaddleOcrEngine, "is_available", return_value=False):
            engine = get_ocr_engine()
            assert isinstance(engine, NullOcrEngine)

    # 4. Preferred engine requested
    with patch.object(PaddleOcrEngine, "is_available", return_value=True):
        engine = get_ocr_engine(preferred_engine="paddle")
        assert isinstance(engine, PaddleOcrEngine)

    engine_null = get_ocr_engine(preferred_engine="null")
    assert isinstance(engine_null, NullOcrEngine)
