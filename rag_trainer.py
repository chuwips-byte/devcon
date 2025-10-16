# -*- coding: utf-8 -*-
"""
RAG (Retrieval-Augmented Generation) Trainer 모듈
- 문서 임베딩 및 벡터 DB 구축
- FAISS를 사용한 유사도 검색
- Sentence Transformers 기반 임베딩
"""

import os
import sys
import pickle
import numpy as np
from typing import List, Dict, Any, Optional
from datetime import datetime

# Windows 콘솔 인코딩 문제 해결
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# 필수 라이브러리 import
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    print("⚠️ sentence-transformers가 설치되지 않았습니다.")
    print("   설치: pip install sentence-transformers")

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    print("⚠️ faiss-cpu가 설치되지 않았습니다.")
    print("   설치: pip install faiss-cpu")


class RAGTrainer:
    """RAG 학습 및 벡터 DB 구축 클래스"""

    def __init__(self, model_name: str = 'sentence-transformers/all-MiniLM-L6-v2'):
        """
        RAG Trainer 초기화

        Args:
            model_name: 사용할 Sentence Transformer 모델명
        """
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError("sentence-transformers 라이브러리가 필요합니다.")

        if not FAISS_AVAILABLE:
            raise ImportError("faiss-cpu 라이브러리가 필요합니다.")

        print(f"🔄 임베딩 모델 로딩: {model_name}")
        try:
            self.model = SentenceTransformer(model_name)
            self.model_name = model_name
            print("✅ 모델 로드 완료")
        except Exception as e:
            print(f"❌ 모델 로드 실패: {e}")
            raise

        self.documents = []
        self.index = None
        self.dimension = None

    def build_vector_database(self, documents: List[Dict[str, Any]]) -> None:
        """
        문서 리스트로부터 벡터 데이터베이스 구축

        Args:
            documents: 문서 리스트
                각 문서는 다음 구조:
                {
                    'id': 문서 ID,
                    'text': 텍스트 내용,
                    'type': 문서 타입,
                    'metadata': 메타데이터
                }
        """
        if not documents:
            raise ValueError("문서 리스트가 비어있습니다.")

        print(f"\n🔨 벡터 DB 구축 시작...")
        print(f"   문서 수: {len(documents)}개")

        # 문서 저장
        self.documents = documents

        # 텍스트 추출
        texts = [doc['text'] for doc in documents]

        print(f"   임베딩 생성 중...")
        try:
            # 임베딩 생성
            embeddings = self.model.encode(
                texts,
                show_progress_bar=True,
                convert_to_numpy=True
            )

            print(f"   임베딩 완료: shape={embeddings.shape}")

            # FAISS 인덱스 생성
            self.dimension = embeddings.shape[1]
            self.index = faiss.IndexFlatL2(self.dimension)

            # 임베딩을 float32로 변환하여 추가
            embeddings_float32 = embeddings.astype('float32')
            self.index.add(embeddings_float32)

            print(f"✅ 벡터 DB 구축 완료")
            print(f"   인덱스 크기: {self.index.ntotal}개")
            print(f"   벡터 차원: {self.dimension}차원")

        except Exception as e:
            print(f"❌ 벡터 DB 구축 실패: {e}")
            raise

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        쿼리와 유사한 문서 검색

        Args:
            query: 검색 쿼리
            top_k: 반환할 상위 문서 개수

        Returns:
            유사도가 높은 문서 리스트
        """
        if self.index is None:
            raise RuntimeError("벡터 DB가 구축되지 않았습니다.")

        # 쿼리 임베딩
        query_embedding = self.model.encode([query], convert_to_numpy=True)
        query_embedding_float32 = query_embedding.astype('float32')

        # 검색
        distances, indices = self.index.search(query_embedding_float32, top_k)

        # 결과 구성
        results = []
        for i, (distance, idx) in enumerate(zip(distances[0], indices[0])):
            if idx < len(self.documents):
                result = {
                    'rank': i + 1,
                    'document': self.documents[idx],
                    'distance': float(distance),
                    'similarity': float(1 / (1 + distance))  # 거리를 유사도로 변환
                }
                results.append(result)

        return results

    def save_model(self, path: str) -> None:
        """
        모델 및 벡터 DB 저장

        Args:
            path: 저장 경로
        """
        if self.index is None:
            raise RuntimeError("저장할 벡터 DB가 없습니다.")

        # 디렉토리 생성
        os.makedirs(path, exist_ok=True)

        try:
            # FAISS 인덱스 저장
            index_path = os.path.join(path, 'index.faiss')
            faiss.write_index(self.index, index_path)
            print(f"✅ FAISS 인덱스 저장: {index_path}")

            # 문서 리스트 저장
            docs_path = os.path.join(path, 'documents.pkl')
            with open(docs_path, 'wb') as f:
                pickle.dump(self.documents, f)
            print(f"✅ 문서 리스트 저장: {docs_path}")

            # 메타데이터 저장
            metadata = {
                'model_name': self.model_name,
                'dimension': self.dimension,
                'num_documents': len(self.documents),
                'created_at': datetime.now().isoformat()
            }
            metadata_path = os.path.join(path, 'metadata.pkl')
            with open(metadata_path, 'wb') as f:
                pickle.dump(metadata, f)
            print(f"✅ 메타데이터 저장: {metadata_path}")

            print(f"\n✅ 모델 전체 저장 완료: {path}")
            return {
                "model_path": path,
                "issue_keys": [doc.get('id') for doc in self.documents if doc.get('id')],
                "issue_count": len(self.documents)
            }

        except Exception as e:
            print(f"❌ 모델 저장 실패: {e}")
            raise

    def load_model(self, path: str) -> None:
        """
        저장된 모델 및 벡터 DB 로드

        Args:
            path: 모델이 저장된 경로
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"경로를 찾을 수 없습니다: {path}")

        try:
            # FAISS 인덱스 로드
            index_path = os.path.join(path, 'index.faiss')
            self.index = faiss.read_index(index_path)
            print(f"✅ FAISS 인덱스 로드: {index_path}")

            # 문서 리스트 로드
            docs_path = os.path.join(path, 'documents.pkl')
            with open(docs_path, 'rb') as f:
                self.documents = pickle.load(f)
            print(f"✅ 문서 리스트 로드: {docs_path} ({len(self.documents)}개)")

            # 메타데이터 로드
            metadata_path = os.path.join(path, 'metadata.pkl')
            if os.path.exists(metadata_path):
                with open(metadata_path, 'rb') as f:
                    metadata = pickle.load(f)
                self.dimension = metadata.get('dimension')
                print(f"✅ 메타데이터 로드: {metadata_path}")

            print(f"\n✅ 모델 전체 로드 완료: {path}")

        except Exception as e:
            print(f"❌ 모델 로드 실패: {e}")
            raise

    def get_stats(self) -> Dict[str, Any]:
        """
        현재 벡터 DB 통계 반환

        Returns:
            통계 정보 딕셔너리
        """
        if self.index is None:
            return {
                'status': 'not_built',
                'num_documents': 0,
                'dimension': None
            }

        return {
            'status': 'ready',
            'num_documents': len(self.documents),
            'dimension': self.dimension,
            'index_size': self.index.ntotal,
            'model_name': self.model_name
        }


