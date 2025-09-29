# jira_integration.py
import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

from rag.trainer import train_issue

load_dotenv()

JIRA_URL = os.getenv("JIRA_URL")
USERNAME = os.getenv("JIRA_USERNAME")
PASSWORD = os.getenv("JIRA_PASSWORD")
PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY")

# JQL: 프로젝트 키 있으면 프로젝트 단위, 없으면 전체
if PROJECT_KEY:
    JQL = f'project = {PROJECT_KEY} AND issuetype = Bug ORDER BY created DESC'
else:
    JQL = 'issuetype = Bug ORDER BY created DESC'

def fetch_bug_issues(max_results):
    url = f"{JIRA_URL}/rest/api/2/search"
    params = {"jql": JQL, "maxResults": max_results}
    res = requests.get(url, auth=HTTPBasicAuth(USERNAME, PASSWORD), params=params)

    if res.status_code != 200:
        raise RuntimeError(f"❌ Jira API 실패: {res.status_code} {res.text}")

    return res.json().get("issues", [])

def main():
    print(f"🚀 Jira BUG 이슈 학습 시작 (최대 {MAX_RESULTS}개)")
    issues = fetch_bug_issues()

    for issue in issues:
        key = issue["key"]
        fields = issue["fields"]

        desc = fields.get("description") or ""
        신고내용, 처리내용 = "", ""
        if "신고내용" in desc:
            parts = desc.split("처리내용")
            신고내용 = parts[0].replace("신고내용", "").strip()
            처리내용 = parts[1].strip() if len(parts) > 1 else ""
        else:
            신고내용 = desc.strip()

        train_issue(key, 신고내용, 처리내용)

    print("✅ Jira BUG 이슈 학습 완료")

if __name__ == "__main__":
    main()
