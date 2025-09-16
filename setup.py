#!/usr/bin/env python3
import subprocess
import sys
import os
from pathlib import Path

def check_python_version():
    """파이썬 버전 확인"""
    required_version = (3, 9)
    current_version = sys.version_info[:2]
    
    if current_version < required_version:
        print(f"Python {required_version[0]}.{required_version[1]} 이상이 필요합니다.")
        print(f"현재 버전: {current_version[0]}.{current_version[1]}")
        sys.exit(1)
    
    print(f"Python 버전 확인 완료: {current_version[0]}.{current_version[1]}")

def setup_project():
    """프로젝트 초기 설정"""
    
    # 파이썬 버전 확인
    check_python_version()
    
    # 가상환경 확인
    if not os.path.exists('venv'):
        print("가상환경 생성 중...")
        subprocess.run([sys.executable, '-m', 'venv', 'venv'])
    
    # 가상환경 내 파이썬 경로
    if os.name == 'nt':  # Windows
        python_path = 'venv\\Scripts\\python'
        pip_path = 'venv\\Scripts\\pip'
    else:  # Linux/Mac
        python_path = 'venv/bin/python'
        pip_path = 'venv/bin/pip'
    
    # pip 업그레이드
    print("pip 업그레이드 중...")
    subprocess.run([python_path, '-m', 'pip', 'install', '--upgrade', 'pip'])
    
    # 패키지 설치
    print("패키지 설치 중...")
    subprocess.run([pip_path, 'install', '-r', 'requirements.txt'])
    
    # .env 파일 생성
    if not os.path.exists('.env'):
        print(".env 파일 생성 중...")
        if os.path.exists('.env.example'):
            with open('.env.example', 'r') as src, open('.env', 'w') as dst:
                dst.write(src.read())
    
    print("설정 완료!")
    print(f"가상환경 활성화: {'venv\\Scripts\\activate' if os.name == 'nt' else 'source venv/bin/activate'}")
    print("실행: python src/main.py")

if __name__ == "__main__":
    setup_project()