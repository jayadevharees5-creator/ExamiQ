import re
import io
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Tuple, Optional
import pymupdf

class DocumentProcessor:
    """
    Handles multi-format document ingestion (PDF, DOCX, TXT),
    scanned PDF detection, metadata extraction, and unit boundary discovery.
    """

    @staticmethod
    def process_pdf(file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """Extracts text page-by-page from PDF, checks text density for scanned files."""
        try:
            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
            total_pages = len(doc)
            pages_data = []
            total_char_count = 0
            empty_or_low_text_pages = 0

            detected_units: List[Dict[str, Any]] = []
            unit_regex = re.compile(
                r'^(?:UNIT|CHAPTER|MODULE)\s*([0-9IVX]+)[\s:\.\-]+([^\n\r]{3,80})',
                re.IGNORECASE | re.MULTILINE
            )

            for page_num in range(total_pages):
                page = doc[page_num]
                text = page.get_text("text").strip()
                char_count = len(text)
                total_char_count += char_count

                if char_count < 30:
                    empty_or_low_text_pages += 1

                matches = unit_regex.findall(text)
                for match in matches:
                    u_num = match[0].strip()
                    u_title = match[1].strip()
                    detected_units.append({
                        "unit_number": f"Unit {u_num}",
                        "title": u_title,
                        "page_number": page_num + 1
                    })

                pages_data.append({
                    "page_number": page_num + 1,
                    "text": text,
                    "char_count": char_count,
                    "doc_name": filename
                })

            doc.close()

            avg_chars = total_char_count / max(total_pages, 1)
            is_scanned = (total_pages > 0 and (avg_chars < 50 or (empty_or_low_text_pages / total_pages) > 0.85))

            return {
                "filename": filename,
                "file_type": "PDF",
                "total_pages": total_pages,
                "pages_data": pages_data,
                "total_characters": total_char_count,
                "is_scanned": is_scanned,
                "detected_units": detected_units,
                "success": True,
                "error": None
            }
        except Exception as e:
            return {
                "filename": filename,
                "file_type": "PDF",
                "total_pages": 0,
                "pages_data": [],
                "total_characters": 0,
                "is_scanned": False,
                "detected_units": [],
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def process_docx(file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """Extracts text paragraphs from DOCX XML with zero external dependencies."""
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                xml_content = zf.read('word/document.xml')
                tree = ET.fromstring(xml_content)
                ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

                paragraphs = []
                for p in tree.iter(f"{{{ns['w']}}}p"):
                    texts = [node.text for node in p.iter(f"{{{ns['w']}}}t") if node.text]
                    if texts:
                        paragraphs.append("".join(texts).strip())

            full_text = "\n\n".join([p for p in paragraphs if p])
            
            # Divide into simulated pages (~1800 characters per page)
            page_size = 1800
            pages_data = []
            char_pos = 0
            page_num = 1

            while char_pos < len(full_text):
                end_pos = min(char_pos + page_size, len(full_text))
                if end_pos < len(full_text):
                    last_nl = full_text.rfind('\n', char_pos + int(page_size * 0.7), end_pos)
                    if last_nl != -1:
                        end_pos = last_nl + 1

                chunk = full_text[char_pos:end_pos].strip()
                if chunk:
                    pages_data.append({
                        "page_number": page_num,
                        "text": chunk,
                        "char_count": len(chunk),
                        "doc_name": filename
                    })
                    page_num += 1

                char_pos = end_pos

            if not pages_data:
                pages_data.append({
                    "page_number": 1,
                    "text": full_text or "No text content.",
                    "char_count": len(full_text),
                    "doc_name": filename
                })

            return {
                "filename": filename,
                "file_type": "DOCX",
                "total_pages": len(pages_data),
                "pages_data": pages_data,
                "total_characters": len(full_text),
                "is_scanned": False,
                "detected_units": [],
                "success": True,
                "error": None
            }
        except Exception as e:
            return {
                "filename": filename,
                "file_type": "DOCX",
                "total_pages": 0,
                "pages_data": [],
                "total_characters": 0,
                "is_scanned": False,
                "detected_units": [],
                "success": False,
                "error": str(e)
            }

    @staticmethod
    def process_txt(file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """Extracts text from plain text files."""
        try:
            try:
                full_text = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                full_text = file_bytes.decode("latin-1", errors="replace")

            full_text = full_text.strip()
            page_size = 1800
            pages_data = []
            char_pos = 0
            page_num = 1

            while char_pos < len(full_text):
                end_pos = min(char_pos + page_size, len(full_text))
                if end_pos < len(full_text):
                    last_nl = full_text.rfind('\n', char_pos + int(page_size * 0.7), end_pos)
                    if last_nl != -1:
                        end_pos = last_nl + 1

                chunk = full_text[char_pos:end_pos].strip()
                if chunk:
                    pages_data.append({
                        "page_number": page_num,
                        "text": chunk,
                        "char_count": len(chunk),
                        "doc_name": filename
                    })
                    page_num += 1

                char_pos = end_pos

            if not pages_data:
                pages_data.append({
                    "page_number": 1,
                    "text": full_text or "No text content.",
                    "char_count": len(full_text),
                    "doc_name": filename
                })

            return {
                "filename": filename,
                "file_type": "TXT",
                "total_pages": len(pages_data),
                "pages_data": pages_data,
                "total_characters": len(full_text),
                "is_scanned": False,
                "detected_units": [],
                "success": True,
                "error": None
            }
        except Exception as e:
            return {
                "filename": filename,
                "file_type": "TXT",
                "total_pages": 0,
                "pages_data": [],
                "total_characters": 0,
                "is_scanned": False,
                "detected_units": [],
                "success": False,
                "error": str(e)
            }

    @classmethod
    def process_document(cls, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """Dispatcher for PDF, DOCX, and TXT documents."""
        ext = filename.lower().split('.')[-1]
        if ext == "pdf":
            return cls.process_pdf(file_bytes, filename)
        elif ext in ["docx", "doc"]:
            return cls.process_docx(file_bytes, filename)
        elif ext in ["txt", "md"]:
            return cls.process_txt(file_bytes, filename)
        else:
            return cls.process_txt(file_bytes, filename)

# Backward-compatible alias
PDFProcessor = DocumentProcessor
