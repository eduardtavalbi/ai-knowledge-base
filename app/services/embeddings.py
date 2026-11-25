from threading import Lock


MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

_model = None
_model_lock = Lock()


def _get_model():
    """Load the embedding model once, on the first embedding request."""
    global _model

    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                _model = SentenceTransformer(MODEL_NAME)

    return _model


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
