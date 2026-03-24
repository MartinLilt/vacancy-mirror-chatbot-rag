"""Local embedding helpers."""

from __future__ import annotations

from sentence_transformers import SentenceTransformer


class LocalEmbeddingService:
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def encode(self, texts: list[str], *, batch_size: int = 32) -> list[list[float]]:
        vectors = self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=True,
        )
        return [vector.tolist() for vector in vectors]
