# 다중 파일 형식 지원 RAG (TXT + HTML + 기타)
# pip install beautifulsoup4 (HTML 파싱용)

import os
from pathlib import Path
from datetime import datetime
import re

def install_beautifulsoup():
    """BeautifulSoup 설치 확인 및 안내"""
    try:
        from bs4 import BeautifulSoup
        return True
    except ImportError:
        print("❌ BeautifulSoup4가 설치되지 않았습니다.")
        print("💡 설치 명령어: pip install beautifulsoup4")
        return False

def extract_text_from_html(html_content):
    """HTML에서 구조화된 텍스트 추출"""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return "HTML 파싱 불가 - beautifulsoup4 설치 필요"
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 불필요한 태그 제거
    for tag in soup(['style', 'script', 'meta', 'link', 'nav', 'header', 'footer']):
        tag.decompose()
    
    # Confluence 특화 정리
    for tag in soup.find_all(['div'], class_=['confluence-information-macro']):
        tag.decompose()
    
    text_parts = []
    
    # 페이지 제목 추출
    title = soup.find('title')
    if title:
        text_parts.append(f"# {title.get_text(strip=True)}")
    
    # 메인 제목들 추출 (h1-h6)
    for header in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        level = int(header.name[1])
        prefix = '#' * level
        header_text = header.get_text(strip=True)
        if header_text:
            text_parts.append(f"\n{prefix} {header_text}\n")
    
    # 본문 텍스트 추출
    for p in soup.find_all('p'):
        text = p.get_text(strip=True)
        if text and len(text) > 5:  # 의미있는 텍스트만
            text_parts.append(text)
    
    # 리스트 항목 추출
    for ul in soup.find_all(['ul', 'ol']):
        for li in ul.find_all('li', recursive=False):  # 중첩 방지
            list_text = li.get_text(strip=True)
            if list_text:
                text_parts.append(f"• {list_text}")
    
    # 코드 블록 추출
    for code in soup.find_all(['code', 'pre']):
        code_text = code.get_text(strip=True)
        if code_text and len(code_text.split('\n')) > 1:  # 여러 줄 코드만
            text_parts.append(f"\n```\n{code_text}\n```\n")
        elif code_text:  # 인라인 코드
            text_parts.append(f"`{code_text}`")
    
    # 테이블 추출
    for table in soup.find_all('table'):
        text_parts.append("\n--- 표 ---")
        for row in table.find_all('tr'):
            cells = []
            for cell in row.find_all(['td', 'th']):
                cell_text = cell.get_text(strip=True)
                if cell_text:
                    cells.append(cell_text)
            if cells:
                text_parts.append(" | ".join(cells))
    
    # 인용구/정보박스 추출
    for blockquote in soup.find_all(['blockquote', 'div'], class_=['highlight', 'info', 'warning', 'note']):
        quote_text = blockquote.get_text(strip=True)
        if quote_text:
            text_parts.append(f"> {quote_text}")
    
    # 링크 정보 추출 (중요한 것만)
    for link in soup.find_all('a', href=True):
        href = link.get('href')
        link_text = link.get_text(strip=True)
        if link_text and href and not href.startswith('#'):
            text_parts.append(f"[링크] {link_text}: {href}")
    
    return "\n".join(text_parts)

def detect_file_encoding(file_path):
    """파일 인코딩 자동 감지"""
    encodings = ['utf-8', 'cp949', 'euc-kr', 'utf-16', 'ascii']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                f.read()
            return encoding
        except UnicodeDecodeError:
            continue
    
    return 'utf-8'  # 기본값

def read_file_content(file_path):
    """파일 형식에 따른 내용 읽기"""
    file_ext = file_path.suffix.lower()
    
    try:
        # 인코딩 감지
        encoding = detect_file_encoding(file_path)
        
        with open(file_path, 'r', encoding=encoding) as f:
            raw_content = f.read()
        
        if file_ext == '.html' or file_ext == '.htm':
            # HTML 파일 처리
            clean_content = extract_text_from_html(raw_content)
            file_type = "HTML"
            
        elif file_ext == '.txt':
            # 텍스트 파일 처리
            clean_content = raw_content
            file_type = "TEXT"
            
        elif file_ext == '.md':
            # 마크다운 파일 처리
            clean_content = raw_content
            file_type = "MARKDOWN"
            
        else:
            # 기타 파일 (텍스트로 시도)
            clean_content = raw_content
            file_type = "UNKNOWN"
        
        return clean_content, file_type, encoding
        
    except Exception as e:
        return f"파일 읽기 오류: {e}", "ERROR", "unknown"

