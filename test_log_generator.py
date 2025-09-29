"""
테스트 로그 생성기 - 다양한 에러 패턴을 로컬 파일로 생성
SSH 연결 없이도 대시보드 기능을 테스트할 수 있습니다
"""

import os
import time
import random
from datetime import datetime
import threading
import argparse

# 로그 생성 설정
class LogGeneratorConfig:
    def __init__(self):
        self.log_file = "logs/test_app.log"
        self.ssh_log_file = "logs/ssh_test.log"  # SSH 로그 시뮬레이션
        self.error_rate = 0.3  # 30% 에러율
        self.generate_interval = 2.0  # 2초마다 생성
        self.burst_mode = False  # 버스트 모드
        self.running = True

# 다양한 로그 패턴들
LOG_PATTERNS = {
    # 정상 로그 패턴들
    "info": [
        "[INFO] User {user_id} logged in successfully from {ip_address}",
        "[INFO] Processing order {order_id} for customer {customer_id}",
        "[INFO] Database backup completed successfully at {timestamp}",
        "[INFO] Cache refreshed for region {region_code}",
        "[INFO] API request to {endpoint} completed in {response_time}ms",
        "[INFO] Email sent to {email} with template {template_id}",
        "[INFO] File {filename} uploaded successfully, size: {file_size}MB",
        "[INFO] Cron job {job_name} executed successfully",
        "[INFO] Session created for user {user_id}, expires at {expiry}",
        "[INFO] Payment processed: amount={amount}, method={payment_method}"
    ],

    # 에러 로그 패턴들 (클러스터링 테스트용)
    "error": [
        "[ERROR] NullPointerException in UserService.getProfile() at line {line_number}",
        "[ERROR] SQLException: Connection refused to database {db_host}:{db_port}",
        "[ERROR] OutOfMemoryError: Java heap space exceeded, current usage: {memory_usage}MB",
        "[ERROR] ConnectionTimeoutException: Failed to connect to {service_name} after {timeout}ms",
        "[ERROR] FileNotFoundException: Unable to read config file {config_file}",
        "[ERROR] AccessDeniedException: User {user_id} lacks permission for {resource}",
        "[ERROR] InvalidTokenException: JWT token expired for user {user_id}",
        "[ERROR] NetworkException: Connection lost to {external_service}",
        "[ERROR] ValidationException: Invalid email format: {email}",
        "[ERROR] CacheException: Redis server unavailable at {redis_host}",
        "[ERROR] ParseException: Malformed JSON in request body",
        "[ERROR] DiskSpaceException: Insufficient disk space, available: {available_space}GB",
        "[ERROR] LockTimeoutException: Unable to acquire lock for resource {resource_id}",
        "[ERROR] RateLimitException: API limit exceeded for client {client_id}",
        "[ERROR] EncryptionException: Failed to decrypt data for user {user_id}"
    ],

    # 경고 로그 패턴들
    "warning": [
        "[WARN] High memory usage detected: {memory_percentage}%",
        "[WARN] Slow query detected: {query_time}ms for query {query_id}",
        "[WARN] Failed login attempt from IP {ip_address} for user {username}",
        "[WARN] SSL certificate expires in {days_remaining} days",
        "[WARN] Queue size growing rapidly: {queue_size} items pending",
        "[WARN] Response time above threshold: {response_time}ms for {endpoint}",
        "[WARN] Disk usage high: {disk_percentage}% on volume {volume}",
        "[WARN] Connection pool nearly exhausted: {active_connections}/{max_connections}",
        "[WARN] Cache miss rate high: {cache_miss_rate}% for {cache_key}",
        "[WARN] Retry limit reached for external service {service_name}"
    ]
}

