import faiss
import numpy as np
from typing import List, Dict, Any, Tuple, Optional

class FAISSVectorStore:
    """
    In-memory FAISS vector index with metadata mapping for dense retrieval.
    """

    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.index = faiss.IndexFlatIP(dimension)  # Cosine similarity for normalized vectors
        self.chunks: List[Dict[str, Any]] = []

    def add_embeddings(self, embeddings: np.ndarray, chunks: List[Dict[str, Any]]) -> None:
        """
        Add normalized embeddings and corresponding chunk metadata.
        """
        if embeddings.shape[0] == 0:
            return
        
        if embeddings.shape[1] != self.dimension:
            raise ValueError(f"Embedding dimension {embeddings.shape[1]} does not match index dimension {self.dimension}")

        self.index.add(embeddings)
        self.chunks.extend(chunks)

    def search(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        page_min: Optional[int] = None,
        page_max: Optional[int] = None,
        doc_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search top_k closest chunks using cosine similarity.
        Optionally filter results by page range or document name.
        """
        if self.index.ntotal == 0:
            return []

        # Retrieve a slightly larger pool if filtering is active
        fetch_k = min(self.index.ntotal, top_k * 3 if (page_min or page_max or doc_name) else top_k)
        scores, indices = self.index.search(query_vector, fetch_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.chunks):
                continue
            chunk = self.chunks[idx]

            # Apply metadata filters if provided
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
        """Reset index and stored chunks."""
        self.index.reset()
        self.chunks.clear()

    def save_index(self, filename: str) -> bool:
        """Persist FAISS index and chunk metadata to disk.
        ``filename`` is the base name (without extension) inside a dedicated ``faiss_indexes`` folder.
        """
        import os, json
        storage_dir = "faiss_indexes"
        os.makedirs(storage_dir, exist_ok=True)
        safe_name = "".join(c for c in filename if c.isalnum() or c in ("-", "_")).rstrip()
        if not safe_name:
            safe_name = "default"
        index_path = os.path.join(storage_dir, f"{safe_name}.index")
        meta_path = os.path.join(storage_dir, f"{safe_name}_meta.json")
        try:
            # Save FAISS index binary
            faiss.write_index(self.index, index_path)
            # Save chunk metadata as JSON
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(self.chunks, f)
            return True
        except Exception as e:
            return False

    def load_index(self, filename: str) -> bool:
        """Load FAISS index and chunk metadata if they exist.
        ``filename`` is the base name (without extension) inside the ``faiss_indexes`` folder.
        """
        import os, json
        storage_dir = "faiss_indexes"
        safe_name = "".join(c for c in filename if c.isalnum() or c in ("-", "_")).rstrip()
        if not safe_name:
            safe_name = "default"
        index_path = os.path.join(storage_dir, f"{safe_name}.index")
        meta_path = os.path.join(storage_dir, f"{safe_name}_meta.json")
        if os.path.isfile(index_path) and os.path.isfile(meta_path):
            try:
                self.index = faiss.read_index(index_path)
                with open(meta_path, "r", encoding="utf-8") as f:
                    self.chunks = json.load(f)
                return True
            except Exception:
                self.index = faiss.IndexFlatIP(self.dimension)
                self.chunks = []
                return False
        else:
            # No persisted data – start fresh
            self.index = faiss.IndexFlatIP(self.dimension)
            self.chunks = []
            return False

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)
