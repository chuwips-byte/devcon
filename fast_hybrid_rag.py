# 빠른 하이브리드 RAG - 속도 최적화 버전
# pip install beautifulsoup4 requests

import os
import requests
import json
import time
from pathlib import Path
from datetime import datetime
import re

def install_beautifulsoup():
    """BeautifulSoup 설치 확인"""
    try:
        from bs4 import BeautifulSoup
        return True
    except ImportError:
        print("⚠️ BeautifulSoup4 설치 권장: pip install beautifulsoup4")
        return False

def extract_text_from_html(html_content):
    """HTML에서 텍스트 추출"""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 불필요한 태그 제거
        for tag in soup(['style', 'script', 'meta', 'link']):
            tag.decompose()
        
        text_parts = []
        
        # 테이블 특별 처리 (시스템 코드 테이블용)
        for table in soup.find_all('table'):
            text_parts.append("\n=== 표 데이터 ===")
            for row in table.find_all('tr'):
                cells = []
                for cell in row.find_all(['td', 'th']):
                    cell_text = cell.get_text(strip=True)
                    if cell_text and cell_text != " ":
                        cells.append(cell_text)
                if cells:
                    text_parts.append(" | ".join(cells))
        
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
    except:
        # BeautifulSoup 없으면 간단한 HTML 태그 제거
        import re
        clean = re.sub('<[^<]+?>', '', html_content)
        return clean

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

class FastHybridRAG:
    def __init__(self):
        # 임계값 조정 (더 엄격하게)
        self.doc_threshold_high = 0.6    # 확실한 문서 매칭
        self.doc_threshold_low = 0.25    # 최소 관련성 (더 엄격)
        self.documents = []
        self.doc_embeddings = None
        self.model = None
        
        # 빠른 모델들 (우선순위)
        self.fast_models = [
            "llama3.2:1b",      # 가장 빠름 (1B 파라미터)
            "qwen2.5:1.5b",     # 빠름 (1.5B 파라미터)
            "llama3.2:3b",      # 보통 (3B 파라미터)
            "phi3:mini"         # 대안
        ]
        
        self.ollama_url = "http://localhost:11434/api/generate"
        self.selected_model = None
        
        # 성능 통계
        self.response_times = []
        
        # 간단한 FAQ 캐시 (즉시 답변)
        self.faq_cache = {}
    
    def check_ollama_and_select_model(self):
        """Ollama 연결 및 가장 빠른 모델 선택"""
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=3)
            if response.status_code == 200:
                models = response.json()
                available_models = [model['name'] for model in models.get('models', [])]
                
                # 빠른 모델 순서로 확인
                for fast_model in self.fast_models:
                    if fast_model in available_models:
                        self.selected_model = fast_model
                        print(f"✅ 빠른 모델 선택: {fast_model}")
                        return True, available_models
                
                # 빠른 모델이 없으면 첫 번째 사용 가능한 모델
                if available_models:
                    self.selected_model = available_models[0]
                    print(f"⚠️ 기본 모델 사용: {self.selected_model}")
                    return True, available_models
                
                return False, []
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
        
        # FAQ 캐시 구축 (빠른 답변용)
        self.build_faq_cache()
        
        return len(self.documents) > 0
    
    def build_faq_cache(self):
        """자주 묻는 질문 캐시 구축"""
        print("🔄 FAQ 캐시 구축 중...")
        
        # 문서에서 패턴 추출해서 캐시 구축
        for doc in self.documents:
            content = doc['content'].lower()
            
            # 시스템 코드 관련 패턴 캐시
            if '시스템' in doc['title'] and '코드' in doc['title']:
                # 간단한 코드 매핑 캐시 생성
                lines = doc['content'].split('\n')
                for line in lines:
                    if '|' in line:
                        parts = [part.strip() for part in line.split('|')]
                        if len(parts) >= 3:
                            system_name = parts[1] if len(parts) > 1 else ""
                            code = parts[2] if len(parts) > 2 else ""
                            
                            if system_name and code and code.isdigit():
                                # 캐시에 추가
                                cache_key = system_name.lower().replace(' ', '')
                                self.faq_cache[cache_key] = f"{system_name}의 시스템 코드는 {code}입니다."
                                
                                # 역방향 캐시도 추가
                                self.faq_cache[f"코드{code}"] = f"코드 {code}는 {system_name} 시스템입니다."
        
        print(f"✅ {len(self.faq_cache)}개 FAQ 캐시 생성")
    
    def check_faq_cache(self, question):
        """FAQ 캐시에서 즉시 답변 확인"""
        question_clean = re.sub(r'[^가-힣a-zA-Z0-9]', '', question.lower())
        
        for cache_key, answer in self.faq_cache.items():
            if cache_key in question_clean:
                return answer
        
        return None
    
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
    
    def call_ollama_fast(self, prompt):
        """최적화된 Ollama 호출"""
        start_time = time.time()
        
        try:
            # 짧은 프롬프트로 최적화
            payload = {
                "model": self.selected_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,      # 낮은 temperature (더 빠름)
                    "top_p": 0.8,           # 낮은 top_p (더 빠름)
                    "max_tokens": 200,      # 짧은 답변 (더 빠름)
                    "repeat_penalty": 1.1
                }
            }
            
            response = requests.post(self.ollama_url, json=payload, timeout=20)  # 짧은 타임아웃
            
            if response.status_code == 200:
                result = response.json()
                answer = result.get('response', '').strip()
                
                # 응답 시간 기록
                response_time = time.time() - start_time
                self.response_times.append(response_time)
                
                return answer
            else:
                return f"API 오류: {response.status_code}"
                
        except requests.exceptions.Timeout:
            return "응답 시간 초과 (20초)"
        except Exception as e:
            return f"연결 실패: {str(e)}"
    
    def generate_fast_answer(self, question, doc_score, doc_content=None):
        """빠른 답변 생성"""
        
        if doc_score >= self.doc_threshold_high:
            # 높은 관련성 - 간단한 문서 기반 답변
            prompt = f"""질문: {question}
문서 내용: {doc_content[:500]}

위 문서를 참고해서 간단명료하게 답변하세요. 2-3문장으로 요약해주세요."""

            answer_type = "📄 문서 기반"
            
        elif doc_score >= self.doc_threshold_low:
            # 중간 관련성 - 간단한 하이브리드
            prompt = f"""질문: {question}
참고 자료: {doc_content[:300]}

간단하고 실용적인 답변을 2-3문장으로 해주세요."""

            answer_type = "🔄 하이브리드"
            
        else:
            # 낮은 관련성 - 간단한 일반 답변
            prompt = f"""질문: {question}

이 질문에 대해 간단하고 유용한 답변을 2-3문장으로 해주세요."""

            answer_type = "🌐 일반 지식"
        
        # 빠른 Ollama 호출
        ai_answer = self.call_ollama_fast(prompt)
        
        return answer_type, ai_answer
    
    def answer_question_fast(self, question):
        """빠른 질문 답변"""
        start_time = time.time()
        
        print(f"\n💬 질문: {question}")
        print("="*50)
        
        # 1. FAQ 캐시 확인 (즉시 답변)
        cached_answer = self.check_faq_cache(question)
        if cached_answer:
            total_time = time.time() - start_time
            print("⚡ FAQ 캐시 답변 (즉시)")
            print(f"🤖 답변: {cached_answer}")
            print(f"⏱️ 응답 시간: {total_time:.2f}초")
            return
        
        # 2. Ollama 연결 확인
        if not self.selected_model:
            print("❌ Ollama 모델이 선택되지 않았습니다.")
            return
        
        # 3. 문서 검색
        doc_score, best_doc, _ = self.find_relevant_docs(question)
        
        # 4. 빠른 답변 생성
        if doc_score >= self.doc_threshold_low:
            answer_type, answer = self.generate_fast_answer(question, doc_score, best_doc['content'])
            doc_info = f"📄 {best_doc['filename']}"
        else:
            answer_type, answer = self.generate_fast_answer(question, doc_score)
            doc_info = "문서 없음"
        
        # 5. 결과 출력
        total_time = time.time() - start_time
        
        print(f"📊 문서 관련성: {doc_score:.1%}")
        print(f"📄 참고: {doc_info}")
        print(f"🎯 {answer_type}")
        print(f"\n🤖 답변:")
        print(answer)
        print(f"\n⏱️ 응답 시간: {total_time:.2f}초")
        print(f"🚀 모델: {self.selected_model}")
    
    def show_performance_stats(self):
        """성능 통계 표시"""
        if self.response_times:
            avg_time = sum(self.response_times) / len(self.response_times)
            min_time = min(self.response_times)
            max_time = max(self.response_times)
            
            print(f"\n📊 성능 통계:")
            print(f"   평균 응답 시간: {avg_time:.2f}초")
            print(f"   최단 응답 시간: {min_time:.2f}초")
            print(f"   최장 응답 시간: {max_time:.2f}초")
            print(f"   총 질문 수: {len(self.response_times)}개")