# 가상 데이터 생성기
class MockDataGenerator:
    def __init__(self):
        self.user_ids = [f"user_{i:04d}" for i in range(1, 1001)]
        self.ip_addresses = [f"192.168.{random.randint(1,255)}.{random.randint(1,255)}" for _ in range(100)]
        self.order_ids = [f"ORD-{random.randint(100000,999999)}" for _ in range(500)]
        self.endpoints = ["/api/users", "/api/orders", "/api/payments", "/api/products", "/api/reports"]
        self.service_names = ["UserService", "OrderService", "PaymentService", "NotificationService", "AuthService"]
        self.db_hosts = ["db-master-01", "db-slave-02", "redis-cache-01", "elasticsearch-01"]

    def get_random_data(self):
        return {
            "user_id": random.choice(self.user_ids),
            "ip_address": random.choice(self.ip_addresses),
            "order_id": random.choice(self.order_ids),
            "customer_id": f"CUST_{random.randint(1000,9999)}",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "region_code": random.choice(["US", "EU", "ASIA", "KR"]),
            "endpoint": random.choice(self.endpoints),
            "response_time": random.randint(50, 2000),
            "email": f"user{random.randint(1,999)}@example.com",
            "template_id": f"tmpl_{random.randint(100,999)}",
            "filename": f"upload_{random.randint(1,999)}.pdf",
            "file_size": round(random.uniform(0.1, 50.0), 1),
            "job_name": random.choice(["daily_backup", "cleanup_logs", "send_newsletter"]),
            "expiry": (datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
            "amount": f"${random.randint(10,1000)}",
            "payment_method": random.choice(["card", "paypal", "bank_transfer"]),
            "line_number": random.randint(45, 999),
            "db_host": random.choice(self.db_hosts),
            "db_port": random.choice([3306, 5432, 6379, 9200]),
            "memory_usage": random.randint(512, 8192),
            "service_name": random.choice(self.service_names),
            "timeout": random.randint(1000, 30000),
            "config_file": random.choice(["/etc/app/config.yml", "/opt/app/settings.ini"]),
            "resource": random.choice(["/admin/users", "/api/sensitive", "/reports/financial"]),
            "external_service": random.choice(["payment-gateway", "email-service", "sms-provider"]),
            "redis_host": "redis://cache-01:6379",
            "available_space": round(random.uniform(0.5, 10.0), 1),
            "resource_id": f"RES_{random.randint(1000,9999)}",
            "client_id": f"client_{random.randint(100,999)}",
            "memory_percentage": random.randint(70, 95),
            "query_time": random.randint(1000, 10000),
            "query_id": f"query_{random.randint(1000,9999)}",
            "username": random.choice(["admin", "guest", "test_user", "unknown"]),
            "days_remaining": random.randint(1, 30),
            "queue_size": random.randint(100, 10000),
            "disk_percentage": random.randint(80, 98),
            "volume": random.choice(["/data", "/logs", "/backup"]),
            "active_connections": random.randint(90, 100),
            "max_connections": 100,
            "cache_miss_rate": random.randint(15, 45),
            "cache_key": random.choice(["user_sessions", "product_catalog", "pricing_data"])
        }

class TestLogGenerator:
    def __init__(self, config):
        self.config = config
        self.data_generator = MockDataGenerator()
        self.total_logs = 0
        self.error_logs = 0

        # 로그 디렉토리 생성
        os.makedirs("logs", exist_ok=True)

        print("🎯 테스트 로그 생성기 초기화 완료")
        print(f"📁 로그 파일: {config.log_file}")
        print(f"🔑 SSH 로그 파일: {config.ssh_log_file}")
        print(f"⚠️ 에러율: {config.error_rate*100}%")
        print(f"⏱️ 생성 간격: {config.generate_interval}초")

    def generate_log_entry(self, log_type=None):
        """단일 로그 엔트리 생성"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        data = self.data_generator.get_random_data()

        if log_type is None:
            # 확률적으로 로그 타입 결정
            rand = random.random()
            if rand < self.config.error_rate:
                log_type = "error"
            elif rand < self.config.error_rate + 0.1:  # 10% 경고
                log_type = "warning"
            else:
                log_type = "info"

        # 패턴 선택 및 데이터 치환
        pattern = random.choice(LOG_PATTERNS[log_type])
        log_content = pattern.format(**data)

        # 최종 로그 형태
        log_entry = f"{timestamp} {log_content}"

        self.total_logs += 1
        if log_type == "error":
            self.error_logs += 1

        return log_entry, log_type

    def write_to_file(self, log_entry, file_path):
        """파일에 로그 쓰기"""
        try:
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(log_entry + '\n')
                f.flush()  # 즉시 디스크에 쓰기
        except Exception as e:
            print(f"❌ 파일 쓰기 오류: {e}")

    def generate_burst_logs(self, count=10):
        """버스트 모드: 한번에 많은 로그 생성"""
        print(f"💥 버스트 모드: {count}개 로그 생성 중...")

        for i in range(count):
            # 에러 로그 비율을 높임
            log_entry, log_type = self.generate_log_entry("error" if i < count//2 else None)

            self.write_to_file(log_entry, self.config.log_file)
            self.write_to_file(f"[SSH] {log_entry}", self.config.ssh_log_file)

            time.sleep(0.1)  # 0.1초 간격으로 빠르게 생성

        print(f"✅ 버스트 로그 {count}개 생성 완료")

    def generate_specific_error_pattern(self, pattern_type, count=5):
        """특정 에러 패턴 반복 생성 (클러스터링 테스트용)"""
        print(f"🎯 특정 패턴 생성: {pattern_type} x{count}")

        if pattern_type == "database":
            patterns = [p for p in LOG_PATTERNS["error"] if "SQL" in p or "database" in p]
        elif pattern_type == "memory":
            patterns = [p for p in LOG_PATTERNS["error"] if "Memory" in p or "heap" in p]
        elif pattern_type == "network":
            patterns = [p for p in LOG_PATTERNS["error"] if "Connection" in p or "Network" in p]
        else:
            patterns = LOG_PATTERNS["error"]

        selected_pattern = random.choice(patterns)

        for i in range(count):
            data = self.data_generator.get_random_data()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            log_content = selected_pattern.format(**data)
            log_entry = f"{timestamp} {log_content}"

            self.write_to_file(log_entry, self.config.log_file)
            self.write_to_file(f"[SSH] {log_entry}", self.config.ssh_log_file)

            time.sleep(0.5)

        print(f"✅ {pattern_type} 패턴 {count}개 생성 완료")

    def start_continuous_generation(self):
        """연속 로그 생성 시작"""
        print("🚀 연속 로그 생성 시작 (Ctrl+C로 중지)")
        print("-" * 50)

        try:
            while self.config.running:
                log_entry, log_type = self.generate_log_entry()

                # 일반 로그 파일에 쓰기
                self.write_to_file(log_entry, self.config.log_file)

                # SSH 로그 파일에도 쓰기 (SSH 연결 시뮬레이션)
                ssh_log_entry = f"[SSH] {log_entry}"
                self.write_to_file(ssh_log_entry, self.config.ssh_log_file)

                # 콘솔 출력
                color = "🔴" if log_type == "error" else "🟡" if log_type == "warning" else "🟢"
                print(f"{color} {log_entry}")

                # 통계 출력 (10개마다)
                if self.total_logs % 10 == 0:
                    error_rate = (self.error_logs / self.total_logs) * 100
                    print(f"📊 총 {self.total_logs}개 로그, 에러 {self.error_logs}개 ({error_rate:.1f}%)")

                # 버스트 모드 랜덤 실행 (5% 확률)
                if self.config.burst_mode and random.random() < 0.05:
                    self.generate_burst_logs(random.randint(5, 15))

                time.sleep(self.config.generate_interval)

        except KeyboardInterrupt:
            print("\n⏹️ 로그 생성 중지됨")
            self.config.running = False

        print(f"✅ 총 {self.total_logs}개 로그 생성 완료")

    def interactive_mode(self):
        """대화형 모드"""
        print("\n🎮 대화형 테스트 모드")
        print("=" * 40)

        while True:
            print("\n선택하세요:")
            print("1. 🚀 연속 로그 생성 시작")
            print("2. 💥 버스트 로그 생성")
            print("3. 🎯 특정 패턴 생성")
            print("4. 📊 통계 확인")
            print("5. 🗑️ 로그 파일 초기화")
            print("0. ❌ 종료")

            choice = input("\n입력: ").strip()

            if choice == "1":
                self.start_continuous_generation()
            elif choice == "2":
                count = input("생성할 로그 수 (기본 10): ").strip()
                count = int(count) if count.isdigit() else 10
                self.generate_burst_logs(count)
            elif choice == "3":
                print("패턴 유형:")
                print("1. database (DB 오류)")
                print("2. memory (메모리 오류)")
                print("3. network (네트워크 오류)")
                print("4. random (랜덤)")

                pattern_choice = input("선택: ").strip()
                pattern_map = {"1": "database", "2": "memory", "3": "network", "4": "random"}
                pattern_type = pattern_map.get(pattern_choice, "random")

                count = input("생성할 개수 (기본 5): ").strip()
                count = int(count) if count.isdigit() else 5

                self.generate_specific_error_pattern(pattern_type, count)
            elif choice == "4":
                self.show_statistics()
            elif choice == "5":
                self.clear_log_files()
            elif choice == "0":
                print("👋 테스트 로그 생성기 종료")
                break
            else:
                print("❌ 잘못된 선택입니다")

    def show_statistics(self):
        """통계 정보 표시"""
        print(f"\n📊 통계 정보")
        print("-" * 30)
        print(f"총 생성된 로그: {self.total_logs:,}개")
        print(f"에러 로그: {self.error_logs:,}개")
        if self.total_logs > 0:
            error_rate = (self.error_logs / self.total_logs) * 100
            print(f"에러율: {error_rate:.1f}%")

        # 파일 크기 확인
        try:
            main_size = os.path.getsize(self.config.log_file) / 1024  # KB
            ssh_size = os.path.getsize(self.config.ssh_log_file) / 1024  # KB
            print(f"메인 로그 파일: {main_size:.1f} KB")
            print(f"SSH 로그 파일: {ssh_size:.1f} KB")
        except FileNotFoundError:
            print("로그 파일이 아직 생성되지 않았습니다")

    def clear_log_files(self):
        """로그 파일 초기화"""
        confirm = input("🗑️ 로그 파일을 모두 삭제하시겠습니까? (y/N): ").strip().lower()

        if confirm == 'y':
            try:
                open(self.config.log_file, 'w').close()
                open(self.config.ssh_log_file, 'w').close()
                self.total_logs = 0
                self.error_logs = 0
                print("✅ 로그 파일 초기화 완료")
            except Exception as e:
                print(f"❌ 파일 초기화 실패: {e}")
        else:
            print("취소됨")

def main():
    parser = argparse.ArgumentParser(description="테스트 로그 생성기")
    parser.add_argument("--mode", choices=["auto", "interactive", "burst", "pattern"],
                        default="interactive", help="실행 모드")
    parser.add_argument("--error-rate", type=float, default=0.3,
                        help="에러 로그 비율 (0.0~1.0)")
    parser.add_argument("--interval", type=float, default=2.0,
                        help="로그 생성 간격 (초)")
    parser.add_argument("--burst", action="store_true",
                        help="버스트 모드 활성화")
    parser.add_argument("--pattern", choices=["database", "memory", "network", "random"],
                        help="특정 패턴 생성")
    parser.add_argument("--count", type=int, default=5,
                        help="패턴 생성 개수")

    args = parser.parse_args()

    # 설정 초기화
    config = LogGeneratorConfig()
    config.error_rate = args.error_rate
    config.generate_interval = args.interval
    config.burst_mode = args.burst

    # 생성기 초기화
    generator = TestLogGenerator(config)

    print("🎯 테스트 로그 생성기")
    print("=" * 50)
    print("📋 이 도구로 다음을 테스트할 수 있습니다:")
    print("   • SSH 연결 없이 로컬 로그 파일 모니터링")
    print("   • 다양한 에러 패턴 클러스터링")
    print("   • 실시간 대시보드 기능")
    print("   • 빈발 패턴 감지 알림")
    print("=" * 50)

    # 모드별 실행
    if args.mode == "auto":
        generator.start_continuous_generation()
    elif args.mode == "interactive":
        generator.interactive_mode()
    elif args.mode == "burst":
        generator.generate_burst_logs(args.count)
    elif args.mode == "pattern":
        generator.generate_specific_error_pattern(args.pattern, args.count)

if __name__ == "__main__":
    main()