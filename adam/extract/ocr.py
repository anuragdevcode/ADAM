"""Pluggable OCR engine abstraction for document text and layout extraction.

Supports Tesseract CLI, PaddleOCR, and a Null fallback engine for environments
where OCR dependencies are not installed. Produces structured page text,
per-block layout data, bounding boxes, and normalized confidence scores.
"""

import csv
import logging
import os
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class OcrResult:
    """Structured result of an OCR extraction pass on a document page or image.

    Attributes:
        text: Transcribed full-page text with layout breaks preserved.
        confidence: Overall page-level confidence score normalized between 0.0 and 1.0.
        blocks: Structured list of extracted layout/text blocks. Each block dictionary contains:
            - 'block_type' (str): Type of block, e.g. 'text'.
            - 'text' (str): Transcribed text of the block.
            - 'bbox' (List[float]): Bounding box [x0, y0, x1, y1] coordinates.
            - 'reading_order' (int): 0-indexed sequence in standard reading order.
            - 'confidence' (float): Normalized block-level confidence (0.0 to 1.0).
    """

    text: str = ""
    confidence: float = 0.0
    blocks: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Clamp confidence score within valid bounds [0.0, 1.0]."""
        if self.confidence < 0.0:
            self.confidence = 0.0
        elif self.confidence > 1.0:
            self.confidence = 1.0


class BaseOcrEngine(ABC):
    """Abstract base class for pluggable OCR engines."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether the OCR engine executable or library is installed and usable.

        Returns:
            bool: True if available, False otherwise.
        """
        pass

    @abstractmethod
    def ocr_page_image(
        self,
        image_bytes: bytes,
        languages: Optional[List[str]] = None,
    ) -> OcrResult:
        """Extract text and layout blocks from a raw page image.

        Args:
            image_bytes: Raw binary image data (e.g. PNG, JPEG, TIFF).
            languages: Optional list of language codes (e.g. ['hin', 'eng']).
                If omitted, the engine's default languages will be used.

        Returns:
            OcrResult containing extracted text, average confidence, and layout blocks.
        """
        pass


class TesseractOcrEngine(BaseOcrEngine):
    """OCR engine implementation backed by the Tesseract CLI tool.

    Extracts text, per-word confidence, and layout bounding boxes using Tesseract's
    TSV output format. Defaults to bilingual Hindi and English recognition.
    """

    DEFAULT_LANGUAGES: List[str] = ["hin", "eng"]
    DEFAULT_OEM: int = 1  # Neural nets LSTM engine only
    DEFAULT_PSM: int = 3  # Fully automatic page segmentation, but no OSD
    DEFAULT_TIMEOUT_SECONDS: int = 60

    def __init__(
        self,
        default_languages: Optional[List[str]] = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize Tesseract engine configuration.

        Args:
            default_languages: Default language codes to use when not passed per call.
            timeout_seconds: Subprocess execution timeout in seconds.
        """
        self.default_languages = default_languages or list(self.DEFAULT_LANGUAGES)
        self.timeout_seconds = timeout_seconds
        self._available_languages: Optional[List[str]] = None

    def is_available(self) -> bool:
        """Check if 'tesseract' binary is discoverable in system PATH.

        Returns:
            bool: True if 'tesseract' executable exists in PATH, False otherwise.
        """
        return shutil.which("tesseract") is not None

    def get_installed_languages(self) -> List[str]:
        """Query Tesseract for installed traineddata languages.

        Returns:
            List of language codes installed in Tesseract tessdata.
        """
        if self._available_languages is not None:
            return self._available_languages

        if not self.is_available():
            self._available_languages = []
            return self._available_languages

        try:
            res = subprocess.run(
                ["tesseract", "--list-langs"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if res.returncode == 0:
                langs = []
                for line in res.stdout.splitlines():
                    cleaned = line.strip()
                    if cleaned and not cleaned.lower().startswith("list of"):
                        langs.append(cleaned)
                self._available_languages = langs
                return self._available_languages
        except Exception as e:
            logger.debug(f"Failed to query installed Tesseract languages: {e}")

        self._available_languages = []
        return self._available_languages

    def ocr_page_image(
        self,
        image_bytes: bytes,
        languages: Optional[List[str]] = None,
    ) -> OcrResult:
        """Run Tesseract on image bytes via subprocess and parse TSV output.

        Args:
            image_bytes: Raw binary image data.
            languages: Optional list of ISO language codes (default: ['hin', 'eng']).

        Returns:
            OcrResult with transcribed text, average confidence, and layout blocks.
        """
        if not image_bytes:
            logger.debug("Empty image bytes passed to TesseractOcrEngine.")
            return OcrResult(text="", confidence=0.0, blocks=[])

        if not self.is_available():
            logger.warning("Tesseract binary not found in PATH.")
            return OcrResult(text="", confidence=0.0, blocks=[])

        target_langs = languages if languages else self.default_languages
        lang_arg = "+".join(target_langs)


        # Detect image format from magic bytes for proper file extension
        ext = ".png"
        if image_bytes.startswith(b"\xff\xd8\xff"):
            ext = ".jpg"
        elif image_bytes.startswith(b"II*\x00") or image_bytes.startswith(b"MM\x00*"):
            ext = ".tiff"

        temp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(image_bytes)
                temp_path = tmp.name

            cmd = [
                "tesseract",
                temp_path,
                "stdout",
                "-l",
                lang_arg,
                "--oem",
                str(self.DEFAULT_OEM),
                "--psm",
                str(self.DEFAULT_PSM),
                "tsv",
            ]

            logger.debug(f"Executing Tesseract command: {' '.join(cmd)}")
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
            )

            if proc.returncode != 0:
                logger.error(
                    f"Tesseract process exited with code {proc.returncode}. "
                    f"stderr: {proc.stderr.strip()}"
                )
                return OcrResult(text="", confidence=0.0, blocks=[])

            return self._parse_tsv(proc.stdout)

        except subprocess.TimeoutExpired:
            logger.error(f"Tesseract timed out after {self.timeout_seconds} seconds.")
            return OcrResult(text="", confidence=0.0, blocks=[])
        except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
            logger.error(f"Subprocess error while running Tesseract: {e}")
            return OcrResult(text="", confidence=0.0, blocks=[])
        except Exception as e:
            logger.error(f"Unexpected error during Tesseract OCR: {e}", exc_info=True)
            return OcrResult(text="", confidence=0.0, blocks=[])
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError as err:
                    logger.debug(f"Failed to remove temporary image file '{temp_path}': {err}")

    def _parse_tsv(self, tsv_text: str) -> OcrResult:
        """Parse Tesseract TSV output into structured OcrResult.

        Tesseract TSV levels:
            1: Page
            2: Block
            3: Paragraph
            4: Line
            5: Word

        Args:
            tsv_text: Raw TSV output string from Tesseract stdout.

        Returns:
            OcrResult with full text, average confidence, and block list.
        """
        lines = tsv_text.splitlines()
        if not lines:
            return OcrResult(text="", confidence=0.0, blocks=[])

        reader = csv.reader(lines, delimiter="\t", quoting=csv.QUOTE_NONE)
        header = next(reader, None)
        if not header:
            return OcrResult(text="", confidence=0.0, blocks=[])

        col_map = {col.strip().lower(): idx for idx, col in enumerate(header)}
        level_idx = col_map.get("level", 0)
        block_idx = col_map.get("block_num", 2)
        par_idx = col_map.get("par_num", 3)
        line_idx = col_map.get("line_num", 4)
        left_idx = col_map.get("left", 6)
        top_idx = col_map.get("top", 7)
        width_idx = col_map.get("width", 8)
        height_idx = col_map.get("height", 9)
        conf_idx = col_map.get("conf", 10)
        text_idx = col_map.get("text", 11)

        # Store explicit level 2 block bounding boxes if provided
        block_boxes: Dict[int, List[float]] = {}
        # words_by_block: block_num -> list of line groups, each line group is list of words
        # where word is {"text": str, "conf": float, "bbox": [x0, y0, x1, y1]}
        block_order: List[int] = []
        block_lines: Dict[int, Dict[int, List[Dict[str, Any]]]] = {}

        for row in reader:
            if not row or len(row) <= max(level_idx, block_idx, left_idx, top_idx, width_idx, height_idx, conf_idx):
                continue

            try:
                level = int(row[level_idx])
                b_num = int(row[block_idx])
                left = float(row[left_idx])
                top = float(row[top_idx])
                width = float(row[width_idx])
                height = float(row[height_idx])
                conf_val = float(row[conf_idx])
            except (ValueError, IndexError):
                continue

            # Level 2 defines a block bounding box
            if level == 2:
                block_boxes[b_num] = [left, top, left + width, top + height]
                continue

            # Level 5 defines a word
            if level == 5:
                w_text = row[text_idx] if len(row) > text_idx else ""
                clean_word = w_text.strip()
                # Tesseract reports conf=-1 for non-words or whitespace
                if not clean_word or conf_val < 0:
                    continue

                # Normalize confidence to [0.0, 1.0]
                norm_conf = max(0.0, min(1.0, conf_val / 100.0))
                p_num = int(row[par_idx]) if len(row) > par_idx else 0
                l_num = int(row[line_idx]) if len(row) > line_idx else 0
                # Unique line identifier combining paragraph and line numbers
                unique_line_key = (p_num * 1000) + l_num

                if b_num not in block_lines:
                    block_lines[b_num] = {}
                    block_order.append(b_num)

                if unique_line_key not in block_lines[b_num]:
                    block_lines[b_num][unique_line_key] = []

                block_lines[b_num][unique_line_key].append({
                    "text": clean_word,
                    "confidence": norm_conf,
                    "bbox": [left, top, left + width, top + height],
                })

        # Assemble layout blocks
        blocks: List[Dict[str, Any]] = []
        all_word_confidences: List[float] = []
        reading_order = 0

        for b_num in block_order:
            lines_dict = block_lines[b_num]
            line_strings: List[str] = []
            block_words: List[Dict[str, Any]] = []

            for line_key in sorted(lines_dict.keys()):
                words = lines_dict[line_key]
                if words:
                    line_text = " ".join(w["text"] for w in words)
                    line_strings.append(line_text)
                    block_words.extend(words)

            block_text = "\n".join(line_strings).strip()
            if not block_text or not block_words:
                continue

            # Compute block bounding box: prefer explicit level 2 bbox, else envelope of words
            if b_num in block_boxes and (block_boxes[b_num][2] > block_boxes[b_num][0]):
                bbox = block_boxes[b_num]
            else:
                x0 = min(w["bbox"][0] for w in block_words)
                y0 = min(w["bbox"][1] for w in block_words)
                x1 = max(w["bbox"][2] for w in block_words)
                y1 = max(w["bbox"][3] for w in block_words)
                bbox = [x0, y0, x1, y1]

            word_confs = [w["confidence"] for w in block_words]
            block_conf = sum(word_confs) / len(word_confs)
            all_word_confidences.extend(word_confs)

            blocks.append({
                "block_type": "text",
                "text": block_text,
                "bbox": [round(c, 2) for c in bbox],
                "reading_order": reading_order,
                "confidence": round(block_conf, 4),
            })
            reading_order += 1

        full_text = "\n\n".join(b["text"] for b in blocks)
        overall_confidence = (
            sum(all_word_confidences) / len(all_word_confidences)
            if all_word_confidences
            else 0.0
        )

        return OcrResult(
            text=full_text,
            confidence=round(overall_confidence, 4),
            blocks=blocks,
        )


class PaddleOcrEngine(BaseOcrEngine):
    """OCR engine implementation backed by the PaddleOCR deep learning library.

    Provides high-accuracy Devanagari and Latin script text recognition with
    structured layout polygon and bounding box outputs.
    """

    DEFAULT_LANG: str = "hi"

    def __init__(self, default_lang: str = DEFAULT_LANG) -> None:
        """Initialize PaddleOCR engine configuration.

        Args:
            default_lang: Default language code (e.g. 'hi' or 'en').
        """
        self.default_lang = default_lang
        self._engines: Dict[str, Any] = {}

    def is_available(self) -> bool:
        """Check if the 'paddleocr' library is installed and importable.

        Returns:
            bool: True if paddleocr can be imported, False otherwise.
        """
        try:
            import paddleocr  # noqa: F401
            return True
        except (ImportError, Exception):
            return False

    def _map_language(self, languages: Optional[List[str]]) -> str:
        """Map generic language codes to PaddleOCR language codes."""
        if not languages:
            return self.default_lang

        for lang in languages:
            lower = lang.lower().strip()
            if lower in ("hin", "hi", "hindi"):
                return "hi"
            if lower in ("eng", "en", "english"):
                return "en"

        return languages[0].lower()

    def _get_paddle_instance(self, lang: str) -> Any:
        """Lazily initialize and cache PaddleOCR instance for the target language."""
        if lang not in self._engines:
            from paddleocr import PaddleOCR
            logger.info(f"Initializing PaddleOCR(use_angle_cls=True, lang='{lang}')")
            self._engines[lang] = PaddleOCR(use_angle_cls=True, lang=lang)
        return self._engines[lang]

    def ocr_page_image(
        self,
        image_bytes: bytes,
        languages: Optional[List[str]] = None,
    ) -> OcrResult:
        """Extract text and layout blocks using PaddleOCR.

        Args:
            image_bytes: Raw binary image data.
            languages: Optional list of language codes (e.g. ['hin', 'eng']).

        Returns:
            OcrResult with transcribed text, average confidence, and structured blocks.
        """
        if not image_bytes:
            logger.debug("Empty image bytes passed to PaddleOcrEngine.")
            return OcrResult(text="", confidence=0.0, blocks=[])

        if not self.is_available():
            logger.warning("PaddleOCR is not available in current environment.")
            return OcrResult(text="", confidence=0.0, blocks=[])

        target_lang = self._map_language(languages)
        ext = ".png"
        if image_bytes.startswith(b"\xff\xd8\xff"):
            ext = ".jpg"

        temp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(image_bytes)
                temp_path = tmp.name

            ocr_engine = self._get_paddle_instance(target_lang)
            raw_result = ocr_engine.ocr(temp_path, cls=True)
            return self._parse_paddle_output(raw_result)

        except Exception as e:
            logger.error(f"Error during PaddleOCR extraction: {e}", exc_info=True)
            return OcrResult(text="", confidence=0.0, blocks=[])
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError as err:
                    logger.debug(f"Failed to remove temporary image file '{temp_path}': {err}")

    def _parse_paddle_output(self, raw_result: Any) -> OcrResult:
        """Parse PaddleOCR's raw output structure into standard OcrResult.

        Handles standard nested list format `[[ [points, (text, score)], ... ]]`
        as well as dictionary/JSON-style outputs.

        Args:
            raw_result: The raw object returned by PaddleOCR.ocr().

        Returns:
            Structured OcrResult.
        """
        if not raw_result:
            return OcrResult(text="", confidence=0.0, blocks=[])

        items = raw_result
        # Handle standard PaddleOCR wrapping: list of page results
        if isinstance(items, list) and len(items) > 0:
            if isinstance(items[0], list):
                if not items[0]:
                    return OcrResult(text="", confidence=0.0, blocks=[])
                if isinstance(items[0][0], (list, tuple, dict)):
                    items = items[0]

        blocks: List[Dict[str, Any]] = []
        confidences: List[float] = []
        reading_order = 0

        for item in items:
            if not item:
                continue

            text = ""
            conf = 0.0
            bbox = [0.0, 0.0, 0.0, 0.0]

            # Case A: Dictionary output
            if isinstance(item, dict):
                text = str(item.get("text") or item.get("transcription") or "").strip()
                conf_val = item.get("confidence") or item.get("score") or 0.0
                try:
                    conf = float(conf_val)
                except (ValueError, TypeError):
                    conf = 0.0

                raw_box = item.get("bbox") or item.get("points")
                if raw_box:
                    if len(raw_box) == 4 and all(isinstance(c, (int, float)) for c in raw_box):
                        bbox = [float(c) for c in raw_box]
                    elif isinstance(raw_box, (list, tuple)):
                        xs = [p[0] for p in raw_box if isinstance(p, (list, tuple)) and len(p) >= 2]
                        ys = [p[1] for p in raw_box if isinstance(p, (list, tuple)) and len(p) >= 2]
                        if xs and ys:
                            bbox = [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))]

            # Case B: Standard list/tuple format: [points, (text, confidence)]
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                raw_box = item[0]
                text_score = item[1]

                if isinstance(text_score, (list, tuple)) and len(text_score) >= 2:
                    text = str(text_score[0]).strip()
                    try:
                        conf = float(text_score[1])
                    except (ValueError, TypeError):
                        conf = 0.0
                elif isinstance(text_score, str):
                    text = text_score.strip()
                    conf = 1.0

                if isinstance(raw_box, (list, tuple)):
                    if len(raw_box) == 4 and all(isinstance(c, (int, float)) for c in raw_box):
                        bbox = [float(c) for c in raw_box]
                    else:
                        xs = [p[0] for p in raw_box if isinstance(p, (list, tuple)) and len(p) >= 2]
                        ys = [p[1] for p in raw_box if isinstance(p, (list, tuple)) and len(p) >= 2]
                        if xs and ys:
                            bbox = [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))]

            if not text:
                continue

            # Normalize confidence score to [0.0, 1.0]
            if conf > 1.0:
                conf = conf / 100.0
            conf = max(0.0, min(1.0, conf))

            blocks.append({
                "block_type": "text",
                "text": text,
                "bbox": [round(c, 2) for c in bbox],
                "reading_order": reading_order,
                "confidence": round(conf, 4),
            })
            confidences.append(conf)
            reading_order += 1

        full_text = "\n".join(b["text"] for b in blocks)
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        return OcrResult(
            text=full_text,
            confidence=round(avg_conf, 4),
            blocks=blocks,
        )