def test_rag_trainer():
    """RAG Trainer 테스트 함수"""
    print("="*60)
    print("RAG Trainer 테스트 시작")
    print("="*60)

    # 테스트 문서 준비
    sample_documents = [
        {
            'id': 'DOC-001',
            'text': 'NullPointerException이 발생했습니다. UserService에서 사용자 조회 실패.',
            'type': 'bug',
            'metadata': {'severity': 'high'}
        },
        {
            'id': 'DOC-002',
            'text': 'OutOfMemoryError가 발생했습니다. 힙 메모리 부족.',
            'type': 'bug',
            'metadata': {'severity': 'critical'}
        },
        {
            'id': 'DOC-003',
            'text': 'ConnectionTimeout 오류입니다. 데이터베이스 연결 시간 초과.',
            'type': 'bug',
            'metadata': {'severity': 'medium'}
        }
    ]

    # RAG Trainer 생성
    print("\n1. RAG Trainer 초기화...")
    trainer = RAGTrainer(model_name='sentence-transformers/all-MiniLM-L6-v2')

    # 벡터 DB 구축
    print("\n2. 벡터 DB 구축...")
    trainer.build_vector_database(sample_documents)

    # 통계 확인
    print("\n3. 통계 확인...")
    stats = trainer.get_stats()
    print(f"   상태: {stats['status']}")
    print(f"   문서 수: {stats['num_documents']}개")
    print(f"   벡터 차원: {stats['dimension']}차원")

    # 검색 테스트
    print("\n4. 검색 테스트...")
    query = "사용자 조회 중 에러가 발생했습니다"
    results = trainer.search(query, top_k=3)

    print(f"\n   쿼리: '{query}'")
    print(f"   결과:")
    for result in results:
        doc = result['document']
        print(f"   {result['rank']}위: {doc['id']} (유사도: {result['similarity']:.3f})")
        print(f"        {doc['text'][:50]}...")

    # 모델 저장 테스트
    print("\n5. 모델 저장 테스트...")
    save_path = "models/test_rag_model"
    trainer.save_model(save_path)

    print("\n" + "="*60)
    print("테스트 완료")
    print("="*60)


if __name__ == "__main__":
    # 필수 라이브러리 확인
    if not SENTENCE_TRANSFORMERS_AVAILABLE or not FAISS_AVAILABLE:
        print("\n❌ 필수 라이브러리가 설치되지 않았습니다.")
        print("\n다음 명령어로 설치하세요:")
        print("pip install sentence-transformers faiss-cpu")
        sys.exit(1)

    # 테스트 실행
    test_rag_trainer()