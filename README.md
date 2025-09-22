# Log Monitoring System

Drain3를 이용한 실시간 로그 클러스터링 및 모니터링 시스템

## 주요 기능

- **실시간 로그 모니터링**: Watchdog를 이용한 파일 변경 감지
- **지능형 클러스터링**: Drain3 알고리즘으로 에러 패턴 자동 분류
- **빈발 패턴 감지**: 반복되는 에러 패턴 자동 탐지 (3회 이상 발생시 알림)
- **Slack 연동**: 빈발 에러 패턴을 Slack 채널로 실시간 알림
- **웹 대시보드**: 브라우저에서 실시간 모니터링 및 시각화
- **패턴별 권장사항**: NPE, DB 연결, 메모리 부족 등 에러 유형별 맞춤 조치사항 제공

## 요구사항

- Python 3.9 이상 3.13 미만
- Git

### 파이썬 버전 확인
```bash
python --version  # 3.9 이상 필요
```

## 빠른 시작

### 1. 저장소 클론
```bash
git clone https://github.com/chuwips-byte/devcon.git
cd devcon
```

### 2. 자동 설정 실행
```bash
python setup.py
```

### 3. 가상환경 활성화
```bash
# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 4. 환경변수 설정 (선택사항)
```bash
# .env 파일에서 Slack Webhook URL 설정
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### 5. 실행
```bash
# 통합 실행 방법 (권장)
python main.py --mode test      # Drain3 개념 학습
python main.py --mode monitor   # 실시간 모니터링 시작
python main.py --mode generate  # 테스트 로그 생성 (다른 터미널에서)
python main.py --mode dashboard # 웹 대시보드 실행 (브라우저에서 모니터링)

# 직접 실행 방법 (개발/학습용)
python 1_basic_drain3_test.py   # Drain3 기본 학습
python 2_clustering_monitor.py  # 실시간 모니터링
python 3_log_generator.py       # 테스트 로그 생성
python web_dashboard.py         # 웹 대시보드 직접 실행
```

## 사용법

### 기본 학습 과정
1. **개념 학습**: `python main.py --mode test` 실행으로 Drain3 클러스터링 이해
2. **실시간 모니터링**: `python main.py --mode monitor` 실행
3. **로그 생성**: 다른 터미널에서 `python main.py --mode generate` 실행
4. **Slack 알림 확인**: 빈발 패턴 감지시 Slack 채널에서 알림 수신

### 웹 대시보드 사용법
1. **대시보드 실행**: `python main.py --mode dashboard` 실행
2. **브라우저 접속**: http://localhost:5000 접속
3. **로그 생성**: 다른 터미널에서 `python main.py --mode generate` 실행
4. **실시간 모니터링**: 브라우저에서 실시간으로 로그와 클러스터링 결과 확인

### 모니터링 결과 해석
- **클러스터 ID**: 각 에러 패턴의 고유 식별자
- **템플릿**: 변수 부분을 `<*>`로 치환한 일반화된 패턴
- **발생 횟수**: 해당 패턴으로 발생한 총 에러 수
- **심각도 수준**: 발생 횟수에 따른 자동 분류
  - 매우 심각 (50회 이상)
  - 심각 (20회 이상)
  - 주의 (10회 이상)
  - 경미 (10회 미만)

## 프로젝트 구조

```
log-monitoring-system/
├── venv/                           # 가상환경 (Git 제외)
├── 1_basic_drain3_test.py         # Drain3 학습 및 기본 테스트
├── 2_clustering_monitor.py        # 실시간 로그 모니터링 (메인 기능)
├── 3_log_generator.py             # 테스트용 로그 생성기
├── slack_integration.py           # Slack 알림 연동 모듈
├── web_dashboard.py               # 웹 대시보드 (Flask 기반)
├── main.py                        # 통합 실행 진입점
├── setup.py                       # 프로젝트 자동 설정 스크립트
├── requirements.txt               # Python 패키지 의존성
├── .env.example                   # 환경변수 설정 예시
├── .env                           # 실제 환경변수 (Git 제외)
├── .gitignore                     # Git 제외 파일 목록
├── README.md                      # 프로젝트 문서
└── logs/                          # 로그 파일 디렉토리
    └── app.log                    # 생성되는 테스트 로그 파일
```

## Slack 연동 설정

### 1. Slack Webhook URL 생성
1. Slack 워크스페이스에서 앱 관리 페이지 접속
2. "Incoming WebHooks" 검색 후 추가
3. 알림받을 채널 선택
4. 생성된 Webhook URL 복사

### 2. 환경변수 설정
```bash
# .env 파일에 추가
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
```

### 3. 연동 테스트
```bash
python slack_integration.py
```

## 개발자를 위한 가이드

### 새로운 개발자 온보딩
```bash
# 저장소 클론 후
python setup.py    # 자동 환경 구성
# 가상환경 활성화 후 바로 사용 가능
```

### 패키지 의존성 관리
```bash
# 새 패키지 추가 후
pip freeze > requirements.txt

# 다른 환경에서 설치
pip install -r requirements.txt
```

### 코드 구조
- **LogClusteringHandler**: Watchdog 이벤트 처리 및 Drain3 연동
- **SlackNotifier**: Slack Webhook 알림 전송
- **TemplateMiner**: Drain3 클러스터링 엔진

## 트러블슈팅

### 자주 발생하는 문제

**1. Slack 연동 실패**
```bash
# 환경변수 확인
echo $SLACK_WEBHOOK_URL  # Linux/Mac
echo %SLACK_WEBHOOK_URL%  # Windows

# 연동 테스트
python slack_integration.py
```

**2. 모듈 import 오류**
```bash
# 가상환경 활성화 확인
which python  # Linux/Mac
where python  # Windows

# 패키지 재설치
pip install -r requirements.txt
```

**3. 파일 권한 오류**
```bash
# logs 디렉토리 권한 확인
ls -la logs/  # Linux/Mac
# 또는 Windows 탐색기에서 속성 확인
```

## 기여하기

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 `LICENSE` 파일을 참조하세요.

## 관련 기술

- [Drain3](https://github.com/logpai/Drain3): 로그 클러스터링 알고리즘
- [Watchdog](https://github.com/gorakhargosh/watchdog): 파일 시스템 모니터링
- [Slack Webhooks](https://api.slack.com/messaging/webhooks): 메시지 알림

## 버전 히스토리

- **v1.0.0**: 기본 로그 모니터링 및 클러스터링
- **v1.1.0**: Slack 연동 추가
- **v1.2.0**: 패턴별 권장사항 제공