import re
from typing import List, Dict, Any

class TextChunker:
    """
    Splits extracted PDF pages into overlapping chunks while preserving
    document metadata, page references, and section headers.
    """

    def __init__(self, chunk_size: int = 750, chunk_overlap: int = 150):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def clean_text(self, text: str) -> str:
        """Sanitize text, normalizing whitespace and line endings."""
        text = re.sub(r'\r\n', '\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def chunk_pages(self, pages_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Takes page objects and produces chunks with metadata.
        Chunks are bound to page numbers, or cross boundaries if needed,
        while maintaining precise source page citations.
        """
        chunks: List[Dict[str, Any]] = []
        chunk_counter = 0

        for idx, page in enumerate(pages_data):
            text = self.clean_text(page.get("text", ""))
            doc_name = page.get("doc_name") or page.get("filename") or "document.pdf"
            page_num = page.get("page_number") or page.get("page_num") or (idx + 1)

            if not text:
                continue

            # If the page text is shorter than chunk size, treat whole page as one chunk
            if len(text) <= self.chunk_size:
                chunk_counter += 1
                chunks.append({
                    "chunk_id": f"{doc_name}_p{page_num}_c{chunk_counter}",
                    "text": text,
                    "doc_name": doc_name,
                    "page_number": page_num,
                    "char_count": len(text)
                })
                continue

            # Overlapping sliding window within the page
            start = 0
            while start < len(text):
                end = min(start + self.chunk_size, len(text))
                
                # If we are not at the end of the text, try to break at a newline or space
                if end < len(text):
                    last_newline = text.rfind('\n', start + int(self.chunk_size * 0.7), end)
                    if last_newline != -1:
                        end = last_newline + 1
                    else:
                        last_space = text.rfind(' ', start + int(self.chunk_size * 0.7), end)
                        if last_space != -1:
                            end = last_space + 1

                chunk_text = text[start:end].strip()
                if len(chunk_text) >= 40:  # Avoid trivial fragments
                    chunk_counter += 1
                    chunks.append({
                        "chunk_id": f"{doc_name}_p{page_num}_c{chunk_counter}",
                        "text": chunk_text,
                        "doc_name": doc_name,
                        "page_number": page_num,
                        "char_count": len(chunk_text)
                    })

                if end >= len(text):
                    break

                # Advance window by chunk_size - overlap
                step = max(self.chunk_size - self.chunk_overlap, 50)
                start += step

        return chunks
