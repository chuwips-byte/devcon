"""
파일명: 3_log_generator.py
목적: 테스트용 로그 자동 생성
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
    
    # 다양한 에러 패턴들
    error_patterns = [
        "ERROR NullPointerException at UserService.findById({user_id})",
        "ERROR Database connection failed - timeout after {seconds}s",
        "ERROR FileNotFoundException: config/{filename} not found", 
        "ERROR OutOfMemoryError: Java heap space exceeded {size}GB",
        "ERROR SQL Exception: Duplicate entry '{value}' for key '{key}'",
        "FATAL Unable to start server - Port {port} already in use",
        "ERROR Redis connection lost - attempt {attempt}",
        "ERROR Authentication failed for user {username}",
        "INFO User {user_id} logged in successfully",  # 정상 로그
        "DEBUG Processing request {request_id}",        # 정상 로그
    ]
    
    print(f"🎯 로그 생성 시작: {log_file}")
    print("🛑 Ctrl+C로 중단")
    
    try:
        while True:
            # 랜덤 패턴 선택
            pattern = random.choice(error_patterns)
            
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
            
            print(f"📝 생성: {full_log}")
            
            # 1-3초 랜덤 대기
            time.sleep(random.uniform(1, 3))
            
    except KeyboardInterrupt:
        print(f"\n✅ 로그 생성 중단됨")

if __name__ == "__main__":
    generate_test_logs()