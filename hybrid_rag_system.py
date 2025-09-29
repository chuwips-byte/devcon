# 하이브리드 RAG 시스템 - 문서 + AI 일반지식 조합
# pip install beautifulsoup4 requests

import os
import requests
import json
from pathlib import Path
from datetime import datetime
import re

def install_beautifulsoup():
    """BeautifulSoup 설치 확인"""
    try:
        from bs4 import BeautifulSoup
        return True
    except ImportError:
        print("❌ BeautifulSoup4가 설치되지 않았습니다.")
        print("💡 설치: pip install beautifulsoup4")
        return False

def extract_text_from_html(html_content):
    """HTML에서 텍스트 추출"""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return html_content  # HTML 태그 포함된 원본 반환
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 불필요한 태그 제거
    for tag in soup(['style', 'script', 'meta', 'link']):
        tag.decompose()
    
    text_parts = []
    
    # 구조화된 텍스트 추출
    for header in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        level = int(header.name[1])
        prefix = '#' * level
        text_parts.append(f"\n{prefix} {header.get_text(strip=True)}\n")
    
    for p in soup.find_all('p'):
        text = p.get_text(strip=True)
        if text:
            text_parts.append(text)
    
    for ul in soup.find_all(['ul', 'ol']):
        for li in ul.find_all('li'):
            text_parts.append(f"• {li.get_text(strip=True)}")
    
    return "\n".join(text_parts)

def read_file_content(file_path):
    """다양한 형식의 파일 읽기"""
    file_ext = file_path.suffix.lower()
    
    try:
        encodings = ['utf-8', 'cp949', 'euc-kr']
        content = None
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    raw_content = f.read()
                content = raw_content
                break
            except UnicodeDecodeError:
                continue
        
        if content is None:
            return "인코딩 오류", "ERROR"
        
        if file_ext in ['.html', '.htm']:
            clean_content = extract_text_from_html(content)
            return clean_content, "HTML"
        else:
            return content, "TEXT"
            
    except Exception as e:
        return f"파일 읽기 오류: {e}", "ERROR"

