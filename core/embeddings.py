from typing import List, Union
import numpy as np
from functools import lru_cache
from sentence_transformers import SentenceTransformer
from config import Config

@lru_cache(maxsize=1)
def load_embedding_model(model_name: str = Config.EMBEDDING_MODEL_NAME) -> SentenceTransformer:
    """
    Cached SentenceTransformer singleton to prevent reloading model on repeated calls.
    """
    model = SentenceTransformer(model_name)
    return model

class EmbeddingGenerator:
    """
    Generates normalized dense embeddings using HuggingFace Sentence Transformers.
    """

    def __init__(self, model_name: str = Config.EMBEDDING_MODEL_NAME):
        self.model_name = model_name
        self.model = load_embedding_model(model_name)

    def embed_documents(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """
        Embed a list of text chunks and normalize vectors for cosine similarity.
        """
        if not texts:
            return np.empty((0, 384), dtype=np.float32)
            
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True
        )
        return embeddings.astype(np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        """
        Embed a single search query and normalize vector.
        """
        embedding = self.model.encode(
            [query],
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True
        )
        return embedding.astype(np.float32)
