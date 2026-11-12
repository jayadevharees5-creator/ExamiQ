from typing import List, Dict, Any, Optional
from config import Config
from core.text_chunker import TextChunker
from core.embeddings import EmbeddingGenerator
from core.vector_store import FAISSVectorStore
from core.bm25_retriever import BM25KeywordRetriever
from core.rrf_fusion import ReciprocalRankFusion

class RAGPipeline:
    """
    Orchestrates the entire Hybrid RAG system:
    Document Chunking -> Embedding -> FAISS & BM25 Indexing -> Hybrid Search -> RRF Fusion.
    """

    def __init__(
        self,
        chunk_size: int = Config.DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = Config.DEFAULT_CHUNK_OVERLAP,
        rrf_k: int = Config.DEFAULT_RRF_K
    ):
        self.chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.embedder = EmbeddingGenerator()
        self.vector_store = FAISSVectorStore(dimension=384)
        self.bm25 = BM25KeywordRetriever()
        self.rrf = ReciprocalRankFusion(k=rrf_k)
        self.indexed_chunks: List[Dict[str, Any]] = []

    def set_rrf_k(self, k: int) -> None:
        self.rrf.k = k

    def index_documents(self, documents_pages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Chunks and indexes all extracted pages into both FAISS and BM25.
        documents_pages is a flat list of page dicts with doc_name, page_number, text.
        """
        self.vector_store.clear()
        self.bm25.clear()
        self.indexed_chunks.clear()

        # 1. Chunk pages
        chunks = self.chunker.chunk_pages(documents_pages)
        if not chunks:
            return {"success": False, "chunk_count": 0, "error": "No extractable text found to chunk."}

        self.indexed_chunks = chunks

        # 2. Dense vector indexing
        texts = [c["text"] for c in chunks]
        embeddings = self.embedder.embed_documents(texts)
        self.vector_store.add_embeddings(embeddings, chunks)

        # 3. BM25 keyword indexing
        self.bm25.index_chunks(chunks)

        return {
            "success": True,
            "chunk_count": len(chunks),
            "vector_store_total": self.vector_store.total_chunks,
            "bm25_total": len(self.bm25.chunks)
        }

    def save_pipeline(self, user_id: str) -> bool:
        """Persist FAISS index and chunk metadata for the user."""
        return self.vector_store.save_index(user_id)

    def load_pipeline(self, user_id: str) -> bool:
        """Load FAISS index and chunk metadata for the user, and rebuild BM25 index."""
        loaded = self.vector_store.load_index(user_id)
        if loaded and self.vector_store.chunks:
            self.indexed_chunks = list(self.vector_store.chunks)
            self.bm25.clear()
            self.bm25.index_chunks(self.indexed_chunks)
            return True
        return False

    def retrieve(
        self,
        query: str,
        top_k_dense: int = Config.DEFAULT_TOP_K_DENSE,
        top_k_bm25: int = Config.DEFAULT_TOP_K_BM25,
        top_k_fused: int = Config.DEFAULT_TOP_K_FUSED,
        page_min: Optional[int] = None,
        page_max: Optional[int] = None,
        doc_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes hybrid retrieval:
        1. Dense search via FAISS.
        2. Sparse search via BM25.
        3. Reciprocal Rank Fusion of the two ranked lists.
        """
        if not self.indexed_chunks:
            return {
                "fused_results": [],
                "context_text": "",
                "dense_count": 0,
                "bm25_count": 0,
                "insufficient_context": True
            }

        # Dense retrieval
        query_vec = self.embedder.embed_query(query)
        dense_results = self.vector_store.search(
            query_vec,
            top_k=top_k_dense,
            page_min=page_min,
            page_max=page_max,
            doc_name=doc_name
        )

        # BM25 retrieval
        bm25_results = self.bm25.search(
            query,
            top_k=top_k_bm25,
            page_min=page_min,
            page_max=page_max,
            doc_name=doc_name
        )

        # RRF Fusion
        fused = self.rrf.fuse(dense_results, bm25_results, top_k=top_k_fused)

        if not fused:
            return {
                "fused_results": [],
                "context_text": "",
                "dense_count": len(dense_results),
                "bm25_count": len(bm25_results),
                "insufficient_context": True
            }

        # Assemble structured context block for LLM with explicit page annotations
        context_blocks = []
        for item in fused:
            c = item["chunk"]
            block = (
                f"--- [SOURCE: {c['doc_name']} | PAGE: {c['page_number']} | "
                f"RRF SCORE: {item['rrf_score']:.4f}] ---\n"
                f"{c['text']}\n"
            )
            context_blocks.append(block)

        context_text = "\n".join(context_blocks)

        return {
            "fused_results": fused,
            "context_text": context_text,
            "dense_count": len(dense_results),
            "bm25_count": len(bm25_results),
            "fused_count": len(fused),
            "insufficient_context": len(context_text.strip()) < 50
        }
