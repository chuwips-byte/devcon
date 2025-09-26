import os
import requests
from bs4 import BeautifulSoup
import paramiko
from dotenv import load_dotenv

# 환경변수 (Confluence 계정)
load_dotenv()
CONFLUENCE_URL = os.getenv("CONFLUENCE_URL")
CONFLUENCE_USER = os.getenv("CONFLUENCE_USER")
CONFLUENCE_TOKEN = os.getenv("CONFLUENCE_TOKEN")
PAGE_ID = os.getenv("CONFLUENCE_PAGE_ID")  # 계정 테이블이 있는 페이지 ID

def fetch_table_from_confluence():
    url = f"{CONFLUENCE_URL}/pages/viewpage.action?pageId={PAGE_ID}"
    res = requests.get(url, auth=(CONFLUENCE_USER, CONFLUENCE_TOKEN))  
    res.raise_for_status()
    html = res.text
    return html

def parse_servers(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.find_all("tr")
    servers = []

    for row in rows:
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cols) < 4:
            continue

        host, account, password, method = cols[:4]

        # strike-through 체크 (취소선 있으면 skip)
        if row.find("s") or row.find("span", style=lambda v: v and "line-through" in v):
            continue

        # SSH만 선택
        if method.lower() != "ssh":
            continue

        servers.append({
            "host": host,
            "account": account,
            "password": password,
        })

    return servers

def test_ssh_connection(server):
    host = server["host"]
    user = server["account"]
    pwd = server["password"]

    print(f"🔗 {host} ({user}) 접속 시도...")

    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(host, username=user, password=pwd, timeout=5)

        # 로그 파일 확인 (오늘 날짜)
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        log_file = f"catalina.{today}.out"
        stdin, stdout, stderr = client.exec_command(f"ls /path/to/tomcat/logs/{log_file}")
        output = stdout.read().decode().strip()

        if output:
            print(f"✅ 연결 성공 & 로그 파일 발견: {output}")
        else:
            print(f"⚠️ 연결 성공 but 로그 파일 없음")

        client.close()
    except Exception as e:
        print(f"❌ 접속 실패: {e}")

def main():
    html = fetch_table_from_confluence()
    servers = parse_servers(html)

    print(f"총 {len(servers)}개 서버 필터링됨 (SSH 가능)")
    for s in servers:
        test_ssh_connection(s)

if __name__ == "__main__":
    main()
