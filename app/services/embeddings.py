from sentence_transformers import SentenceTransformer


model = SentenceTransformer(
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)


def generate_embedding(text: str) -> list[float]:
    """Generate one embedding for a search query or document-level vector."""
    vector = model.encode(text)
    return vector.tolist()


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate chunk embeddings in batches to reduce model-call overhead."""
    if not texts:
        return []

    vectors = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return vectors.tolist()