def fast_hybrid_demo():
    """빠른 하이브리드 RAG 데모"""
    print("⚡ 빠른 하이브리드 RAG 시스템")
    print("속도 최적화 + 품질 유지")
    print("="*50)
    
    # BeautifulSoup 확인
    install_beautifulsoup()
    
    # 빠른 하이브리드 RAG 초기화
    fast_rag = FastHybridRAG()
    
    # 모델 선택
    print("\n🔍 Ollama 모델 확인 중...")
    is_connected, models = fast_rag.check_ollama_and_select_model()
    
    if not is_connected:
        print("❌ Ollama 연결 실패")
        print("💡 빠른 모델 설치 방법:")
        for model in fast_rag.fast_models:
            print(f"   ollama pull {model}")
        return
    
    # 문서 로드
    if not fast_rag.load_documents():
        print("❌ 문서 로드 실패")
        return
    
    # 임베딩 설정
    if not fast_rag.setup_embeddings():
        print("❌ 임베딩 설정 실패")
        return
    
    # 빠른 테스트 질문들
    quick_test_questions = [
        "국문 홈페이지 시스템 코드는?",
        "코드 015는 뭐야?",
        "지라 관련 코드들 알려줘",
        "Redis 캐시 설정 방법은?",  # 문서에 없는 질문
        "영업관리 코드가 궁금해"
    ]
    
    print("\n" + "="*50)
    print("⚡ 빠른 테스트 시작")
    print("="*50)
    
    for question in quick_test_questions:
        fast_rag.answer_question_fast(question)
        print("\n" + "="*50)
    
    # 성능 통계
    fast_rag.show_performance_stats()
    
    print("\n🎉 빠른 하이브리드 RAG 완료!")
    print("\n⚡ 속도 최적화 기능:")
    print("   ✅ FAQ 캐시 (즉시 답변)")
    print("   ✅ 작은 모델 우선 선택")
    print("   ✅ 짧은 프롬프트")
    print("   ✅ 낮은 temperature")
    print("   ✅ 응답 길이 제한")

if __name__ == "__main__":
    fast_hybrid_demo()