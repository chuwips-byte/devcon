# rag/trainer.py
from rag.embedder import embed
from rag.vector_store import store

def train_issue(issue_key, 신고내용, 처리내용):
    text = f"[신고내용] {신고내용}\n[처리내용] {처리내용}"
    vec = embed(text)
    store(issue_key, text, vec)
    print(f"✅ 저장 완료: {issue_key}")
