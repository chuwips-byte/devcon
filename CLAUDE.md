# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

**로그 모니터링 시스템 v3.1** - RAG-Ollama 통합 지능형 에러 분석 시스템입니다.

**핵심 특징 (v3.1 업데이트):**
- 🚀 **RAG + Ollama 완전 통합**: 과거 Jira 이슈를 AI 분석에 자동 반영
- 🔍 **2단계 AI 분석**: RAG 검색 → Ollama 분석 (컨텍스트 제공)
- 📊 **과거 사례 추적**: `past_cases_referenced`, `rag_enhanced` 메타데이터
- 🎯 **향상된 신뢰도**: 검증된 해결책 기반 분석 (신뢰도 상승)
- 🐛 **상세한 디버깅 로그**: RAG 검색 과정 전체 추적 가능
- ⚡ **Drain3 실시간 클러스터링**: 로그 패턴 자동 분류
- 🔑 **SSH 원격 모니터링**: 다중 서버 로그 통합 분석
- 🖥️ **통합 웹 대시보드**: 실시간 모니터링 + RAG 학습 + SSH 연결

## 주요 명령어

### 설치 및 설정
```bash
# 초기 설정 (venv 생성, 의존성 설치, .env 생성)
python setup.py

# 가상환경 활성화
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 의존성 설치/업데이트
pip install -r requirements.txt
```

### 시스템 실행
```bash
# 통합 실행 (권장)
python main.py --mode dashboard  # 통합 웹 대시보드 (모든 기능 포함)
python main.py --mode monitor    # 실시간 모니터링 (터미널 모드)
python main.py --mode generate   # 테스트 로그 생성 (별도 터미널)
python main.py --mode test       # Drain3 기본 학습
python main.py --mode rag        # RAG 학습 (대시보드 권장)
python main.py --mode ssh        # SSH 연결 (대시보드 권장)
python main.py --mode jira       # Jira 연동 테스트

# 직접 실행 (개발용)
python 1_basic_drain3_test.py    # Drain3 학습
python clustering_monitor.py     # 메인 모니터링
python 3_log_generator.py        # 로그 생성기
python web_dashboard.py          # 통합 웹 대시보드
python ollama_integration.py     # AI 분석기 테스트
python rag_trainer.py            # RAG Trainer 테스트
```

### 테스트
```bash
# Slack 연동 테스트
python slack_integration.py

# Jira 연동 테스트
python jira_integration.py

# Ollama AI 연동 테스트
python ollama_integration.py

# RAG Trainer 테스트 (Sentence Transformers + FAISS)
python rag_trainer.py
```

## 아키텍처 개요

### 핵심 컴포넌트

**1. 로그 클러스터링 엔진 (`clustering_monitor.py`)**
- Watchdog + Drain3를 사용한 메인 모니터링 서비스
- `D:\devcon\logs` 디렉토리의 로그 처리
- 단일 라인 및 멀티라인 스택트레이스 처리
- 알림 스팸 방지를 위한 쿨다운 메커니즘 (5분)
- 각 클러스터별 원본 로그 예시 저장 (최대 3개)
- 로컬 HTML/JSON 리포트 생성 지원
- SSH를 통한 원격 서버 로그도 동일 엔진으로 처리

**2. RAG 통합 AI 에러 분석기 (`ollama_integration.py`)** (★ v3.1 완전 재설계!)
- **클래스**: `RagIntegratedOllamaAnalyzer` (기존 `OllamaErrorAnalyzer` 대체)
- **주요 변경사항**:
  - RAG 모델 자동 로드 (`_load_latest_rag_model()`)
  - 유사 이슈 검색 통합 (`_search_similar_issues()`)
  - RAG 향상 프롬프트 생성 (`_create_rag_enhanced_prompt()`)

