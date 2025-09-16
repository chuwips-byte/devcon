# Log Monitoring System

Drain3를 이용한 실시간 로그 클러스터링 및 모니터링 시스템

## 요구사항
- Python 3.9 이상 3.13 미만
- Git
### 파이썬 버전 확인
```bash
python --version  # 3.9 이상 필요
```

## 설치 방법

```bash
1. 저장소 클론
git clone https://github.com/chuwips-byte/devcon.git
cd log-monitoring-system

2. 자동 설정 실행
python setup.py

3. 가상환경 활성화
venv\Scripts\activate

4. 실행
python src/main.py

# 통합 실행 방법 (권장)
python main.py --mode test      # Drain3 학습
python main.py --mode monitor   # 실시간 모니터링
python main.py --mode generate  # 테스트 로그 생성(다른 터미널)

# 직접 실행 방법 (기존)
python 1_basic_drain3_test.py
python 2_clustering_monitor.py
python 3_log_generator.py
```

## 프로젝트 구조
```
log-monitoring-system/
├── venv/                           # 가상환경
├── 1_basic_drain3_test.py         # Drain3 학습용
├── 2_clustering_monitor.py        # 메인 모니터링  
├── 3_log_generator.py             # 로그 생성기
├── main.py                        # 통합 진입점
├── setup.py                       # 자동 설정
├── requirements.txt               # 패키지 목록
├── .env.example                   # 환경변수 예시
├── .gitignore                     # Git 제외 파일
├── README.md                      # 프로젝트 문서
└── logs/                          # 로그 디렉토리
```