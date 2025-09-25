# rag/embedder.py
from sentence_transformers import SentenceTransformer

# 로컬에서 무료로 동작하는 모델 (한글 가능 모델도 있음)
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

def embed(text: str):
    vec = model.encode(text).tolist()
    return vec
