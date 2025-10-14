# -*- coding: utf-8 -*-
"""
Jira 링크 생성 테스트
"""

import sys
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

from jira_integration import JiraIntegration

# Jira 연동 생성
jira = JiraIntegration()

# 샘플 에러 정보
error_info = {
    'template': 'ERROR NullPointerException at UserService.findById',
    'count': 25,
    'cluster_id': 1,
    'severity': '심각',
    'examples': [
        {'text': '[2024-01-15 08:25:32] ERROR NullPointerException at UserService.findById'}
    ]
}

# 링크 생성
link = jira.generate_web_link(error_info)

print("="*70)
print("생성된 Jira 링크:")
print("="*70)
print(link)
print("="*70)
print("\nSlack 메시지에 포함될 형식:")
print(f"<{link}|📝 여기를 클릭하여 Jira 이슈 작성>")
print("="*70)
