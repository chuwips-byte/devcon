# -*- coding: utf-8 -*-
"""
Jira 프로젝트 목록 조회 스크립트
.env에 설정된 Jira 서버의 모든 프로젝트를 조회합니다.
"""

import os
import sys
import requests
from dotenv import load_dotenv

# Windows 콘솔 인코딩 문제 해결
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

load_dotenv()

def list_jira_projects():
    """Jira 프로젝트 목록 조회"""
    jira_url = os.getenv('JIRA_URL', '').rstrip('/')
    jira_username = os.getenv('JIRA_USERNAME', '')
    jira_password = os.getenv('JIRA_PASSWORD', '')
    jira_email = os.getenv('JIRA_EMAIL', '')
    jira_api_token = os.getenv('JIRA_API_TOKEN', '')

    if not jira_url:
        print("❌ JIRA_URL이 설정되지 않았습니다.")
        return

    # 인증 정보 선택
    if jira_email and jira_api_token:
        auth = (jira_email, jira_api_token)
        auth_type = "API Token"
        api_version = "3"
    elif jira_username and jira_password:
        auth = (jira_username, jira_password)
        auth_type = "Basic Auth"
        api_version = "2"
    else:
        print("❌ 인증 정보가 설정되지 않았습니다.")
        return

    print("="*70)
    print("Jira 프로젝트 목록 조회")
    print("="*70)
    print(f"서버: {jira_url}")
    print(f"인증: {auth_type}")
    print("-"*70)

    try:
        headers = {"Accept": "application/json"}

        # 프로젝트 목록 조회
        response = requests.get(
            f"{jira_url}/rest/api/{api_version}/project",
            headers=headers,
            auth=auth,
            timeout=10
        )

        if response.status_code == 200:
            projects = response.json()

            if not projects:
                print("⚠️ 프로젝트가 없습니다.")
                return

            print(f"\n✅ 총 {len(projects)}개의 프로젝트 발견:\n")

            for project in projects:
                key = project.get('key', 'N/A')
                name = project.get('name', 'N/A')
                project_type = project.get('projectTypeKey', 'N/A')

                print(f"  🔹 [{key}] {name}")
                print(f"     타입: {project_type}")
                print()

            print("-"*70)
            print("💡 .env 파일에 설정 예시:")
            print(f"   JIRA_PROJECT_KEY={projects[0].get('key', 'YOUR_KEY')}")
            print("="*70)

        else:
            print(f"❌ API 호출 실패: HTTP {response.status_code}")
            print(f"응답: {response.text}")

    except Exception as e:
        print(f"❌ 오류 발생: {e}")


if __name__ == "__main__":
    list_jira_projects()