- **핵심 메서드**:
  ```python
  # 1. 초기화 시 RAG 모델 자동 로드
  def __init__(self, rag_models_dir="models"):
      self._load_latest_rag_model()  # 최신 모델 자동 탐색

  # 2. 에러 분석 (2단계)
  def analyze_error(self, error_log, error_template, occurrence_count):
      # 1단계: RAG 검색
      similar_issues = self._search_similar_issues(error_log, error_template)

      # 2단계: Ollama 분석 (과거 사례 컨텍스트 포함)
      prompt = self._create_rag_enhanced_prompt(..., similar_issues)
      result = self._call_ollama_api(prompt)

      # 결과에 RAG 정보 추가
      result['past_cases_referenced'] = len(similar_issues)
      result['rag_enhanced'] = True
      result['similar_issues'] = similar_issues
  ```

- **반환 데이터 구조** (확장됨):
  ```python
  {
      "error_type": "...",
      "root_cause": "... (유사 사례 참고)",
      "immediate_actions": ["... (과거 사례 기반)", ...],
      "confidence": 95,  # 과거 사례 있으면 상승
      "past_cases_referenced": 3,  # NEW!
      "rag_enhanced": True,  # NEW!
      "similar_issues": [  # NEW!
          {"issue_id": "WATD-123", "similarity": 0.87, "rank": 1},
          ...
      ]
  }
  ```

- **디버깅 로그** (대폭 강화):
  - 🔍 RAG 검색 쿼리 출력
  - 📄 각 검색 결과의 유사도 표시
  - 📝 프롬프트 생성 과정 로깅
  - ⏱️ 분석 시작/완료/소요 시간 추적

