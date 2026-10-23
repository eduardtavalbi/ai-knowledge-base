from sentence_transformers import SentenceTransformer



model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')


def generate_embedding(text: str) -> list[float]:
    vector = model.encode(text)
    return vector.tolist()