class NullOcrEngine(BaseOcrEngine):
    """Fallback OCR engine returning empty results when no real engine is available."""

    def is_available(self) -> bool:
        """Always returns True as NullOcrEngine requires no external dependencies.

        Returns:
            bool: Always True.
        """
        return True

    def ocr_page_image(
        self,
        image_bytes: bytes,
        languages: Optional[List[str]] = None,
    ) -> OcrResult:
        """Return an empty OcrResult without attempting recognition.

        Args:
            image_bytes: Raw binary image data (ignored).
            languages: Optional language list (ignored).

        Returns:
            OcrResult(text='', confidence=0.0, blocks=[]).
        """
        logger.debug("NullOcrEngine called; returning empty OcrResult.")
        return OcrResult(text="", confidence=0.0, blocks=[])


_WARNED_NO_OCR = False


def get_ocr_engine(preferred_engine: Optional[str] = None) -> BaseOcrEngine:
    """Factory function to select and instantiate an OCR engine.

    Checks engines in priority order:
    1. Preferred engine (if specified and available)
    2. TesseractOcrEngine
    3. PaddleOcrEngine
    4. NullOcrEngine (fallback)

    Args:
        preferred_engine: Optional engine name ('tesseract', 'paddle', or 'null')
            to prioritize.

    Returns:
        BaseOcrEngine: The selected OCR engine instance.
    """
    global _WARNED_NO_OCR
    if preferred_engine:
        name = preferred_engine.strip().lower()
        if name in ("tesseract", "tesseractocr"):
            engine = TesseractOcrEngine()
            if engine.is_available():
                logger.info("Selected OCR engine: TesseractOcrEngine (preferred)")
                _WARNED_NO_OCR = False
                return engine
            logger.warning("Preferred OCR engine 'tesseract' is not available.")
        elif name in ("paddle", "paddleocr"):
            engine = PaddleOcrEngine()
            if engine.is_available():
                logger.info("Selected OCR engine: PaddleOcrEngine (preferred)")
                _WARNED_NO_OCR = False
                return engine
            logger.warning("Preferred OCR engine 'paddle' is not available.")
        elif name in ("null", "nulloct", "none"):
            logger.info("Selected OCR engine: NullOcrEngine (preferred)")
            return NullOcrEngine()
        else:
            logger.warning(
                f"Unknown preferred OCR engine '{preferred_engine}'. "
                f"Proceeding with default engine resolution."
            )

    tesseract = TesseractOcrEngine()
    if tesseract.is_available():
        logger.info("Selected OCR engine: TesseractOcrEngine")
        _WARNED_NO_OCR = False
        return tesseract

    paddle = PaddleOcrEngine()
    if paddle.is_available():
        logger.info("Selected OCR engine: PaddleOcrEngine")
        _WARNED_NO_OCR = False
        return paddle

    if not _WARNED_NO_OCR:
        logger.warning(
            "No OCR engine available (neither Tesseract nor PaddleOCR). "
            "Falling back to NullOcrEngine for scanned pages. "
            "(To enable OCR for scanned government orders on macOS: brew install tesseract tesseract-lang)"
        )
        _WARNED_NO_OCR = True
    else:
        logger.debug("No OCR engine available; using NullOcrEngine.")

    return NullOcrEngine()
