"""
파일명: 3_log_generator.py
목적: 테스트용 로그 자동 생성 (Slack 알림 확인용 - 주기 조정)
사용법: python 3_log_generator.py
"""

import time
import random
import os
from datetime import datetime

def generate_test_logs():
    """테스트용 로그 자동 생성"""
    
    # 로그 파일 경로
    log_dir = r"D:\devcon\logs"
    log_file = os.path.join(log_dir, "app.log")
    
    # 디렉토리 생성
    os.makedirs(log_dir, exist_ok=True)
    
    # 다양한 에러 패턴들 (에러 비율을 높임)
    error_patterns = [
        "ERROR NullPointerException at UserService.findById({user_id})",
        "ERROR Database connection failed - timeout after {seconds}s",
        "ERROR FileNotFoundException: config/{filename} not found", 
        "ERROR OutOfMemoryError: Java heap space exceeded {size}GB",
        "ERROR SQL Exception: Duplicate entry '{value}' for key '{key}'",
        "FATAL Unable to start server - Port {port} already in use",
        "ERROR Redis connection lost - attempt {attempt}",
        "ERROR Authentication failed for user {username}",
        # 정상 로그 비율 낮춤
        "INFO User {user_id} logged in successfully",
        "DEBUG Processing request {request_id}",
    ]
    
    print(f"로그 생성 시작: {log_file}")
    print("Slack 알림 테스트용 - 느린 생성 주기")
    print("Ctrl+C로 중단")
    print("-" * 50)
    
    log_count = 0
    
    try:
        while True:
            # 랜덤 패턴 선택 (에러 패턴 우선)
            if random.random() < 0.8:  # 80% 확률로 에러 로그
                pattern = random.choice(error_patterns[:8])  # 에러 패턴만
            else:  # 20% 확률로 정상 로그
                pattern = random.choice(error_patterns[8:])  # 정상 로그만
            
            # 변수들을 실제 값으로 교체
            log_entry = pattern.format(
                user_id=random.randint(100, 999),
                seconds=random.randint(30, 120),
                filename=random.choice(['app.properties', 'db.config', 'redis.conf']),
                size=random.randint(2, 8),
                value=f"user{random.randint(100, 999)}",
                key=random.choice(['username', 'email', 'id']),
                port=random.choice([8080, 9090, 3000]),
                attempt=random.randint(1, 5),
                username=f"user{random.randint(100, 999)}",
                request_id=f"req_{random.randint(1000, 9999)}"
            )
            
            # 타임스탬프 추가
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            full_log = f"[{timestamp}] {log_entry}"
            
            # 파일에 쓰기
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(full_log + "\n")
                f.flush()  # 즉시 디스크에 쓰기
            
            log_count += 1
            log_type = "ERROR" if any(keyword in log_entry for keyword in ['ERROR', 'FATAL']) else "INFO"
            
            print(f"[{log_count:03d}] [{log_type}] {full_log}")
            
            # 로그 생성 주기 조정 (5-8초로 늘림)
            wait_time = random.uniform(5, 8)
            print(f"        다음 로그까지 {wait_time:.1f}초 대기...")
            time.sleep(wait_time)
            
    except KeyboardInterrupt:
        print(f"\n로그 생성 중단됨 (총 {log_count}개 생성)")

if __name__ == "__main__":
    generate_test_logs()