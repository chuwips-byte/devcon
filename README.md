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
- **실시간 로그 모니터링**: Watchdog를 이용한 파일 변경 감지
- **지능형 클러스터링**: Drain3 알고리즘으로 에러 패턴 자동 분류
- **AI 에러 분석**: Ollama 로컬 LLM을 통한 에러 근본 원인 분석
- **빈발 패턴 감지**: 반복되는 에러 패턴 자동 탐지 (3회 이상)
- **멀티라인 스택트레이스 처리**: 복잡한 Java 스택트레이스 자동 연결

### 🔔 알림 및 연동
- **Slack 연동**: 빈발 에러를 Slack 채널로 실시간 알림
  - 원본 로그 예시 포함
  - AI 분석 결과 자동 전송
  - 심각도별 색상 구분
  - 10분마다 요약 리포트 자동 전송
- **Jira 연동**: Slack 알림에서 클릭 한 번으로 Jira 이슈 생성
  - 에러 정보 자동 입력
  - 제안 제목 자동 생성
  - AI 분석 결과 포함

### 📊 시각화
- **웹 대시보드**: Flask + SocketIO 실시간 웹 인터페이스
  - 실시간 로그 스트림
  - 에러 통계 카드
  - 클러스터링 결과 시각화
  - Chart.js 타임라인

### 🤖 AI 분석
- **Ollama 연동**: 로컬 LLM을 통한 에러 분석
  - 에러 유형 자동 분류
  - 근본 원인 분석
  - 즉시 조치사항 제안
  - 장기적 해결방안 제공
  - 예방 팁 제공

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

### 3️⃣ 바로 체험하기

```bash
# 터미널 1: 모니터링 시작
python main.py --mode monitor

# 터미널 2: 테스트 로그 생성
python main.py --mode generate

# 콘솔에서 실시간으로 에러 감지 및 클러스터링 확인!
```

### 4️⃣ 웹 대시보드로 보기

```bash
# 터미널 1: 웹 대시보드 실행
python main.py --mode dashboard

# 브라우저에서 http://localhost:5000 접속

# 터미널 2: 테스트 로그 생성
python main.py --mode generate

# 브라우저에서 실시간 업데이트 확인!
```

## 📖 사용 방법

### 실행 모드

```bash
# 1. Drain3 기본 학습 (처음 사용하는 경우 추천)
python main.py --mode test

# 2. 실시간 모니터링 (메인 기능)
python main.py --mode monitor

# 3. 테스트 로그 생성 (다른 터미널에서)
python main.py --mode generate

# 4. 웹 대시보드 (브라우저 모니터링)
python main.py --mode dashboard

# 5. Ollama AI 분석기 테스트
python main.py --mode ollama-test
```

### 로그 모니터링 워크플로우

```
┌─────────────────┐
│  로그 파일 생성   │
│  (app.log)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Watchdog 감지   │
│ (파일 변경)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Drain3 처리      │
│ (패턴 추출)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 에러 3회 이상?   │
└────┬───────┬────┘
     │ YES   │ NO
     ▼       └──────> 계속 모니터링
┌─────────────────┐
│ RAG 문서 검색   │
│ (기술문서 기반)  │
└────┬───────┬────┘
     │ 성공  │ 실패/부적합
     │       ▼
     │  ┌──────────┐
     │  │ Ollama AI│
     │  │ 분석     │
     │  └────┬─────┘
     │       │
     └───────┤
             ▼
┌─────────────────┐
│ 통합 분석 결과   │
│ (근본원인 파악)  │
└────────┬────────┘
         │
         ├──────────┐
         ▼          ▼
    ┌────────┐  ┌────────┐
    │ Slack  │  │ 웹     │
    │ 알림   │  │ 대시보드│
    └────────┘  └────────┘
         │
         ▼
    ┌────────┐
    │ Jira   │
    │ 이슈생성│
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

### AI 분석 결과 예시

```json
{
  "error_type": "NullPointerException",
  "severity": "High",
  "root_cause": "사용자 ID가 null인 상태에서 조회 시도",
  "confidence": 85,
  "immediate_actions": [
    "널 체크 로직 추가",
    "Optional 패턴 사용 검토"
  ],
  "long_term_solutions": [
    "단위 테스트에서 널 케이스 추가",
    "코드 리뷰 프로세스 강화"
  ],
  "prevention_tips": [
    "IDE 널 체크 플러그인 사용",
    "정적 분석 도구 도입"
  ]
}
```

## 📁 프로젝트 구조

```
devcon/
├── 🐍 Python 스크립트
│   ├── main.py                      # 통합 실행 진입점
│   ├── setup.py                     # 프로젝트 자동 설정
│   ├── 1_basic_drain3_test.py       # Drain3 학습
│   ├── 2_clustering_monitor.py      # 메인 모니터링 (★)
│   ├── 3_log_generator.py           # 테스트 로그 생성
│   ├── web_dashboard.py             # Flask 웹 대시보드
│   ├── slack_integration.py         # Slack 알림 연동
│   ├── jira_integration.py          # Jira 이슈 생성
│   ├── ollama_integration.py        # Ollama AI 분석
│   └── list_jira_projects.py        # Jira 프로젝트 목록
│
├── 📄 설정 파일
│   ├── requirements.txt             # Python 의존성
│   ├── .env                         # 환경변수 (Git 제외)
│   ├── .env.example                 # 환경변수 예시
│   ├── .gitignore                   # Git 제외 목록
│   └── CLAUDE.md                    # 프로젝트 가이드
│
├── 📂 디렉토리
│   ├── logs/                        # 모니터링 대상 로그
│   ├── log_reports/                 # 생성된 리포트 (HTML/JSON)
│   ├── docs/                        # RAG용 기술 문서
│   ├── confluence_docs/             # Confluence 문서
│   ├── templates/                   # Flask HTML 템플릿
│   ├── venv/                        # 가상환경 (Git 제외)
│   └── rag_db/                      # Chroma 벡터 DB (Git 제외)
│
└── 📖 문서
    └── README.md                    # 이 파일
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

- **v2.0.0** (현재)
  - 🤖 Ollama AI 분석기 추가
  - 🎫 Jira 이슈 생성 연동
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
- [Slack Webhooks](https://api.slack.com/messaging/webhooks) - Slack 메시징
- [Flask](https://flask.palletsprojects.com/) - Python 웹 프레임워크
- [Jira REST API](https://developer.atlassian.com/server/jira/platform/rest-apis/) - Jira 연동

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## 👨‍💻 개발팀

개발 문의: [GitHub Issues](https://github.com/chuwips-byte/devcon/issues)

---

⭐ 이 프로젝트가 도움이 되었다면 Star를 눌러주세요!
