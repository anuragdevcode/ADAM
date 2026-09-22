"""PDF text extraction, layout awareness, table parsing, and scan detection."""

import io
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

import fitz  # PyMuPDF


@dataclass
class ExtractedPage:
    """Extracted text, structure, tables, and scan metrics for a single page."""
    page_number: int
    clean_text: str
    raw_text: str
    is_scanned: bool
    scan_quality_score: Optional[int]
    detected_language: str
    tables: List[Dict[str, Any]] = field(default_factory=list)
    word_count: int = 0


class PdfExtractor:
    """Extracts clean, structured text, tables, and metadata from digital and scanned PDFs."""

    SCANNED_TEXT_THRESHOLD = 50  # Characters below which a page is treated as scanned

    @staticmethod
    def get_page_count(pdf_bytes: bytes) -> int:
        """Return total page count of a PDF for verification (acceptance criterion: 100% pages accounted)."""
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            count = len(doc)
            doc.close()
            return count
        except Exception as e:
            raise ValueError(f"Failed to count PDF pages: {e}") from e

    @staticmethod
    def render_page_image(pdf_bytes: bytes, page_number: int, dpi: int = 300) -> bytes:
        """Render a single page to PNG bytes for citation display. page_number is 1-indexed."""
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page_idx = page_number - 1
            if page_idx < 0 or page_idx >= len(doc):
                doc.close()
                raise ValueError(f"Page {page_number} out of range (PDF has {len(doc)} pages)")
            page = doc[page_idx]
            pix = page.get_pixmap(dpi=dpi)
            png_bytes = pix.tobytes("png")
            doc.close()
            return png_bytes
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Failed to render page {page_number} to PNG: {e}") from e

    @classmethod
    def extract_pages(cls, pdf_bytes: bytes) -> List[ExtractedPage]:
        """Extract all pages from PDF bytes, preserving layout and isolating tables."""
        pages: List[ExtractedPage] = []

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            raise ValueError(f"Failed to open PDF stream with PyMuPDF: {e}") from e

        for page_idx in range(len(doc)):
            page_num = page_idx + 1
            page = doc[page_idx]

            # 1. Raw and layout-aware text extraction
            raw_text = page.get_text("text") or ""
            clean_text = cls._clean_text(raw_text)

            # 2. Check for scanned / bitmap page
            is_scanned, scan_score = cls._detect_scan(page, len(clean_text.strip()))

            # 3. Detect language (Hindi / English / Bilingual)
            detected_lang = cls.detect_language(clean_text)

            # 4. Extract tables from page (especially annexures)
            tables = cls._extract_tables(page)

            # Calculate word count
            word_count = len(clean_text.split())

            pages.append(
                ExtractedPage(
                    page_number=page_num,
                    clean_text=clean_text,
                    raw_text=raw_text,
                    is_scanned=is_scanned,
                    scan_quality_score=scan_score,
                    detected_language=detected_lang,
                    tables=tables,
                    word_count=word_count,
                )
            )

        doc.close()
        return pages

    @classmethod
    def _clean_text(cls, text: str) -> str:
        """Normalize unicode, whitespace, remove broken line wraps and noise."""
        if not text:
            return ""

        # Normalize unicode (crucial for Devnagari matras and conjuncts)
        text = unicodedata.normalize("NFC", text)

        # Remove standalone header/footer artifact line numbers like "Page 1 of 5"
        text = re.sub(r"(?i)^\s*page\s+\d+\s*(of\s+\d+)?\s*$", "", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*पृष्ठ\s+\d+\s*(का\s+\d+)?\s*$", "", text, flags=re.MULTILINE)

        # Replace non-breaking spaces with normal spaces
        text = text.replace("\u00a0", " ").replace("\ufeff", "")

        # Normalize hyphenated word breaks across line ends (e.g. "govern-\nment" -> "government")
        text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)

        # Collapse excess empty lines (max 2 consecutive newlines)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    @classmethod
    def _detect_scan(cls, page: fitz.Page, text_length: int) -> Tuple[bool, Optional[int]]:
        """Detect if page is a scanned document and evaluate scan quality/DPI."""
        image_list = page.get_images(full=True)
        has_images = len(image_list) > 0

        # If page has very little or no native text and contains bitmap images, it is scanned
        if text_length < cls.SCANNED_TEXT_THRESHOLD and has_images:
            is_scanned = True
            # Compute estimated DPI from primary image
            dpi_scores = []
            rect = page.rect
            for img_info in image_list:
                xref = img_info[0]
                base_image = page.parent.extract_image(xref)
                w, h = base_image["width"], base_image["height"]
                if rect.width > 0 and rect.height > 0:
                    # PDF dimensions are points (1/72 inch)
                    dpi_x = (w / rect.width) * 72
                    dpi_y = (h / rect.height) * 72
                    dpi_scores.append(int((dpi_x + dpi_y) / 2))

            avg_dpi = int(sum(dpi_scores) / len(dpi_scores)) if dpi_scores else 150
            return True, avg_dpi

        return False, None

    @classmethod
    def _format_markdown_table(cls, headers: List[str], rows: List[List[str]]) -> str:
        """Format 2D table data into a clean GitHub Flavored Markdown table string."""
        if not rows and not headers:
            return ""
        col_count = max(len(headers), max((len(r) for r in rows), default=0))
        if col_count == 0:
            return ""

        padded_headers = list(headers) + [""] * (col_count - len(headers))
        hdr_line = "| " + " | ".join(h.replace("|", "\\|") for h in padded_headers) + " |"
        sep_line = "| " + " | ".join(["---"] * col_count) + " |"

        body_lines = []
        for r in rows:
            padded_row = list(r) + [""] * (col_count - len(r))
            body_lines.append("| " + " | ".join(c.replace("|", "\\|") for c in padded_row) + " |")

        return "\n".join([hdr_line, sep_line] + body_lines)

    @classmethod
    def _extract_tables(cls, page: fitz.Page) -> List[Dict[str, Any]]:
        """Extract structured tabular data from annexures using PyMuPDF table finder."""
        tables_data: List[Dict[str, Any]] = []
        try:
            tabs = page.find_tables()
            for idx, tab in enumerate(tabs):
                df_headers = tab.header.names if tab.header else []
                rows = tab.extract()
                clean_rows = []
                for row in rows:
                    clean_rows.append([cell.strip() if cell else "" for cell in row])

                clean_headers = [h.strip() if h else "" for h in df_headers]
                md_table = ""
                if hasattr(tab, "to_markdown"):
                    try:
                        md_table = tab.to_markdown()
                    except Exception:
                        pass
                if not md_table:
                    md_table = cls._format_markdown_table(clean_headers, clean_rows)

                tables_data.append({
                    "table_index": idx + 1,
                    "bbox": list(tab.bbox),
                    "headers": clean_headers,
                    "rows": clean_rows,
                    "markdown": md_table,
                    "row_count": len(clean_rows),
                    "col_count": len(df_headers) if df_headers else (len(clean_rows[0]) if clean_rows else 0),
                })
        except Exception:
            # Table extraction fallback if fitz tables not available on older doc layout
            pass

        return tables_data

    @staticmethod
    def detect_language(text: str) -> str:
        """Analyze character distribution to classify Hindi Devnagari, English, or Bilingual."""
        if not text or not text.strip():
            return "hi"  # Default Uttarakhand state administration language

        devanagari_chars = sum(1 for c in text if "\u0900" <= c <= "\u097f")
        latin_chars = sum(1 for c in text if ("a" <= c <= "z") or ("A" <= c <= "Z"))
        total_letters = devanagari_chars + latin_chars

        if total_letters == 0:
            return "hi"

        dev_ratio = devanagari_chars / total_letters
        lat_ratio = latin_chars / total_letters

        if devanagari_chars >= 5 and latin_chars >= 5 and min(dev_ratio, lat_ratio) >= 0.15:
            return "bilingual"
        elif dev_ratio >= 0.60:
            return "hi"
        else:
            return "en"
