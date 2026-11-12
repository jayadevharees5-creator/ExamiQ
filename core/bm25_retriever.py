import re
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi

class BM25KeywordRetriever:
    """
    Keyword-based sparse retriever using BM25Okapi algorithm.
    """

    def __init__(self):
        self.bm25: Optional[BM25Okapi] = None
        self.chunks: List[Dict[str, Any]] = []

    @staticmethod
    def tokenize(text: str) -> List[str]:
        """Simple, fast lower-case word tokenization."""
        return re.findall(r'\b[a-zA-Z0-9_]+\b', text.lower())

    def index_chunks(self, chunks: List[Dict[str, Any]]) -> None:
        """Build BM25 index over chunk text."""
        self.chunks = chunks
        corpus = [self.tokenize(c["text"]) for c in chunks]
        if corpus:
            self.bm25 = BM25Okapi(corpus)
        else:
            self.bm25 = None

    def search(
        self,
        query: str,
        top_k: int = 10,
        page_min: Optional[int] = None,
        page_max: Optional[int] = None,
        doc_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search top_k chunks matching the query keywords.
        Optionally filter by page range or document name.
        """
        if not self.bm25 or not self.chunks:
            return []

        tokenized_query = self.tokenize(query)
        if not tokenized_query:
            return []

        scores = self.bm25.get_scores(tokenized_query)
        # Pair indices with scores
        scored_indices = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in scored_indices:
            if score <= 0.0:
                continue
            chunk = self.chunks[idx]

            # Filters
            if doc_name and chunk.get("doc_name") != doc_name:
                continue
            p_num = chunk.get("page_number", 0)
            if page_min is not None and p_num < page_min:
                continue
            if page_max is not None and p_num > page_max:
                continue

            results.append({
                "chunk": chunk,
                "score": float(score),
                "rank": len(results) + 1
            })

            if len(results) >= top_k:
                break

        return results

    def clear(self) -> None:
        self.bm25 = None
        self.chunks = []