class HybridRAG:
    def __init__(self):
        self.doc_threshold_high = 0.7    # 확실한 문서 매칭
        self.doc_threshold_low = 0.3     # 최소 관련성
        self.documents = []
        self.doc_embeddings = None
        self.model = None
        
        # Ollama 설정 (로컬 LLM)
        self.ollama_url = "http://localhost:11434/api/generate"
        self.ollama_model = "llama3.2:3b"
        
    def check_ollama_connection(self):
        """Ollama 연결 상태 확인"""
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=3)
            if response.status_code == 200:
                models = response.json()
                available_models = [model['name'] for model in models.get('models', [])]
                return True, available_models
            return False, []
        except:
            return False, []
    
    def load_documents(self):
        """문서 로드"""
        print("📚 문서 로딩 중...")
        
        docs_folder = Path("confluence_docs")
        if not docs_folder.exists():
            print("❌ confluence_docs 폴더가 없습니다.")
            return False
        
        supported_extensions = ['.txt', '.html', '.htm', '.md']
        all_files = []
        
        for ext in supported_extensions:
            files = list(docs_folder.glob(f"*{ext}"))
            all_files.extend(files)
        
        if not all_files:
            print("❌ 지원하는 문서가 없습니다.")
            return False
        
        self.documents = []
        
        for file_path in all_files:
            content, file_type = read_file_content(file_path)
            
            if not content.startswith("파일 읽기 오류") and not content.startswith("인코딩 오류"):
                self.documents.append({
                    'title': file_path.stem.replace('_', ' '),
                    'content': content,
                    'filename': file_path.name,
                    'file_type': file_type
                })
        
        print(f"✅ {len(self.documents)}개 문서 로드 완료")
        return len(self.documents) > 0
    
    def setup_embeddings(self):
        """임베딩 설정"""
        try:
            from sentence_transformers import SentenceTransformer
            from sklearn.metrics.pairwise import cosine_similarity
            import numpy as np
            
            print("🤖 AI 모델 로딩 중...")
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            
            doc_contents = [doc['content'] for doc in self.documents]
            print("🔄 문서 임베딩 중...")
            self.doc_embeddings = self.model.encode(doc_contents)
            
            print("✅ 임베딩 완료!")
            return True
            
        except ImportError as e:
            print(f"❌ 패키지 오류: {e}")
            return False
    
    def find_relevant_docs(self, question):
        """관련 문서 찾기"""
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np
        
        question_embedding = self.model.encode([question])
        similarities = cosine_similarity(question_embedding, self.doc_embeddings)[0]
        
        best_idx = np.argmax(similarities)
        best_score = similarities[best_idx]
        best_doc = self.documents[best_idx]
        
        return best_score, best_doc, best_idx
    
    def call_ollama(self, prompt):
        """Ollama 로컬 LLM 호출"""
        try:
            payload = {
                "model": self.ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "max_tokens": 400
                }
            }
            
            response = requests.post(self.ollama_url, json=payload, timeout=45)
            
            if response.status_code == 200:
                result = response.json()
                return result.get('response', '').strip()
            else:
                return f"Ollama API 오류: {response.status_code}"
                
        except requests.exceptions.Timeout:
            return "Ollama 응답 시간 초과 (45초)"
        except Exception as e:
            return f"Ollama 연결 실패: {str(e)}"
    
    def generate_hybrid_answer(self, question, doc_score, doc_content=None):
        """하이브리드 답변 생성"""
        
        if doc_score >= self.doc_threshold_high:
            # 높은 관련성 - 문서 기반 답변
            prompt = f"""당신은 회사의 기술 문서 도우미입니다.

회사 내부 문서 내용:
{doc_content}

질문: {question}

위 회사 문서를 정확히 참고해서 답변해주세요. 문서에 명시된 내용을 우선으로 하되, 필요시 일반적인 보완 설명을 추가하세요."""

            answer_type = "📄 회사 문서 기반"
            
        elif doc_score >= self.doc_threshold_low:
            # 중간 관련성 - 하이브리드 답변
            prompt = f"""당신은 개발자 도우미입니다.

참고할 회사 문서:
{doc_content}

질문: {question}

회사 문서에서 찾은 정보를 바탕으로 하되, 부족한 부분은 일반적인 개발 모범 사례와 기술 지식으로 보완해서 실용적인 답변을 해주세요. 

회사 특화 내용과 일반 권장사항을 구분해서 설명하세요."""

            answer_type = "🔄 하이브리드 (문서+일반지식)"
            
        else:
            # 낮은 관련성 - 일반 지식 기반
            prompt = f"""당신은 개발자 도우미입니다.

질문: {question}

이 질문에 대해 일반적인 개발 지식과 모범 사례를 바탕으로 도움이 되는 답변을 해주세요. 실무에서 자주 사용되는 방법들을 중심으로 설명해주세요.

주의: 이것은 회사 내부 문서에 없는 내용이므로, 실제 적용 전에 팀 내 확인이 필요할 수 있습니다."""

            answer_type = "🌐 일반 기술 지식"
        
        # Ollama로 답변 생성
        ai_answer = self.call_ollama(prompt)
        
        return answer_type, ai_answer
    
    def answer_question(self, question):
        """하이브리드 질문 답변"""
        print(f"\n💬 질문: {question}")
        print("="*60)
        
        # 1. Ollama 연결 확인
        is_connected, available_models = self.check_ollama_connection()
        
        if not is_connected:
            print("❌ Ollama가 실행되지 않았습니다!")
            print("💡 해결방법:")
            print("   1. Ollama 설치: https://ollama.ai")
            print("   2. 터미널에서 'ollama serve' 실행")
            print("   3. 'ollama pull llama3.2:3b' 로 모델 다운로드")
            print("\n🔄 문서 기반 답변만 제공합니다...")
            
            # 문서 기반 답변만 제공
            doc_score, best_doc, _ = self.find_relevant_docs(question)
            
            if doc_score > 0.3:
                print(f"📊 문서 관련성: {doc_score:.1%}")
                print(f"📄 관련 문서: {best_doc['filename']}")
                
                # 간단한 문서 기반 답변
                content_lines = best_doc['content'].split('\n')
                answer_lines = []
                
                for i, line in enumerate(content_lines):
                    if any(word.lower() in line.lower() for word in question.split() if len(word) > 2):
                        start = max(0, i-1)
                        end = min(len(content_lines), i+4)
                        answer_lines.extend([l.strip() for l in content_lines[start:end] if l.strip()])
                        break
                
                print(f"\n📄 문서 기반 답변:")
                for line in answer_lines[:6]:
                    if line:
                        print(f"   {line}")
            else:
                print("❌ 관련 문서를 찾을 수 없습니다.")
            
            return
        
        if self.ollama_model not in available_models:
            print(f"❌ 모델 '{self.ollama_model}'이 없습니다!")
            print(f"💡 설치: ollama pull {self.ollama_model}")
            return
        
        # 2. 문서 검색
        doc_score, best_doc, _ = self.find_relevant_docs(question)
        print(f"📊 문서 관련성: {doc_score:.1%}")
        
        # 3. 하이브리드 답변 생성
        if doc_score >= self.doc_threshold_low:
            print(f"📄 참고 문서: {best_doc['filename']} ({best_doc['file_type']})")
            answer_type, answer = self.generate_hybrid_answer(question, doc_score, best_doc['content'])
        else:
            print("📄 관련 문서: 없음")
            answer_type, answer = self.generate_hybrid_answer(question, doc_score)
        
        # 4. 결과 출력
        print(f"\n🎯 {answer_type}")
        print(f"\n🤖 답변:")
        print(answer)
        
        print(f"\n💰 비용: 완전 무료 (로컬 실행)")
        
        # 5. 신뢰도 정보
        if doc_score >= self.doc_threshold_high:
            print("✅ 높은 신뢰도: 회사 문서 기반 답변")
        elif doc_score >= self.doc_threshold_low:
            print("🔄 중간 신뢰도: 문서 + 일반 지식 조합")
        else:
            print("⚠️ 일반 지식 기반: 회사 정책 확인 권장")

