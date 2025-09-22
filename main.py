#!/usr/bin/env python3
"""
Log Monitoring System - Unified Entry Point
기존 스크립트들에 대한 통합 실행 진입점
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path

def run_script(script_name, description):
    """스크립트 실행"""
    print(f"🚀 {description} 시작")
    print("=" * 50)
    
    try:
        result = subprocess.run([sys.executable, script_name], check=True)
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"❌ 실행 실패: {e}")
        return e.returncode
    except KeyboardInterrupt:
        print("\n⏹️ 사용자에 의해 중단됨")
        return 1

def main():
    parser = argparse.ArgumentParser(
        description='Log Monitoring System - 실시간 로그 클러스터링 및 모니터링',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python main.py --mode test      # Drain3 개념 학습
  python main.py --mode monitor   # 실시간 모니터링 (메인 기능)
  python main.py --mode generate  # 테스트 로그 생성
  python main.py --mode dashboard # 웹 대시보드 실행
  
직접 실행 (기존 방식):
  python 1_basic_drain3_test.py
  python 2_clustering_monitor.py  
  python 3_log_generator.py
        """
    )
    
    parser.add_argument(
        '--mode', 
        choices=['test', 'monitor', 'generate', 'dashboard'], 
        default='monitor',
        help='실행 모드 선택 (기본: monitor)'
    )
    
    parser.add_argument(
        '--list', 
        action='store_true',
        help='사용 가능한 스크립트 목록 출력'
    )
    
    args = parser.parse_args()
    
    # 스크립트 정보
    scripts = {
        'test': {
            'file': '1_basic_drain3_test.py',
            'description': 'Drain3 기본 학습 및 테스트'
        },
        'monitor': {
            'file': '2_clustering_monitor.py', 
            'description': '실시간 로그 모니터링 (메인 기능)'
        },
        'generate': {
            'file': '3_log_generator.py',
            'description': '테스트용 로그 생성기'
        },
        'dashboard': {
            'file': 'web_dashboard.py',
            'description': '웹 대시보드 (브라우저에서 모니터링)'
        }
    }
    
    # 목록 출력
    if args.list:
        print("📋 사용 가능한 스크립트:")
        for mode, info in scripts.items():
            print(f"  {mode:8s} - {info['description']}")
            print(f"           ({info['file']})")
        return 0
    
    # 파일 존재 확인
    script_info = scripts[args.mode]
    script_file = script_info['file']
    
    if not os.path.exists(script_file):
        print(f"❌ 스크립트 파일이 없습니다: {script_file}")
        return 1
    
    # 스크립트 실행
    return run_script(script_file, script_info['description'])

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)