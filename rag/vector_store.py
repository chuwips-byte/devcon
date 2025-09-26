import chromadb

# 영구 저장 모드 (폴더는 자동 생성됨)
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection("jira_issues")

def store(issue_key, text, vector):
    """하나의 이슈를 저장"""
    collection.add(
        ids=[issue_key],
        documents=[text],
        embeddings=[vector],
        metadatas=[{"issueKey": issue_key}]
    )

def search_similar_error(query_text, embed, n=3):
    """비슷한 에러 검색"""
    query_vec = embed(query_text)
    results = collection.query(query_embeddings=[query_vec], n_results=n)

    # 보기 쉽게 가공
    matches = []
    for i in range(len(results["ids"][0])):
        matches.append({
            "issueKey": results["metadatas"][0][i]["issueKey"],
            "text": results["documents"][0][i],
            "similarity": 1 - results["distances"][0][i]  # cosine distance → 유사도
        })
    return matches

def list_all():
    """컬렉션 안의 모든 데이터 확인"""
    return collection.get()
