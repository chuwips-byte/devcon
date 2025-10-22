"""
파일명: main.py
목적: 통합 실행 진입점 - 모든 기능을 하나의 명령으로 실행
사용법:
  - python main.py --mode dashboard  # 통합 웹 대시보드 (메인)
  - python main.py --mode monitor    # 터미널 모니터링
  - python main.py --mode generate   # 테스트 로그 생성
  - python main.py --mode test       # Drain3 학습
"""

import argparse
import sys
import os

# Windows 콘솔 인코딩 설정
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

def main():
    parser = argparse.ArgumentParser(description='통합 로그 모니터링 시스템')
    parser.add_argument('--mode', choices=['dashboard', 'test', 'monitor', 'generate', 'jira', 'ssh', 'rag'],
                        required=True, help='실행 모드 선택')

    args = parser.parse_args()

    if args.mode == 'dashboard':
        # 메인 통합 대시보드 (web_dashboard.py) - 포트 5000
        print("🌐 통합 웹 대시보드를 시작합니다...")
        print("=" * 50)
        print("📱 브라우저에서 http://localhost:5000 접속하세요")
        print("🎛️ 왼쪽 메뉴: 로그 모니터링, RAG 학습, SSH 연결, 시스템 정보")
        print("=" * 50)
        try:
            import subprocess
            subprocess.run([sys.executable, 'web_dashboard.py'])
        except Exception as e:
            print(f"❌ 웹 대시보드 실행 실패: {e}")

    elif args.mode == 'test':
        # Drain3 학습 및 테스트
        print("🎓 Drain3 학습을 시작합니다...")
        try:
            import subprocess
            subprocess.run([sys.executable, '1_basic_drain3_test.py'])
        except Exception as e:
            print(f"❌ Drain3 테스트 실행 실패: {e}")

    elif args.mode == 'monitor':
        # 실시간 모니터링
        print("👀 실시간 로그 모니터링을 시작합니다...")
        try:
            import subprocess
            subprocess.run([sys.executable, 'clustering_monitor.py'])
        except Exception as e:
            print(f"❌ 클러스터링 모니터 실행 실패: {e}")

    elif args.mode == 'generate':
        # 테스트 로그 생성
        print("📝 테스트 로그 생성을 시작합니다...")
        try:
            import subprocess
            subprocess.run([sys.executable, '3_log_generator.py'])
        except Exception as e:
            print(f"❌ 로그 생성기 실행 실패: {e}")

    elif args.mode == 'jira':
        # JIRA 연동 직접 실행
        print("🎫 JIRA 연동을 실행합니다...")
        try:
            import subprocess
            subprocess.run([sys.executable, 'jira_integration.py'])
        except Exception as e:
            print(f"❌ JIRA 연동 실행 실패: {e}")

    elif args.mode == 'ssh':
        # SSH 테스트 직접 실행
        print("🔑 SSH 연결 테스트...")
        print("SSH 기능은 통합 대시보드에서 사용하세요: python main.py --mode dashboard")

    elif args.mode == 'rag':
        # RAG 학습 직접 실행
        print("🧠 RAG 학습...")
        print("RAG 학습은 통합 대시보드에서 사용하세요: python main.py --mode dashboard")

if __name__ == "__main__":
    main()