def check_and_load_multi_format_documents():
    """다양한 형식의 문서 확인 및 로드"""
    print("🔍 다중 형식 문서 폴더 확인 중...")
    print("=" * 60)
    
    docs_folder = Path("confluence_docs")
    
    if not docs_folder.exists():
        print("❌ confluence_docs 폴더가 없습니다.")
        docs_folder.mkdir()
        print("📁 confluence_docs 폴더를 생성했습니다.")
        print("💡 여기에 .txt, .html, .htm, .md 파일들을 넣어주세요!")
        return [], "없음"
    
    # 지원하는 파일 형식들
    supported_extensions = ['.txt', '.html', '.htm', '.md']
    all_files = []
    
    for ext in supported_extensions:
        files = list(docs_folder.glob(f"*{ext}"))
        all_files.extend(files)
    
    if not all_files:
        print("⚠️ 지원하는 파일이 없습니다!")
        print("📄 지원 형식: .txt, .html, .htm, .md")
        print("💡 confluence_docs/ 폴더에 파일을 추가하세요.")
        return [], "없음"
    
    # 파일 목록 상세 표시
    print(f"📂 문서 폴더: {docs_folder.absolute()}")
    print(f"📋 발견된 파일 목록 ({len(all_files)}개):")
    print("-" * 60)
    
    documents = []
    
    # BeautifulSoup 설치 확인
    has_bs4 = install_beautifulsoup()
    
    for i, file_path in enumerate(all_files, 1):
        # 파일 정보 수집
        stat = file_path.stat()
        file_size = stat.st_size
        modified_time = datetime.fromtimestamp(stat.st_mtime)
        
        # 파일 내용 읽기
        content, file_type, encoding = read_file_content(file_path)
        
        # 미리보기 생성
        if content and not content.startswith("파일 읽기 오류"):
            lines = content.split('\n')
            non_empty_lines = [line.strip() for line in lines if line.strip()]
            first_line = non_empty_lines[0][:60] + "..." if non_empty_lines and len(non_empty_lines[0]) > 60 else (non_empty_lines[0] if non_empty_lines else "")
            char_count = len(content)
            line_count = len(lines)
        else:
            first_line = content[:60] if content else "읽기 실패"
            char_count = 0
            line_count = 0
        
        # 파일 형식별 아이콘
        type_icons = {
            "HTML": "🌐",
            "TEXT": "📄",
            "MARKDOWN": "📝",
            "ERROR": "❌",
            "UNKNOWN": "❓"
        }
        
        icon = type_icons.get(file_type, "📄")
        
        # 파일 정보 출력
        print(f"{i:2d}. {icon} {file_path.name}")
        print(f"     형식: {file_type} ({encoding})")
        print(f"     크기: {file_size:,} bytes ({char_count:,} 문자)")
        print(f"     줄수: {line_count:,} 줄")
        print(f"     수정: {modified_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"     미리보기: {first_line}")
        
        # HTML 파일 특별 정보
        if file_type == "HTML" and not has_bs4:
            print(f"     ⚠️ HTML 파싱 제한: beautifulsoup4 설치 권장")
        
        print()
        
        # 문서 객체 생성
        documents.append({
            'title': file_path.stem.replace('_', ' ').replace('-', ' '),
            'content': content,
            'filename': file_path.name,
            'file_path': str(file_path),
            'file_type': file_type,
            'encoding': encoding,
            'size': file_size,
            'char_count': char_count,
            'line_count': line_count,
            'modified': modified_time
        })
    
    # 요약 정보
    type_counts = {}
    total_chars = 0
    
    for doc in documents:
        doc_type = doc['file_type']
        type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
        total_chars += doc['char_count']
    
    print("📊 문서 요약:")
    print(f"   총 파일: {len(documents)}개")
    for doc_type, count in type_counts.items():
        icon = {"HTML": "🌐", "TEXT": "📄", "MARKDOWN": "📝", "ERROR": "❌"}.get(doc_type, "❓")
        print(f"   {icon} {doc_type}: {count}개")
    print(f"   총 문자 수: {total_chars:,}자")
    
    return documents, "다중형식"

def multi_format_rag_demo():
    """다중 형식 지원 RAG 데모"""
    print("🚀 다중 형식 Confluence RAG 데모")
    print("지원 형식: TXT, HTML, HTM, MD")
    print("=" * 60)
    
    try:
        # 패키지 확인
        print("📦 패키지 로딩 중...")
        from sentence_transformers import SentenceTransformer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np
        print("✅ 핵심 패키지 준비됨!")
        
        # BeautifulSoup 확인
        install_beautifulsoup()
        
        # 문서 확인 및 로드
        documents, file_source = check_and_load_multi_format_documents()
        
        if not documents:
            print("❌ 처리할 문서가 없습니다.")
            print("\n💡 시작하는 방법:")
            print("   1. confluence_docs/ 폴더에 파일 추가")
            print("   2. Confluence Export → HTML로 다운로드")
            print("   3. 또는 페이지 내용을 .txt로 복사-붙여넣기")
            return
        
        # 오류 문서 필터링
        valid_documents = [doc for doc in documents if not doc['content'].startswith("파일 읽기 오류")]
        
        if not valid_documents:
            print("❌ 읽을 수 있는 문서가 없습니다.")
            return
        
        print(f"\n✅ {len(valid_documents)}개 문서 처리 가능 (총 {len(documents)}개 중)")
        
        # AI 모델 로딩
        print(f"\n🤖 AI 모델 로딩 중...")
        model = SentenceTransformer('all-MiniLM-L6-v2')
        print("✅ AI 모델 준비 완료!")
        
        # 문서 내용 준비
        doc_contents = [doc['content'] for doc in valid_documents]
        
        # 문서 임베딩
        print("🔄 다중 형식 문서 AI 분석 중...")
        doc_embeddings = model.encode(doc_contents)
        print("✅ 문서 분석 완료!")
        
        # 향상된 질문 답변 함수
        def enhanced_qa_with_format_info(question):
            print(f"\n💬 질문: {question}")
            print("-" * 50)
            
            # 질문 임베딩
            question_embedding = model.encode([question])
            
            # 유사도 계산
            similarities = cosine_similarity(question_embedding, doc_embeddings)[0]
            
            # 상위 3개 결과 표시
            top_indices = np.argsort(similarities)[-3:][::-1]
            
            print("📊 관련도 순위:")
            for i, idx in enumerate(top_indices, 1):
                doc = valid_documents[idx]
                score = similarities[idx]
                type_icon = {"HTML": "🌐", "TEXT": "📄", "MARKDOWN": "📝"}.get(doc['file_type'], "❓")
                print(f"  {i}. {type_icon} {doc['filename']} ({doc['file_type']}) - {score:.1%}")
            
            # 가장 관련있는 문서로 답변
            best_idx = top_indices[0]
            best_doc = valid_documents[best_idx]
            confidence = similarities[best_idx]
            
            print(f"\n🎯 선택된 문서: {best_doc['filename']}")
            print(f"📊 신뢰도: {confidence:.1%}")
            print(f"📄 형식: {best_doc['file_type']} ({best_doc['encoding']})")
            print(f"📏 크기: {best_doc['char_count']:,}자")
            
            if confidence > 0.15:  # 15% 이상 관련성
                # 스마트 답변 추출
                content_lines = best_doc['content'].split('\n')
                answer_lines = []
                
                # 질문 키워드와 관련된 섹션 찾기
                question_keywords = [word.lower() for word in question.split() if len(word) > 2]
                
                for i, line in enumerate(content_lines):
                    line_clean = line.strip()
                    if any(keyword in line_clean.lower() for keyword in question_keywords):
                        # 관련 라인 발견시 주변 컨텍스트 포함
                        start = max(0, i-2)
                        end = min(len(content_lines), i+6)
                        section = content_lines[start:end]
                        answer_lines.extend([l.strip() for l in section if l.strip()])
                        break
                
                print(f"\n💡 답변:")
                if answer_lines:
                    for line in answer_lines[:10]:  # 최대 10줄
                        if line:
                            print(f"   {line}")
                else:
                    # 전체 내용에서 미리보기
                    preview = best_doc['content'][:400].replace('\n\n', ' ')
                    print(f"   {preview}...")
                
                print(f"\n📁 출처: {best_doc['file_path']}")
                
            else:
                print("❌ 관련 문서를 찾을 수 없습니다.")
                print(f"💭 다른 키워드로 시도해보세요.")
        
        # 데모 질문들
        demo_questions = [
            "설치 방법은?",
            "오류 해결 방법",
            "설정하는 방법",
            "Arreo 시스템 코드 목록",
            "메일관리시스템 시스템 코드"
        ]
        
        print("\n" + "=" * 60)
        print("🎮 다중 형식 RAG 테스트")
        print("=" * 60)
        
        for question in demo_questions:
            enhanced_qa_with_format_info(question)
            print("\n" + "=" * 60)
        
        print(f"\n🎉 다중 형식 RAG 데모 완료!")
        print(f"✅ {len(valid_documents)}개 문서에서 AI 답변 생성 성공!")
        
        print("\n💡 지원되는 Confluence Export 형식:")
        print("   🌐 HTML: 가장 정확한 구조 추출")
        print("   📄 TXT: 빠른 처리")
        print("   📝 MD: 마크다운 형식")
        
    except ImportError as e:
        print(f"❌ 패키지 설치 필요: {e}")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    multi_format_rag_demo()