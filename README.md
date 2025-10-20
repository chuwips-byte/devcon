# 🚀 지능형 로그 모니터링 시스템

> Drain3 + AI 기반 실시간 로그 클러스터링 및 에러 분석 시스템

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## 📋 목차

- [주요 기능](#-주요-기능)
- [빠른 시작](#-빠른-시작)
- [사용 방법](#-사용-방법)
- [Slack/Jira 연동](#-slackjira-연동)
- [웹 대시보드](#-웹-대시보드)
- [프로젝트 구조](#-프로젝트-구조)
- [트러블슈팅](#-트러블슈팅)

## ✨ 주요 기능

### 🔍 핵심 기능
- **실시간 로그 모니터링**: Watchdog를 이용한 로컬/원격 파일 변경 감지
- **지능형 클러스터링**: Drain3 알고리즘으로 에러 패턴 자동 분류
- **AI 에러 분석**: Ollama 로컬 LLM을 통한 에러 근본 원인 분석
- **빈발 패턴 감지**: 반복되는 에러 패턴 자동 탐지 (3회 이상)
- **멀티라인 스택트레이스 처리**: 복잡한 Java 스택트레이스 자동 연결
- **RAG 기반 해결책 제공**: Jira 이슈 학습을 통한 유사 에러 해결책 자동 제안
- **원격 서버 모니터링**: SSH를 통한 원격 서버 로그 실시간 감시

### 🔔 알림 및 연동
- **Slack 연동**: 빈발 에러를 Slack 채널로 실시간 알림
  - 원본 로그 예시 포함 (최대 3개)
  - AI 분석 결과 자동 전송
  - 심각도별 색상 구분
  - 10분마다 요약 리포트 자동 전송
  - **Jira 이슈 생성 버튼** 포함
- **Jira 연동**: Slack에서 Jira 작성 페이지로 바로 이동
  - 📝 클릭 시 Jira 이슈 작성 페이지 오픈
  - 에러 패턴 기반 제안 제목 자동 생성
  - 사용자가 상세 내용 작성 후 제출

### 📊 시각화
- **웹 대시보드**: Flask + SocketIO 실시간 웹 인터페이스
  - 실시간 로그 스트림
  - 에러 통계 카드
  - 클러스터링 결과 시각화
  - Chart.js 타임라인

### 🤖 AI 분석 (NEW: RAG-Ollama 통합!)
- **RAG 통합 Ollama 분석기**: 과거 이슈 + AI 분석 결합
  - **1단계**: RAG로 유사한 과거 이슈 검색 (Top-3)
  - **2단계**: 과거 사례를 Ollama에 컨텍스트로 제공
  - **결과**: 과거 해결 방법 기반 + AI 분석 통합 답변
  - 에러 유형 자동 분류
  - 근본 원인 분석 (과거 사례 참고)
  - 즉시 조치사항 제안 (검증된 방법 우선)
  - 장기적 해결방안 제공
  - 예방 팁 제공
  - 과거 참조 사례 수 표시 (`past_cases_referenced`)

- **RAG Trainer**: 과거 이슈 학습 시스템
  - Jira 이슈 자동 수집 및 임베딩
  - FAISS 벡터 검색으로 유사 이슈 탐색
  - Sentence Transformers 기반 유사도 분석
  - 학습 모델 자동 로드 (가장 최근 모델)

### 🔌 원격 연동
- **SSH 연결**: 원격 서버 모니터링
  - 웹 대시보드에서 SSH 접속
  - 실시간 원격 로그 스트리밍
  - 원격 서버 에러 자동 감지 및 분석

## 🚀 빠른 시작

### 1️⃣ 사전 요구사항

- **Python 3.9 이상 3.13 미만**
- Git

```bash
# Python 버전 확인
python --version  # 3.9 이상 필요
```

### 2️⃣ 설치

```bash
# 1. 저장소 클론
git clone https://github.com/chuwips-byte/devcon.git
cd devcon

# 2. 자동 설정 실행 (가상환경 생성, 의존성 설치, .env 생성)
python setup.py

# 3. 가상환경 활성화
# Windows:
venv\Scripts\activate

# Linux/Mac:
source venv/bin/activate
```

### 3️⃣ 통합 대시보드로 시작하기 (권장)

```bash
# 통합 웹 대시보드 실행
python main.py --mode dashboard

# 브라우저에서 http://localhost:5000 접속
# 왼쪽 메뉴에서 다음 기능 사용:
#  📊 로그 모니터링 - 실시간 로그 분석
#  🧠 RAG 학습 - Jira 이슈 학습
#  🔑 SSH 연결 - 원격 서버 모니터링
#  💻 시스템 정보 - 서버 상태 확인
```

### 4️⃣ 또는 터미널에서 바로 체험하기

```bash
# 터미널 1: 모니터링 시작
python main.py --mode monitor

# 터미널 2: 테스트 로그 생성
python main.py --mode generate

# 콘솔에서 실시간으로 에러 감지 및 클러스터링 확인!
```

## 📖 사용 방법

### 실행 모드

```bash
# 1. 통합 웹 대시보드 (권장 - 모든 기능 사용 가능)
python main.py --mode dashboard

# 2. 실시간 모니터링 (터미널 모드)
python main.py --mode monitor

# 3. 테스트 로그 생성 (다른 터미널에서)
python main.py --mode generate

# 4. Drain3 기본 학습 (처음 사용하는 경우)
python main.py --mode test

# 5. RAG 학습 (대시보드에서 사용 권장)
python main.py --mode rag

# 6. SSH 연결 테스트 (대시보드에서 사용 권장)
python main.py --mode ssh

# 7. Jira 연동 테스트
python main.py --mode jira
```

### 로그 모니터링 워크플로우

```
┌─────────────────────────────────────────────────┐
│          로그 소스 (다중 입력)                    │
├─────────────┬─────────────┬─────────────────────┤
│ 로컬 파일    │  SSH 원격    │  Jira 이슈 (학습용) │
│ (app.log)   │  서버 로그   │                     │
└──────┬──────┴──────┬──────┴─────────┬───────────┘
       │             │                │
       ▼             ▼                ▼
┌────────────┐ ┌────────────┐ ┌────────────────┐
│  Watchdog  │ │ SSH 스트림  │ │  RAG Trainer   │
│  파일감지   │ │  실시간    │ │  Jira API 수집 │
└──────┬─────┘ └──────┬─────┘ └────────┬───────┘
       │              │                 │
       └──────┬───────┘                 │
              ▼                         ▼
       ┌────────────┐           ┌──────────────┐
       │  Drain3    │           │ FAISS 벡터DB │
       │ 클러스터링  │           │ (임베딩 저장) │
       └──────┬─────┘           └──────────────┘
              │
              ▼
       ┌────────────┐
       │ 에러 3회↑?  │
       └──┬─────┬───┘
          │YES  │NO → 계속 모니터링
          ▼
    ┌──────────────────┐
    │  2단계 AI 분석    │
    ├──────────────────┤
    │ 1️⃣ RAG 검색      │
    │   유사 이슈 탐색  │
    │ 2️⃣ Ollama 분석   │
    │   근본원인 파악   │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────────────┐
    │  통합 결과 전송           │
    ├────┬────┬─────┬──────────┤
    │Slack   │웹    │ 콘솔      │
    │알림    │대시  │ 출력      │
    └────┬───┴─보드─┴──────────┘
         │
         ▼ (클릭)
    ┌────────┐
    │ Jira   │
    │ 작성페이│
    │ 지 오픈 │
    └────────┘
```

### 에러 심각도 분류

| 발생 횟수 | 심각도 | 색상 | 알림 |
|----------|--------|------|------|
| 50회 이상 | 🔴 매우 심각 | 빨강 | 즉시 |
| 20~49회 | 🟠 심각 | 주황 | 즉시 |
| 10~19회 | 🟡 주의 | 노랑 | 즉시 |
| 3~9회 | 🟢 경미 | 초록 | 즉시 |

## 🔗 Slack/Jira 연동

### Slack 설정

#### 1. Slack Webhook URL 생성

1. Slack 워크스페이스 → **앱 관리**
2. **Incoming WebHooks** 검색 후 추가
3. 알림받을 **채널 선택**
4. 생성된 **Webhook URL 복사**

#### 2. 환경변수 설정

```bash
# .env 파일 수정
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

#### 3. 연동 테스트

```bash
python slack_integration.py
```

### Jira 설정

#### 1. 환경변수 설정

```bash
# .env 파일 수정

# Jira 서버 정보
JIRA_URL=http://jira.yourcompany.com
JIRA_PROJECT_KEY=WATD  # 프로젝트 키

# 인증 방식 1: Jira Server (기본 인증)
JIRA_USERNAME=your_username
JIRA_PASSWORD=your_password

# 인증 방식 2: Jira Cloud (API 토큰)
JIRA_EMAIL=your_email@company.com
JIRA_API_TOKEN=your_api_token
```

#### 2. 프로젝트 키 확인

```bash
# 사용 가능한 Jira 프로젝트 목록 확인
python list_jira_projects.py
```

#### 3. 연동 테스트

```bash
python jira_integration.py
```

### Slack 알림 기능

#### 에러 알림 (3회, 8회, 13회... 발생 시)
- 📊 에러 패턴
- 🔢 발생 횟수
- 🏷️ 클러스터 ID
- 🚦 심각도
- 🤖 AI 분석 결과 (에러 유형, 근본 원인, 신뢰도)
- ⚡ 즉시 조치사항
- 🔧 장기적 해결방안
- 🛡️ 예방 방법
- 📝 원본 로그 예시 (최대 3개)
- 🎫 **Jira 이슈 생성 링크** (클릭 한 번으로 이슈 생성!)

#### 요약 리포트 (10분마다 자동 전송)
- 📋 총 로그 수
- 🚨 에러 로그 수
- 🏷️ 클러스터링된 로그 수
- 📊 클러스터 수
- 📈 에러율
- 🎯 클러스터링율
- 🚦 심각도별 분포
- 🏆 TOP 5 에러 패턴
- 🖥️ **웹 대시보드 링크** (클릭하면 대시보드로 이동!)

## 🖥️ 웹 대시보드

### 기능

- **실시간 통계 카드**: 총 로그, 에러, 에러율, 패턴 수
- **실시간 로그 스트림**: 최근 100개 로그 실시간 표시
- **에러 패턴 클러스터**: AI 분석 결과 포함
- **타임라인 차트**: Chart.js 기반 시각화

### 실행

```bash
# 대시보드 실행
python main.py --mode dashboard

# 브라우저에서 접속
http://localhost:5000
```

### 포트 변경

```bash
# .env 파일에서 포트 변경
DASHBOARD_URL=http://localhost:8080
```

## 🧠 RAG 학습 시스템

### RAG란?
**RAG (Retrieval-Augmented Generation)**는 과거 Jira 이슈를 학습하여 유사한 에러가 발생했을 때 과거 해결 방법을 자동으로 제안하는 시스템입니다.

### 학습 방법

#### 1. 웹 대시보드에서 학습 (권장)
```bash
# 1. 대시보드 실행
python main.py --mode dashboard

# 2. 브라우저에서 http://localhost:5000 접속
# 3. 왼쪽 메뉴에서 "🧠 RAG 학습" 클릭
# 4. Jira 프로젝트 키 입력 (예: WATD)
# 5. 학습할 이슈 개수 선택
# 6. "학습 시작" 버튼 클릭
```

#### 2. 직접 테스트
```bash
# RAG Trainer 직접 실행
python rag_trainer.py
```

### 필수 라이브러리
```bash
# RAG 시스템 의존성 설치
pip install sentence-transformers faiss-cpu
```

### RAG 동작 원리
1. **Jira 이슈 수집**: Jira API를 통해 Bug 이슈 조회
2. **임베딩 생성**: Sentence Transformers로 이슈 내용을 벡터로 변환
3. **FAISS 인덱싱**: 벡터를 FAISS 데이터베이스에 저장
4. **유사도 검색**: 새로운 에러 발생 시 유사한 과거 이슈 탐색
5. **해결책 제안**: 과거 처리 방법을 자동으로 제안

### 학습 데이터 구조
```
models/
└── bug_rag_model_YYYYMMDD_HHMMSS/
    ├── index.faiss         # FAISS 벡터 인덱스
    ├── documents.pkl       # 문서 메타데이터
    └── metadata.pkl        # 모델 정보
```

## 🔑 SSH 원격 서버 모니터링

### 설정 방법

#### 1. 웹 대시보드에서 연결
```bash
# 1. 대시보드 실행
python main.py --mode dashboard

# 2. 브라우저에서 http://localhost:5000 접속
# 3. 왼쪽 메뉴에서 "🔑 SSH 연결" 클릭
# 4. SSH 접속 정보 입력:
#    - Host: 원격 서버 주소
#    - Port: SSH 포트 (기본 22)
#    - Username: 사용자명
#    - Password: 비밀번호
#    - 로그 파일 경로: 모니터링할 로그 파일
# 5. "연결" 버튼 클릭
```

### 기능
- **실시간 로그 스트리밍**: 원격 서버의 로그를 실시간으로 웹에 표시
- **자동 에러 감지**: SSH로 받은 로그도 Drain3 클러스터링 적용
- **AI 분석 연동**: 원격 서버 에러도 자동으로 AI 분석

### 보안 주의사항
- SSH 연결 정보는 세션에만 저장되며 파일로 저장되지 않습니다
- 프로덕션 환경에서는 SSH 키 기반 인증 사용을 권장합니다

## 🤖 Ollama AI 분석

### 설치 및 설정

#### 1. Ollama 설치

```bash
# Windows: https://ollama.ai 에서 다운로드

# Linux:
curl -fsSL https://ollama.ai/install.sh | sh

# Mac:
brew install ollama
```

#### 2. 모델 다운로드

```bash
# 권장 모델 (8GB RAM)
ollama pull llama3:8b-instruct-q4_K_M

# 또는 더 작은 모델 (4GB RAM)
ollama pull llama3:8b-instruct-q4_0
```

#### 3. Ollama 서버 실행

```bash
ollama serve
```

#### 4. 연동 테스트

```bash
python main.py --mode ollama-test
```

### RAG 통합 AI 분석 결과 예시 (NEW!)

```json
{
  "error_type": "NullPointerException",
  "severity": "High",
  "root_cause": "사용자 ID가 null인 상태에서 조회 시도 (유사 사례 참고)",
  "confidence": 95,
  "immediate_actions": [
    "널 체크 로직 추가 (과거 사례 기반)",
    "Optional 패턴 사용 검토"
  ],
  "long_term_solutions": [
    "단위 테스트에서 널 케이스 추가 (과거 사례에서 학습)",
    "코드 리뷰 프로세스 강화"
  ],
  "prevention_tips": [
    "IDE 널 체크 플러그인 사용",
    "정적 분석 도구 도입"
  ],
  "past_cases_referenced": 3,
  "rag_enhanced": true,
  "similar_issues": [
    {
      "issue_id": "WATD-1234",
      "similarity": 0.87,
      "rank": 1
    },
    {
      "issue_id": "WATD-5678",
      "similarity": 0.82,
      "rank": 2
    }
  ]
}
```

**RAG 통합의 장점:**
- ✅ **더 높은 신뢰도**: 과거 검증된 해결 방법 기반 (85% → 95%)
- ✅ **구체적인 조치**: 실제로 효과 있었던 방법 우선 제안
- ✅ **학습 효과**: 조직의 지식이 쌓일수록 더 정확해짐
- ✅ **추적 가능**: 어떤 과거 사례를 참고했는지 명시

## 📁 프로젝트 구조

```
devcon/
├── 🐍 Python 스크립트
│   ├── main.py                      # 통합 실행 진입점 (★ 시작점)
│   ├── setup.py                     # 프로젝트 자동 설정
│   ├── 1_basic_drain3_test.py       # Drain3 학습
│   ├── clustering_monitor.py        # 메인 모니터링 (★)
│   ├── 3_log_generator.py           # 테스트 로그 생성
│   ├── web_dashboard.py             # 통합 웹 대시보드 (★)
│   ├── slack_integration.py         # Slack 알림 연동
│   ├── jira_integration.py          # Jira 이슈 생성/조회
│   ├── ollama_integration.py        # RAG 통합 Ollama AI 분석 (★ 업그레이드!)
│   ├── rag_trainer.py               # RAG 학습 모듈
│   └── list_jira_projects.py        # Jira 프로젝트 목록
│
├── 📄 설정 파일
│   ├── requirements.txt             # Python 의존성
│   ├── .env                         # 환경변수 (Git 제외)
│   ├── .env.example                 # 환경변수 예시
│   ├── .gitignore                   # Git 제외 목록
│   ├── CLAUDE.md                    # 개발자 가이드
│   └── README.md                    # 이 파일 (사용자 가이드)
│
├── 📂 디렉토리
│   ├── logs/                        # 모니터링 대상 로그
│   ├── log_reports/                 # 생성된 리포트 (HTML/JSON)
│   ├── docs/                        # 기술 문서
│   ├── confluence_docs/             # Confluence 문서
│   ├── templates/                   # Flask HTML 템플릿 (자동 생성)
│   ├── models/                      # RAG 학습 모델 저장 (NEW!)
│   ├── venv/                        # 가상환경 (Git 제외)
│   └── chroma_db/                   # Chroma 벡터 DB (Git 제외)
│
└── 📖 문서
    ├── README.md                    # 사용자 가이드 (이 파일)
    ├── CLAUDE.md                    # 개발자 가이드
    └── DASHBOARD_GUIDE.md           # 대시보드 가이드
```

## 🔧 트러블슈팅

### ❌ 자주 발생하는 문제

#### 1. Slack 연동 실패

```bash
# 환경변수 확인
# Windows:
echo %SLACK_WEBHOOK_URL%

# Linux/Mac:
echo $SLACK_WEBHOOK_URL

# 연동 테스트
python slack_integration.py
```

**해결방법:**
- `.env` 파일에 `SLACK_WEBHOOK_URL`이 올바르게 설정되어 있는지 확인
- Webhook URL이 유효한지 확인 (Slack 앱 관리 페이지에서)

#### 2. 모듈 import 오류

```bash
ModuleNotFoundError: No module named 'xxx'
```

**해결방법:**
```bash
# 가상환경 활성화 확인
# Windows:
where python

# Linux/Mac:
which python

# 패키지 재설치
pip install -r requirements.txt
```

#### 3. Drain3 초기화 실패

```bash
AttributeError: 'TemplateMiner' object has no attribute 'xxx'
```

**해결방법:**
```bash
# Drain3 업그레이드
pip install drain3 --upgrade

# 또는 특정 버전 설치
pip install drain3==0.9.6
```

#### 4. Ollama 연결 실패

```bash
❌ Ollama 서버에 연결할 수 없습니다
```

**해결방법:**
```bash
# 1. Ollama 서버 실행 확인
ollama serve

# 2. 모델 다운로드 확인
ollama list

# 3. 모델 다운로드 (없는 경우)
ollama pull llama3:8b-instruct-q4_K_M
```

#### 5. 웹 대시보드 접속 불가

```bash
This site can't be reached
```

**해결방법:**
```bash
# 1. Flask 설치 확인
pip install flask flask-socketio python-socketio

# 2. 포트 충돌 확인 (다른 프로그램이 5000 포트 사용 중인지)
# Windows:
netstat -ano | findstr :5000

# Linux/Mac:
lsof -i :5000

# 3. 다른 포트 사용
# .env 파일 수정:
DASHBOARD_URL=http://localhost:8080
```

#### 6. 파일 권한 오류

```bash
PermissionError: [Errno 13] Permission denied: 'logs/app.log'
```

**해결방법:**
```bash
# logs 디렉토리 권한 확인 및 수정
# Windows: 탐색기에서 속성 → 보안 → 편집

# Linux/Mac:
chmod -R 755 logs/
```

### 💡 추가 도움말

- **디버그 모드**: 코드에서 `logging.DEBUG` 레벨 설정
- **로그 확인**: `logs/` 디렉토리의 로그 파일 확인
- **이슈 제보**: [GitHub Issues](https://github.com/chuwips-byte/devcon/issues)

## 🎓 학습 가이드

### 초심자를 위한 학습 순서

1. **Drain3 이해하기**
   ```bash
   python main.py --mode test
   ```
   - 로그 클러스터링 개념 학습
   - 템플릿 패턴 확인

2. **실시간 모니터링 체험**
   ```bash
   # 터미널 1
   python main.py --mode monitor

   # 터미널 2
   python main.py --mode generate
   ```
   - 실시간 에러 감지 확인
   - 클러스터링 결과 관찰

3. **Slack 연동 설정**
   - Webhook URL 생성
   - `.env` 파일 설정
   - 알림 테스트

4. **웹 대시보드 활용**
   ```bash
   python main.py --mode dashboard
   ```
   - 브라우저에서 시각화 확인

5. **AI 분석 활용**
   - Ollama 설치
   - AI 분석 결과 확인

## 🤝 기여하기

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 버전 히스토리

- **v3.1.0** (현재) - RAG-Ollama 통합
  - 🚀 **RAG + Ollama 완전 통합** (가장 중요!)
    - 과거 이슈를 Ollama 컨텍스트로 자동 제공
    - 2단계 분석: RAG 검색 → Ollama 분석
    - `past_cases_referenced` 추적
    - 상세한 디버깅 로그 추가
  - 📊 유사 이슈 검색 결과 표시
  - 🎯 신뢰도 향상 (검증된 해결책 기반)

- **v3.0.0**
  - 🧠 **RAG 학습 시스템** 추가 (Jira 이슈 기반 해결책 제안)
  - 🔑 **SSH 원격 서버 모니터링** 추가
  - 🖥️ **통합 웹 대시보드** 강화 (왼쪽 메뉴 시스템)
  - 📊 FAISS 벡터 검색 엔진 도입
  - 🎯 Sentence Transformers 기반 임베딩

- **v2.0.0**
  - 🤖 Ollama AI 분석기 추가
  - 🎫 Jira 이슈 생성 연동 (웹 링크 방식)
  - 🖥️ 웹 대시보드 링크 추가
  - 🎨 콘솔/Slack 출력 시각적 개선
  - 📊 요약 리포트 기능 강화

- **v1.2.0**
  - 패턴별 권장사항 제공
  - 로그 블록 저장 기능

- **v1.1.0**
  - Slack 연동 추가
  - 웹 대시보드 추가

- **v1.0.0**
  - 기본 로그 모니터링 및 클러스터링

## 📚 관련 기술 문서

- [Drain3](https://github.com/logpai/Drain3) - 로그 클러스터링 알고리즘
- [Watchdog](https://github.com/gorakhargosh/watchdog) - 파일 시스템 모니터링
- [Ollama](https://ollama.ai) - 로컬 LLM 실행
- [FAISS](https://github.com/facebookresearch/faiss) - 벡터 유사도 검색
- [Sentence Transformers](https://www.sbert.net/) - 문장 임베딩 모델
- [Paramiko](http://www.paramiko.org/) - Python SSH 라이브러리
- [Slack Webhooks](https://api.slack.com/messaging/webhooks) - Slack 메시징
- [Flask](https://flask.palletsprojects.com/) - Python 웹 프레임워크
- [Jira REST API](https://developer.atlassian.com/server/jira/platform/rest-apis/) - Jira 연동

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## 👨‍💻 개발팀

개발 문의: [GitHub Issues](https://github.com/chuwips-byte/devcon/issues)

---

⭐ 이 프로젝트가 도움이 되었다면 Star를 눌러주세요!
