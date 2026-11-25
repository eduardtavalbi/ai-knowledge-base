from functools import lru_cache


MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@lru_cache(maxsize=1)
def _get_model():
    """Load the embedding model only when an embedding is actually requested."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME)


def generate_embedding(text: str) -> list[float]:
    """Generate one embedding for a search query or document-level vector."""
    vector = _get_model().encode(text)
    return vector.tolist()


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate chunk embeddings in batches to reduce model-call overhead."""
    if not texts:
        return []

    vectors = _get_model().encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return vectors.tolist()