- 로컬 Ollama 서버 연동 (http://localhost:11434)
- 기본 모델: `mistral:latest`
- Ollama 사용 불가시 패턴 기반 분석으로 자동 전환

**3. 통합 웹 대시보드 (`web_dashboard.py`)** (★ RAG 통합 분석기 연동)
- Flask + SocketIO 실시간 웹 인터페이스
- http://localhost:5000 에서 실행
- **RAG 통합 Ollama 분석기 사용**:
  ```python
  from ollama_integration import RagIntegratedOllamaAnalyzer
  analyzer = RagIntegratedOllamaAnalyzer()  # 자동으로 RAG 모델 로드
  ```
- 왼쪽 메뉴 시스템:
  - 📊 로그 모니터링: 실시간 로그 분석 및 클러스터링 (RAG 향상 AI 분석)
  - 🧠 RAG 학습: Jira 이슈 수집 및 벡터 DB 구축
  - 🔑 SSH 연결: 원격 서버 로그 모니터링
  - 💻 시스템 정보: 서버 상태 확인
- 주요 기능:
  - 실시간 통계 카드 (총 로그, 에러, 에러율, 패턴)
  - 실시간 로그 스트림 (최근 100개)
  - **RAG 향상 AI 분석 결과** 표시 (과거 사례 참조 정보 포함)
  - Chart.js 타임라인 시각화
  - SSH 로그 스트리밍 (최근 500개)
- 메모리 최적화 (maxlen을 가진 deque 사용)
- `LogClusteringHandler` 상속으로 코어 로직 재사용

**4. Slack 연동 (`slack_integration.py`)**
- Webhook 기반 알림
- 향상된 알림 기능:
  - 원본 로그 예시 (최대 3개)
  - AI 분석 결과
  - 심각도 기반 색상 구분
  - 주기적 요약 리포트 (10분마다)
  - **Jira 이슈 생성 링크**
    - 📝 클릭 시 Jira 작성 페이지로 이동
    - 제안 제목 자동 생성
    - 웹 링크 방식 (사용자가 상세 내용 작성)
- `SLACK_WEBHOOK_URL` 환경변수를 통해 동작

**5. Jira 연동 (`jira_integration.py`)**
- **이슈 생성 기능** (Slack → Jira):
  - `create_issue()`: Jira API를 통한 이슈 자동 생성
  - `generate_web_link()`: Jira 작성 페이지 링크 생성 (제목 포함)
  - 인증 방식:
    - Jira Cloud: API Token (JIRA_EMAIL + JIRA_API_TOKEN)
    - Jira Server/Data Center: Basic Auth (JIRA_USERNAME + JIRA_PASSWORD)
  - 자동 생성되는 이슈 정보 (API 방식):
    - 에러 패턴, 발생 횟수, 심각도
    - AI 분석 결과 (근본 원인, 조치사항, 예방 방법)
    - 원본 로그 예시 (Jira 코드 블록)
    - 자동 우선순위 설정 (발생 횟수 기반)
    - 자동 라벨링 (log-monitoring, automated, cluster-ID)
- **이슈 조회 기능** (Jira → RAG):
  - `fetch_bug_issues_for_rag()`: Bug 이슈 일괄 조회 (라벨 정보 포함)
  - `search_issues()`: JQL 기반 검색 (페이지네이션 지원)
  - `parse_issue_for_training()`: RAG 학습용 데이터 파싱
- 환경변수: `JIRA_URL`, `JIRA_PROJECT_KEY`, 인증 정보

**6. RAG Trainer (`rag_trainer.py`)** (NEW!)
- **Sentence Transformers + FAISS 기반** 벡터 검색 시스템
- Jira 이슈를 학습하여 유사 에러 해결책 제안
- 핵심 기능:
  - `build_vector_database()`: 문서 임베딩 및 FAISS 인덱스 구축
  - `search()`: 쿼리와 유사한 문서 검색 (Top-K)
  - `save_model()` / `load_model()`: 학습 모델 저장/로드
- 데이터 구조:
  - `models/bug_rag_model_YYYYMMDD_HHMMSS/`
    - `index.faiss`: FAISS 벡터 인덱스
    - `documents.pkl`: 문서 메타데이터 (Jira 이슈 정보)
    - `metadata.pkl`: 모델 정보 (모델명, 차원, 생성 시간)
- 사용 모델: `sentence-transformers/all-MiniLM-L6-v2` (기본)
- 거리 기반 유사도 계산: `similarity = 1 / (1 + distance)`

**7. SSH 원격 모니터링 (web_dashboard.py 통합)**
- Paramiko 기반 SSH 연결 및 로그 스트리밍
- 웹 대시보드에서 설정:
  - Host, Port, Username, Password, 로그 파일 경로
  - 세션 기반 연결 정보 관리 (파일 저장 안함)
- 실시간 로그 스트리밍:
  - `tail -f` 명령으로 원격 로그 실시간 수신
  - SocketIO를 통한 웹 전송
  - SSH 로그도 동일한 클러스터링 엔진 적용
- 보안 고려사항:
  - 연결 정보는 메모리에만 저장
  - 프로덕션에서는 SSH 키 기반 인증 권장

### 데이터 흐름

```
┌─────────────────────────┐
│ 다중 로그 소스           │
├─────────┬───────┬───────┤
│로컬 파일 │SSH 원격│Jira   │
│(Watchdog)│(tail -f)│ API  │
└────┬────┴───┬───┴───┬───┘
     │        │       │
     ▼        ▼       ▼
┌──────────────────┐  ┌─────────────┐
│clustering_monitor│  │rag_trainer  │
│(Drain3 클러스터링)│  │(FAISS 벡터화)│
└────────┬─────────┘  └──────┬──────┘
         │                   │
         ▼ (에러 3회↑)       │
    ┌────────────┐           │
    │ AI 분석     │           │
    │ 1️⃣ RAG 검색 │←──────────┘
    │ 2️⃣ Ollama   │
    └──────┬─────┘
           │
           ▼
    ┌──────────────┐
    │ 알림 전송     │
    ├──┬───┬───┬──┤
    │Slack Web 콘솔│
    └──┬───┴──────┘
       │ (클릭)
       ▼
    Jira 작성 페이지
```

**주요 흐름:**
1. **로그 수집**: 로컬 파일, SSH 원격, Jira 이슈 (3가지 소스)
2. **클러스터링**: Drain3로 패턴 분류 (clustering_monitor.py)
3. **RAG 학습**: Jira 이슈 → 벡터 DB 저장 (rag_trainer.py)
4. **AI 분석**: 에러 3회 이상 시 → RAG 검색 + Ollama 분석
5. **알림**: Slack/웹/콘솔 → Jira 링크 포함

### 주요 디자인 패턴

**클러스터링 전략:**
- Drain3가 각 에러 로그를 처리하여 템플릿 패턴 추출
- 변수는 `<*>` 토큰으로 대체 (예: "User 123" → "User <*>")
- 클러스터는 고유 ID로 식별되며 발생 횟수 추적
- 임계값: 3회 이상 발생시 알림 트리거

**멀티라인 스택트레이스 처리:**
- 2초 타임아웃을 가진 버퍼 메커니즘
- 스택트레이스를 연결하고 요약
- 복잡한 트레이스를 위한 향상된 프로세서 (`stack_trace_processor.py`) 사용 가능

**쿨다운 시스템:**
- `last_alert_time` 딕셔너리로 클러스터별 마지막 알림 시간 추적
- 5분 쿨다운으로 알림 폭주 방지
- Slack 및 콘솔 알림 모두에 적용

**RAG-Ollama 통합 AI 분석 연동:** (v3.1 업데이트)
- 3회, 8회, 13회... 발생시 트리거 (최초 이후 5회마다)
- **2단계 분석 흐름**:
  1. RAG 검색: 유사한 과거 이슈 탐색 (Top-3)
  2. Ollama 분석: 과거 사례를 컨텍스트로 제공
- 클러스터 메타데이터에 캐시되어 중복 분석 방지
- 구조화된 JSON 출력, 실패시 텍스트 파싱으로 전환
- 180초 타임아웃, 상세한 디버깅 로깅 포함
- **추가 메타데이터**: `past_cases_referenced`, `rag_enhanced`, `similar_issues`

## 설정

### 환경변수 (.env)
```bash
# Slack 알림 설정
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Jira 연동 설정 (NEW!)
JIRA_URL=http://jira1.wips.co.kr
JIRA_PROJECT_KEY=YOUR_PROJECT_KEY
# Jira Cloud: API Token 사용
JIRA_EMAIL=your_email@company.com
JIRA_API_TOKEN=your_api_token
# Jira Server/Data Center: Basic Auth 사용 (또는)
JIRA_USERNAME=your_username
JIRA_PASSWORD=your_password

# RAG 시스템 (선택사항)
OPENAI_API_KEY=sk-...
```

### 주요 디렉토리
- `logs/` - 모니터링 대상 로그 디렉토리 (D:\devcon\logs)
- `log_reports/` - 생성된 HTML/JSON 리포트
- `docs/` - 기술 문서
- `confluence_docs/` - 추가 문서
- `models/` - RAG 학습 모델 저장소 (NEW!)
  - `bug_rag_model_YYYYMMDD_HHMMSS/`: 타임스탬프별 모델
    - `index.faiss`: FAISS 벡터 인덱스
    - `documents.pkl`: 문서 메타데이터
    - `metadata.pkl`: 모델 정보
- `templates/` - Flask HTML 템플릿 (자동 생성)
- `venv/` - 가상환경 (git 제외)
- `chroma_db/` - Chroma 벡터 스토어 (git 제외, 레거시)

### Drain3 설정
`clustering_monitor.py`의 `initialize_drain3()`에 위치:
```python
template_miner.drain.sim_th = 0.4      # 유사도 임계값
template_miner.drain.depth = 4         # 트리 깊이
template_miner.drain.max_children = 100 # 노드당 최대 자식 수
```

### RAG Trainer 설정
`rag_trainer.py`의 `RAGTrainer.__init__()`에서 설정:
```python
model_name = 'sentence-transformers/all-MiniLM-L6-v2'  # 임베딩 모델
dimension = 384  # 벡터 차원 (모델에 따라 자동 결정)
index_type = faiss.IndexFlatL2  # FAISS 인덱스 유형 (L2 거리)
```

## 개발 워크플로우

### 새로운 에러 감지 패턴 추가
1. `LogClusteringHandler.__init__()`의 `error_keywords` 리스트에 키워드 추가
2. `slack_integration.py`의 `_get_recommendations()`에 패턴별 권장사항 추가
3. `ollama_integration.py`의 `_get_fallback_analysis()`에 폴백 분석 추가

### RAG-Ollama 통합 AI 분석 확장 (v3.1)
1. **RAG 검색 로직 수정**:
   - `ollama_integration.py`의 `_search_similar_issues()`에서 유사도 임계값 조정
   - `top_k` 파라미터 변경 (기본 3개)

2. **프롬프트 커스터마이징**:
   - `_create_rag_enhanced_prompt()`에서 과거 사례 포맷 수정
   - 프롬프트에 추가 지침 삽입

3. **응답 구조 확장**:
   - `_parse_analysis_result()`에서 새로운 필드 추가
   - `past_cases_referenced`, `rag_enhanced`, `similar_issues` 처리

4. **RAG 모델 재로드**:
   ```python
   analyzer.reload_rag_model()  # 새로운 학습 후 호출
   ```

5. **디버깅 로그 레벨 조정**:
   - `logging.INFO` → `logging.DEBUG` (더 상세한 로그)
   - 프롬프트 전체 출력 토글

### 대시보드 기능 추가
1. `web_dashboard.py`의 `dashboard_data` 구조 업데이트
2. 새 API 엔드포인트를 위한 Flask 라우트 추가
3. 실시간 업데이트 필요시 SocketIO 이벤트 핸들러 추가
4. `create_templates()`에서 대시보드 HTML 템플릿 업데이트

### 로컬 리포트 생성
- `log_block_saver.py`가 처리 (사용 가능한 경우)
- `log_reports/`에 HTML + JSON으로 저장
- 포함 내용:
  - 예시를 포함한 에러 알림 상세정보
  - 상위 클러스터를 포함한 요약 리포트
  - 원시 로그 클러스터 데이터

### Jira 연동 사용법
**설정:**
1. `.env` 파일에 Jira 정보 설정:
   - `JIRA_URL`: Jira 서버 주소
   - `JIRA_PROJECT_KEY`: 이슈를 생성할 프로젝트 키
   - 인증 정보 (둘 중 하나):
     - Jira Cloud: `JIRA_EMAIL` + `JIRA_API_TOKEN`
     - Jira Server: `JIRA_USERNAME` + `JIRA_PASSWORD`

**사용 (Slack → Jira):**
- Slack 알림에서 📝 링크 클릭:
  - Jira 작성 페이지로 이동 (제목 자동 입력)
  - 사용자가 상세 내용 작성 후 제출
- API 방식으로 자동 생성 (코드에서 직접 호출):
  ```python
  jira = JiraIntegration()
  result = jira.create_issue(error_info)
  ```
- 생성되는 이슈 내용 (API 방식):
  - 제목: 에러 패턴 + 발생 횟수
  - 우선순위: 발생 횟수에 따라 자동 설정
  - 설명: 에러 상세 정보, AI 분석 결과, 원본 로그 예시
  - 라벨: log-monitoring, automated, cluster-ID

**사용 (Jira → RAG):**
- Jira 이슈 조회 및 RAG 학습:
  ```python
  jira = JiraIntegration()
  result = jira.fetch_bug_issues_for_rag(max_results=100)
  # 또는
  issues = jira.search_issues(jql="project = WATD AND issuetype = Bug")
  ```

**테스트:**
```bash
python jira_integration.py  # Jira 연결 및 샘플 이슈 생성 테스트
```

### RAG 학습 워크플로우 (NEW!)
**웹 대시보드에서 학습 (권장):**
1. `python main.py --mode dashboard` 실행
2. 브라우저에서 http://localhost:5000 접속
3. 왼쪽 메뉴 "🧠 RAG 학습" 클릭
4. Jira 프로젝트 키 입력 (예: WATD)
5. 학습할 이슈 개수 선택 (10~100)
6. "학습 시작" 버튼 클릭
7. 진행 상황 확인 및 결과 확인

**코드로 직접 학습:**
```python
from jira_integration import JiraIntegration
from rag_trainer import RAGTrainer

# 1. Jira 이슈 조회
jira = JiraIntegration()
result = jira.fetch_bug_issues_for_rag(max_results=100)

# 2. RAG 학습용 문서 변환
documents = []
for issue in result['issues']:
    doc = {
        'id': issue.key,
        'text': f"{issue.fields.summary}\n{issue.fields.description or ''}",
        'type': 'bug',
        'metadata': {'labels': issue.fields.labels}
    }
    documents.append(doc)

# 3. RAG Trainer 학습
trainer = RAGTrainer()
trainer.build_vector_database(documents)
trainer.save_model('models/bug_rag_model_20250101')

# 4. 유사 이슈 검색
results = trainer.search("NullPointerException at UserService", top_k=5)
```

**모델 재사용:**
```python
trainer = RAGTrainer()
trainer.load_model('models/bug_rag_model_20250101')
results = trainer.search("Database connection timeout", top_k=3)
```

### SSH 원격 모니터링 확장 (NEW!)
**웹 대시보드에서 설정:**
1. `python main.py --mode dashboard` 실행
2. 왼쪽 메뉴 "🔑 SSH 연결" 클릭
3. 접속 정보 입력 후 "연결" 버튼
4. 실시간 로그 스트리밍 확인

**SSH 로그 처리 흐름:**
```python
# web_dashboard.py의 SSH 스레드
ssh_client = paramiko.SSHClient()
ssh_client.connect(host, port, username, password)

# tail -f 명령으로 실시간 로그 수신
stdin, stdout, stderr = ssh_client.exec_command('tail -f /var/log/app.log')

# 로그 라인 읽기 및 SocketIO 전송
for line in stdout:
    socketio.emit('ssh_log', {'log': line})
    # 동일한 클러스터링 엔진 적용
    handler.process_log_line(line)
```

**보안 강화 (프로덕션):**
```python
# SSH 키 기반 인증
ssh_client.connect(
    host, port, username,
    key_filename='/path/to/private_key'
)
```

## 중요 사항

**버전 호환성:**
- Python 3.9+ 필요 (3.13 미만)
- 버전 호환성을 위한 다중 Drain3 초기화 방법 (`initialize_drain3()` 참조)
- 선택적 모듈 사용 불가시 우아한 성능 저하

**모듈 사용 가능성 체크:**
모든 메인 모듈에서 선택적 의존성 확인:
```python
try:
    from module_name import Feature
    FEATURE_AVAILABLE = True
except ImportError:
    FEATURE_AVAILABLE = False
```

**성능 고려사항:**
- 웹 대시보드는 메모리 증가 방지를 위해 maxlen이 있는 deque 사용
- 스택트레이스 버퍼는 10라인으로 제한
- 클러스터 예시는 클러스터당 3개로 제한
- 요약 리포트는 10분마다 생성 (매 이벤트마다 아님)
- SSH 로그는 최대 500개로 제한 (메모리 관리)
- RAG 벡터 검색은 Top-K 제한으로 성능 최적화

**RAG 시스템:**
- FAISS 인덱스는 메모리에 로드 (빠른 검색)
- 임베딩 모델은 첫 사용 시 자동 다운로드
- 모델 저장소: `~/.cache/huggingface/`
- L2 거리 기반 유사도 계산 (빠르고 정확)

**Ollama 연동:**
- Ollama 서버 실행 필요: `ollama serve`
- 모델 사전 설치 필요: `ollama pull llama3:8b-instruct-q4_K_M`
- 시작시 `_check_ollama_connection()`으로 연결 확인

**에러 키워드 범위:**
현재 키워드: ERROR, FATAL, Exception, Failed, Error:, Caused by:, at java., at org., ### Error, NullPointerException, SQLException, OutOfMemoryError

로그 형식에 따라 필요시 키워드 추가

## 일반적인 문제

**Drain3 초기화 실패:**
- 다중 초기화 방법 시도 (이미 구현됨)
- 업그레이드: `pip install drain3 --upgrade`
- 또는 특정 버전 사용: `pip install drain3==0.9.6`

**웹 대시보드 업데이트 안됨:**
- 브라우저 콘솔에서 WebSocket 연결 확인
- 모니터링 디렉토리에 로그가 작성되고 있는지 확인
- Flask/SocketIO 버전 확인

**Ollama 타임아웃:**
- `timeout` 매개변수 증가 (기본 180초)
- 더 작거나 빠른 모델 사용
- Ollama 서버 리소스 확인

**Slack 알림이 전송되지 않음:**
- .env 파일의 SLACK_WEBHOOK_URL 확인
- 연결 테스트: `python slack_integration.py`
- 쿨다운이 알림을 차단하지 않았는지 확인

## 테스트 전략

**단위 테스트:**
컴포넌트 검증을 위한 개별 테스트 스크립트 실행:
- `python slack_integration.py` - Slack 연결성
- `python ollama_integration.py` - AI 분석
- `python 1_basic_drain3_test.py` - 클러스터링 기본

**통합 테스트:**
1. 터미널 1: `python main.py --mode monitor`
2. 터미널 2: `python main.py --mode generate`
3. 콘솔 출력, Slack 메시지, 로컬 리포트 확인

**웹 대시보드 테스트:**
1. 터미널 1: `python main.py --mode dashboard`
2. 브라우저: http://localhost:5000
3. 터미널 3: `python main.py --mode generate`
4. 브라우저에서 실시간 업데이트 확인

## 시스템 확장

**새로운 알림 채널 추가:**
1. `slack_integration.py`와 유사한 새 모듈 생성
2. `clustering_monitor.py`의 선택적 import에 추가
3. `alert_frequent_error()` 메서드에서 호출

**커스텀 로그 프로세서:**
1. `FileSystemEventHandler` 서브클래스 구현
2. `on_modified()` 메서드 오버라이드
3. 기존 `LogClusteringHandler`와 통합하거나 독립 실행

**대체 AI 모델:**
- `ollama_integration.py` 생성자 매개변수 수정
- 다른 모델 기능에 맞게 프롬프트 조정
- 컨텍스트 길이 제한 고려

**RAG 시스템 확장:**
1. **다른 임베딩 모델 사용:**
   ```python
   # 다국어 모델
   trainer = RAGTrainer(model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')

   # 더 정확한 모델 (느림)
   trainer = RAGTrainer(model_name='sentence-transformers/all-mpnet-base-v2')
   ```

2. **FAISS 인덱스 유형 변경:**
   ```python
   # 현재: IndexFlatL2 (정확하지만 느림)
   # 대안: IndexIVFFlat (빠르지만 근사치)
   import faiss
   quantizer = faiss.IndexFlatL2(dimension)
   index = faiss.IndexIVFFlat(quantizer, dimension, 100)  # 100개 클러스터
   ```

3. **다양한 데이터 소스 통합:**
   - Confluence 문서 학습
   - GitHub 이슈 학습
   - Stack Overflow 답변 학습

**SSH 연결 확장:**
1. **다중 서버 모니터링:**
   ```python
   servers = [
       {'host': 'server1', 'log': '/var/log/app1.log'},
       {'host': 'server2', 'log': '/var/log/app2.log'}
   ]
   for server in servers:
       start_ssh_monitoring(server)
   ```

2. **SSH 키 기반 인증:**
   - `.env`에 `SSH_KEY_PATH` 추가
   - Paramiko로 키 파일 로드
   - 비밀번호 없이 안전한 연결

**데이터베이스 연동:**
다음을 위해 인메모리 저장소를 영구 DB로 교체:
- 장기 패턴 분석
- 히스토리 트렌드 분석
- 다중 인스턴스 조정
- RAG 벡터 DB를 PostgreSQL + pgvector로 전환