def hybrid_rag_demo():
    """하이브리드 RAG 데모"""
    print("🚀 하이브리드 RAG 시스템")
    print("문서에 있으면 회사 기준, 없으면 일반 지식으로 답변")
    print("="*60)
    
    # BeautifulSoup 확인
    install_beautifulsoup()
    
    # 하이브리드 RAG 초기화
    hybrid_rag = HybridRAG()
    
    # 문서 로드
    if not hybrid_rag.load_documents():
        print("❌ 문서 로드 실패")
        print("💡 confluence_docs/ 폴더에 .txt, .html 파일을 추가하세요!")
        return
    
    # 임베딩 설정
    if not hybrid_rag.setup_embeddings():
        print("❌ 임베딩 설정 실패")
        return
    
    # Ollama 상태 확인
    print("\n🔍 Ollama 상태 확인 중...")
    is_connected, models = hybrid_rag.check_ollama_connection()
    
    if is_connected:
        print("✅ Ollama 연결됨")
        print(f"📦 사용 가능한 모델: {models}")
        if hybrid_rag.ollama_model in models:
            print(f"✅ {hybrid_rag.ollama_model} 모델 준비됨")
        else:
            print(f"⚠️ {hybrid_rag.ollama_model} 모델 없음")
            print(f"💡 설치: ollama pull {hybrid_rag.ollama_model}")
    else:
        print("❌ Ollama 연결 실패")
        print("💡 Ollama 설치 및 실행 필요")
    
    # 테스트 질문들
    test_questions = [
        # 문서에 있을 가능성이 높은 질문들
        "DB 커넥션 풀 오류 해결 방법?",
        "API 개발 가이드라인은?",
        "로그 레벨 설정 방법?",
        
        # 문서에 없을 가능성이 높은 질문들
        "Redis 클러스터 구성 방법?",
        "GraphQL 최적화 방법?",
        "Kubernetes Pod 오토스케일링 설정?",
        "React 상태 관리 라이브러리 추천?",
        
        # 애매한 질문들
        "성능 최적화 방법?",
        "보안 강화 방법?",
        # 기본 정보 조회

"국문 홈페이지 시스템 코드는 뭐야?",
"영업관리 시스템 코드 알려줘",
"지라1의 코드번호가 궁금해",
"윕스패스 서비스 코드는?",

#🔍 특정 코드 역추적

"코드 015는 어떤 시스템이야?",
"024 코드가 뭘 의미하나요?",
"402 백업 모니터링 코드는 어떤 서비스?",
"코드 220은 무엇인가요?",

#📊 카테고리별 조회

"모니터링 시스템에는 어떤 것들이 있어?",
"백업 서버 모니터링 관련 시스템 코드들 알려줘",
"SMS 발송 관련 시스템들이 뭐가 있나요?",
"홈페이지 관련 시스템 코드들 보여줘",

#🔄 비교 및 관계

"지라와 컨플루언스 관련 코드들 정리해줘",
"윕스패스와 윕스클립 코드 차이점은?",
"그룹웨어 관련 코드가 몇 개나 있어?",
"백업 모니터링과 일반 모니터링 코드 차이는?",

#❓ 존재하지 않는 정보 (하이브리드 테스트용)

"Redis 캐시 서버 코드는 뭐야?",
"Docker 컨테이너 모니터링 코드 알려줘",
"쿠버네티스 클러스터 시스템 코드는?",
"ElasticSearch 로그 시스템 코드가 궁금해"
    ]
    
    print("\n" + "="*60)
    print("🎮 하이브리드 RAG 테스트")
    print("="*60)
    
    for question in test_questions:
        hybrid_rag.answer_question(question)
        print("\n" + "="*60)
        
        # 잠시 대기 (Ollama 부하 방지)
        import time
        time.sleep(1)
    
    print("\n🎉 하이브리드 RAG 데모 완료!")
    print("\n📊 시스템 특징:")
    print("   ✅ 문서에 있으면: 회사 기준 정확한 답변")
    print("   ✅ 문서에 없으면: 일반 기술 지식으로 답변")
    print("   ✅ 완전 무료: 로컬에서 모든 처리")
    print("   ✅ 데이터 보안: 외부 유출 없음")
    
    print("\n💡 다음 단계:")
    print("   - 실제 Confluence 문서 추가")
    print("   - 로그 클러스터링 연동")
    print("   - Slack 봇 통합")

if __name__ == "__main__":
    hybrid_rag_demo()