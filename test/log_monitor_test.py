import paramiko
import datetime
import sys, os
import signal
import select

# 경로 가져오기
import importlib.util

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

module_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "2_clustering_monitor.py")
spec = importlib.util.spec_from_file_location("clustering_monitor", module_path)
clustering_monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clustering_monitor)

LogClusteringHandler = clustering_monitor.LogClusteringHandler

# 테스트할 서버 접속 정보
servers = [
    {
        "host": os.getenv("SERVER1_HOST"),
        "account": os.getenv("SERVER1_ACCOUNT"),
        "password": os.getenv("SERVER1_PASSWORD"),
    },
]

# 전역 플래그
stop_monitoring = False

def signal_handler(signum, frame):
    global stop_monitoring
    print("\n🛑 종료 신호 감지됨 (Ctrl+C)")
    stop_monitoring = True

def monitor_logs_via_ssh(server, handler):
    global stop_monitoring
    host = server["host"]
    user = server["account"]
    pwd = server["password"]

    print(f"🔗 {host} ({user}) 접속 시도...")

    client = None
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(host, username=user, password=pwd, timeout=5)

        today = datetime.datetime.now().strftime("%Y-%m-%d")
        log_file = f"catalina.{today}.out"
        log_path = f"/usr/local/tomcat/logs/{log_file}"

        stdin, stdout, stderr = client.exec_command(f"tail -f {log_path}")

        print("👁️ 로그 모니터링 시작 (Ctrl+C로 중단)")

        # 논블로킹 방식으로 로그 읽기
        while not stop_monitoring:
            try:
                # stdout이 준비되었는지 확인 (최대 1초 대기)
                ready, _, _ = select.select([stdout.channel], [], [], 1.0)

                if ready:
                    line = stdout.readline()
                    if line:
                        line = line.strip()
                        if line:
                            print("📡 새 로그:", line)
                            handler.handle_error_clustering(line)
                    else:
                        # EOF 도달하면 종료
                        break

            except KeyboardInterrupt:
                print("\n🛑 사용자 중단 (Ctrl+C)")
                break
            except Exception as e:
                print(f"❌ 로그 읽기 오류: {e}")
                break

    except KeyboardInterrupt:
        print("\n🛑 사용자 중단 (Ctrl+C)")
    except Exception as e:
        print(f"❌ 접속 실패: {e}")
    finally:
        if client:
            client.close()
            print("🔌 SSH 연결 종료")

def main():
    global stop_monitoring

    # SIGINT 신호 핸들러 등록 (Ctrl+C)
    signal.signal(signal.SIGINT, signal_handler)

    handler = LogClusteringHandler()
    for s in servers:
        if stop_monitoring:
            break
        monitor_logs_via_ssh(s, handler)

if __name__ == "__main__":
    main()