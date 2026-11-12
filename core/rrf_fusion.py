from typing import List, Dict, Any

class ReciprocalRankFusion:
    """
    Implements Reciprocal Rank Fusion (RRF) to merge and rank results
    from multiple distinct retrieval systems (e.g. FAISS Dense + BM25 Sparse).

    Formula:
        RRF_score(d) = sum( 1 / (k + rank_i(d)) ) for each retriever i
    """

    def __init__(self, k: int = 60):
        self.k = k

    def fuse(
        self,
        dense_results: List[Dict[str, Any]],
        bm25_results: List[Dict[str, Any]],
        top_k: int = 6
    ) -> List[Dict[str, Any]]:
        """
        Merges dense vector results and BM25 keyword results using RRF.
        Returns deduplicated top_k chunks sorted by descending RRF score.
        """
        # Map: chunk_id -> { "chunk": chunk, "rrf_score": float, "dense_rank": ..., "bm25_rank": ... }
        fused_items: Dict[str, Dict[str, Any]] = {}

        # 1. Process Dense Results
        for item in dense_results:
            chunk = item["chunk"]
            chunk_id = chunk["chunk_id"]
            dense_rank = item["rank"]  # 1-indexed rank
            score = 1.0 / (self.k + dense_rank)

            fused_items[chunk_id] = {
                "chunk": chunk,
                "rrf_score": score,
                "dense_rank": dense_rank,
                "dense_score": item["score"],
                "bm25_rank": None,
                "bm25_score": None,
                "sources": ["Dense Vector (FAISS)"]
            }

        # 2. Process BM25 Results
        for item in bm25_results:
            chunk = item["chunk"]
            chunk_id = chunk["chunk_id"]
            bm25_rank = item["rank"]  # 1-indexed rank
            score = 1.0 / (self.k + bm25_rank)

            if chunk_id in fused_items:
                fused_items[chunk_id]["rrf_score"] += score
                fused_items[chunk_id]["bm25_rank"] = bm25_rank
                fused_items[chunk_id]["bm25_score"] = item["score"]
                fused_items[chunk_id]["sources"].append("Keyword Search (BM25)")
            else:
                fused_items[chunk_id] = {
                    "chunk": chunk,
                    "rrf_score": score,
                    "dense_rank": None,
                    "dense_score": None,
                    "bm25_rank": bm25_rank,
                    "bm25_score": item["score"],
                    "sources": ["Keyword Search (BM25)"]
                }

        # 3. Sort by descending RRF score
        sorted_fused = sorted(
            fused_items.values(),
            key=lambda x: x["rrf_score"],
            reverse=True
        )

        # 4. Limit to top_k and assign final fusion ranks
        results = []
        for rank, item in enumerate(sorted_fused[:top_k], start=1):
            item["fusion_rank"] = rank
            results.append(item)

        return results
