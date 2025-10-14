# -*- coding: utf-8 -*-
"""
Jira 연동 모듈
Slack 알림에서 Jira 이슈를 자동 생성하는 기능
"""

import os
import sys
import json
import requests
from datetime import datetime
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from urllib.parse import quote

# Windows 콘솔 인코딩 문제 해결
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

load_dotenv()


class JiraIntegration:
    def __init__(self):
        # Jira 설정 로드
        self.jira_url = os.getenv('JIRA_URL', '').rstrip('/')
        self.jira_project_key = os.getenv('JIRA_PROJECT_KEY', '')

        # 인증 방식 1: API 토큰 (Jira Cloud)
        self.jira_email = os.getenv('JIRA_EMAIL', '')
        self.jira_api_token = os.getenv('JIRA_API_TOKEN', '')

        # 인증 방식 2: Username/Password (Jira Server/Data Center)
        self.jira_username = os.getenv('JIRA_USERNAME', '')
        self.jira_password = os.getenv('JIRA_PASSWORD', '')

        # 인증 정보 우선순위: API 토큰 > Username/Password
        if self.jira_email and self.jira_api_token:
            self.auth = (self.jira_email, self.jira_api_token)
            self.auth_type = "api_token"
        elif self.jira_username and self.jira_password:
            self.auth = (self.jira_username, self.jira_password)
            self.auth_type = "basic"
        else:
            self.auth = None
            self.auth_type = None

        # API 연동 가능 여부 확인
        self.api_enabled = bool(self.jira_url and self.auth and self.jira_project_key)

        if not self.api_enabled:
            if not self.jira_project_key:
                print("⚠️ JIRA_PROJECT_KEY가 설정되지 않았습니다. Jira 기능이 제한됩니다.")
            elif not self.auth:
                print("⚠️ Jira 인증 정보가 없습니다. 웹 링크 방식만 사용 가능합니다.")
            else:
                print("⚠️ Jira API 설정이 완전하지 않습니다.")
        else:
            print(f"✅ Jira API 연동 준비 완료: {self.jira_url} (인증: {self.auth_type})")

    def create_issue(self, error_info: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """
        Jira 이슈를 API로 생성

        Args:
            error_info: 에러 정보 딕셔너리
                - template: 에러 패턴
                - count: 발생 횟수
                - cluster_id: 클러스터 ID
                - severity: 심각도
                - ai_analysis: AI 분석 결과 (선택)
                - examples: 원본 로그 예시 (선택)

        Returns:
            생성된 이슈 정보 또는 None
        """
        if not self.api_enabled:
            print("❌ Jira API가 활성화되지 않았습니다.")
            return None

        try:
            # 이슈 요약 (Summary)
            summary = self._generate_summary(error_info)

            # 이슈 설명 (Description)
            description = self._generate_description(error_info)

            # 우선순위 결정
            priority = self._determine_priority(error_info)

            # Jira API 요청 페이로드
            payload = {
                "fields": {
                    "project": {
                        "key": self.jira_project_key
                    },
                    "summary": summary,
                    "description": description,
                    "issuetype": {
                        "name": "Bug"  # 또는 "Task"
                    },
                    "priority": {
                        "name": priority
                    },
                    "labels": [
                        "log-monitoring",
                        "automated",
                        f"cluster-{error_info.get('cluster_id', 'unknown')}"
                    ]
                }
            }

            # API 호출
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json"
            }

            # Jira API 버전 선택 (Server는 api/2, Cloud는 api/3)
            api_version = "2" if self.auth_type == "basic" else "3"

            response = requests.post(
                f"{self.jira_url}/rest/api/{api_version}/issue",
                json=payload,
                headers=headers,
                auth=self.auth,
                timeout=30
            )

            if response.status_code in [200, 201]:
                issue_data = response.json()
                issue_key = issue_data.get('key')
                issue_url = f"{self.jira_url}/browse/{issue_key}"

                print(f"✅ Jira 이슈 생성 성공: {issue_key}")

                return {
                    "key": issue_key,
                    "url": issue_url,
                    "id": issue_data.get('id')
                }
            else:
                print(f"❌ Jira 이슈 생성 실패: HTTP {response.status_code}")
                print(f"응답: {response.text}")
                return None

        except Exception as e:
            print(f"❌ Jira 이슈 생성 오류: {e}")
            return None

    def _get_project_id_by_key(self, project_key: str) -> Optional[str]:
        """프로젝트 키로 프로젝트 ID 조회"""
        if not self.auth:
            return None

        try:
            headers = {"Accept": "application/json"}
            api_version = "2" if self.auth_type == "basic" else "3"

            response = requests.get(
                f"{self.jira_url}/rest/api/{api_version}/project/{project_key}",
                headers=headers,
                auth=self.auth,
                timeout=10
            )

            if response.status_code == 200:
                project_data = response.json()
                return project_data.get('id')
            else:
                return None

        except Exception as e:
            return None

    def generate_web_link(self, error_info: Dict[str, Any]) -> str:
        """
        Jira 이슈 작성 페이지로 바로 이동하는 웹 링크 생성
        (API 사용 불가시 대안)

        Returns:
            Jira 이슈 작성 URL
        """
        if not self.jira_url or not self.jira_project_key:
            return "Jira 설정이 필요합니다."

        # 이슈 요약 및 설명 생성
        summary = self._generate_summary(error_info)
        description = self._generate_description_plaintext(error_info)

        # URL 인코딩
        summary_encoded = quote(summary)
        description_encoded = quote(description)

        # Jira 웹 링크 생성
        # Jira Server는 프로젝트 ID(숫자)를 사용해야 함

        # 프로젝트 ID 조회
        project_id = self._get_project_id_by_key(self.jira_project_key)

        if project_id:
            # 제목 생성 및 인코딩
            summary = self._generate_summary(error_info)
            summary_encoded = quote(summary)

            # 프로젝트 ID로 이슈 생성 페이지 열기 (제목 포함)
            web_link = (
                f"{self.jira_url}/secure/CreateIssue.jspa?"
                f"pid={project_id}&"
                f"issuetype=1&"  # 1=Bug
                f"summary={summary_encoded}"
            )
        else:
            # 프로젝트 ID를 찾을 수 없으면 기본 페이지
            web_link = f"{self.jira_url}/secure/CreateIssue.jspa"

        return web_link

    def _generate_summary(self, error_info: Dict[str, Any]) -> str:
        """Jira 이슈 요약 생성"""
        template = error_info.get('template', 'Unknown Error')
        count = error_info.get('count', 0)

        # 템플릿 길이 제한 (Jira summary는 255자 제한)
        if len(template) > 100:
            template = template[:100] + "..."

        return f"[Log Monitor] {template} (발생 {count}회)"

    def _generate_description(self, error_info: Dict[str, Any]) -> str:
        """Jira 이슈 설명 생성 (Jira Markdown 형식)"""
        lines = []

        # 헤더
        lines.append("h2. 🚨 로그 모니터링 시스템에서 자동 생성된 이슈")
        lines.append("")

        # 기본 정보
        lines.append("h3. 📊 기본 정보")
        lines.append(f"* *에러 패턴:* {{{{color:red}}}}{error_info.get('template', 'Unknown')}{{{{color}}}}")
        lines.append(f"* *발생 횟수:* {error_info.get('count', 0)}회")
        lines.append(f"* *클러스터 ID:* {error_info.get('cluster_id', 'N/A')}")
        lines.append(f"* *심각도:* {error_info.get('severity', '경미')}")
        lines.append(f"* *감지 시간:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # AI 분석 결과 (있는 경우)
        ai_analysis = error_info.get('ai_analysis')
        if ai_analysis:
            lines.append("h3. 🤖 AI 분석 결과")
            lines.append(f"* *에러 유형:* {ai_analysis.get('error_type', 'Unknown')}")
            lines.append(f"* *근본 원인:* {ai_analysis.get('root_cause', '분석 불가')}")
            lines.append(f"* *신뢰도:* {ai_analysis.get('confidence', 0)}%")
            lines.append("")

            # 즉시 조치사항
            immediate_actions = ai_analysis.get('immediate_actions', [])
            if immediate_actions:
                lines.append("h4. ⚡ 즉시 조치사항")
                for action in immediate_actions:
                    lines.append(f"* {action}")
                lines.append("")

            # 장기적 해결방안
            long_term = ai_analysis.get('long_term_solutions', [])
            if long_term:
                lines.append("h4. 🔧 장기적 해결방안")
                for solution in long_term:
                    lines.append(f"* {solution}")
                lines.append("")

            # 예방 방법
            prevention = ai_analysis.get('prevention_tips', [])
            if prevention:
                lines.append("h4. 🛡️ 예방 방법")
                for tip in prevention:
                    lines.append(f"* {tip}")
                lines.append("")

        # 원본 로그 예시
        examples = error_info.get('examples', [])
        if examples:
            lines.append("h3. 📝 원본 로그 예시")
            for i, example in enumerate(examples[:3], 1):
                if isinstance(example, dict):
                    text = example.get('text', str(example))
                else:
                    text = str(example)

                lines.append(f"*예시 {i}:*")
                lines.append("{code}")
                lines.append(text)
                lines.append("{code}")
                lines.append("")

        # 푸터
        lines.append("---")
        lines.append("_이 이슈는 로그 모니터링 시스템에 의해 자동으로 생성되었습니다._")

        return "\n".join(lines)

    def _generate_description_plaintext(self, error_info: Dict[str, Any]) -> str:
        """Jira 이슈 설명 생성 (일반 텍스트, 웹 링크용)"""
        lines = []

        lines.append("=== 로그 모니터링 시스템 자동 생성 ===")
        lines.append("")
        lines.append(f"에러 패턴: {error_info.get('template', 'Unknown')}")
        lines.append(f"발생 횟수: {error_info.get('count', 0)}회")
        lines.append(f"클러스터 ID: {error_info.get('cluster_id', 'N/A')}")
        lines.append(f"심각도: {error_info.get('severity', '경미')}")
        lines.append(f"감지 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # AI 분석 결과
        ai_analysis = error_info.get('ai_analysis')
        if ai_analysis:
            lines.append("--- AI 분석 결과 ---")
            lines.append(f"에러 유형: {ai_analysis.get('error_type', 'Unknown')}")
            lines.append(f"근본 원인: {ai_analysis.get('root_cause', '분석 불가')}")
            lines.append("")

        # 원본 로그 예시
        examples = error_info.get('examples', [])
        if examples and len(examples) > 0:
            lines.append("--- 원본 로그 예시 ---")
            example = examples[0]
            if isinstance(example, dict):
                text = example.get('text', str(example))
            else:
                text = str(example)
            lines.append(text[:200])  # 길이 제한
            lines.append("")

        return "\n".join(lines)

    def _determine_priority(self, error_info: Dict[str, Any]) -> str:
        """
        에러 정보를 기반으로 Jira 우선순위 결정

        Returns:
            "Highest", "High", "Medium", "Low", "Lowest"
        """
        count = error_info.get('count', 0)
        severity = error_info.get('severity', '경미')

        # 발생 횟수 기반
        if count >= 50 or severity == "매우 심각":
            return "Highest"
        elif count >= 20 or severity == "심각":
            return "High"
        elif count >= 10 or severity == "주의":
            return "Medium"
        else:
            return "Low"

    def test_connection(self) -> bool:
        """Jira API 연결 테스트"""
        if not self.api_enabled:
            print("❌ Jira API 설정이 완전하지 않습니다.")
            return False

        try:
            headers = {"Accept": "application/json"}

            # Jira API 버전 선택
            api_version = "2" if self.auth_type == "basic" else "3"

            # 프로젝트 정보 조회로 연결 테스트
            response = requests.get(
                f"{self.jira_url}/rest/api/{api_version}/project/{self.jira_project_key}",
                headers=headers,
                auth=self.auth,
                timeout=10
            )

            if response.status_code == 200:
                project_data = response.json()
                print(f"✅ Jira 연결 성공: {project_data.get('name', self.jira_project_key)}")
                return True
            else:
                print(f"❌ Jira 연결 실패: HTTP {response.status_code}")
                print(f"응답: {response.text}")
                return False

        except Exception as e:
            print(f"❌ Jira 연결 오류: {e}")
            return False


def test_jira_integration():
    """Jira 연동 테스트"""
    print("="*60)
    print("Jira 연동 테스트 시작")
    print("="*60)

    jira = JiraIntegration()

    # 연결 테스트
    print("\n1. Jira API 연결 테스트...")
    if jira.test_connection():
        print("\n2. 샘플 이슈 생성 테스트...")

        sample_error = {
            'template': 'ERROR NullPointerException at UserService.findById',
            'count': 25,
            'cluster_id': 1,
            'severity': '심각',
            'ai_analysis': {
                'error_type': 'NullPointerException',
                'root_cause': '사용자 ID가 null인 상태에서 조회 시도',
                'confidence': 85,
                'immediate_actions': [
                    '널 체크 로직 추가',
                    'Optional 패턴 사용 검토'
                ],
                'long_term_solutions': [
                    '단위 테스트에서 널 케이스 추가',
                    '코드 리뷰 프로세스 강화'
                ],
                'prevention_tips': [
                    'IDE 널 체크 플러그인 사용',
                    '정적 분석 도구 도입'
                ]
            },
            'examples': [
                {
                    'text': '[2024-01-15 08:25:32] ERROR NullPointerException at UserService.findById(UserService.java:123)',
                    'timestamp': datetime.now()
                }
            ]
        }

        result = jira.create_issue(sample_error)

        if result:
            print(f"\n✅ 테스트 이슈 생성 성공!")
            print(f"   이슈 키: {result['key']}")
            print(f"   URL: {result['url']}")
        else:
            print("\n❌ 이슈 생성 실패")

    # 웹 링크 생성 테스트
    print("\n3. Jira 웹 링크 생성 테스트...")
    sample_error = {
        'template': 'ERROR Database connection timeout',
        'count': 15,
        'cluster_id': 2,
        'severity': '주의'
    }

    web_link = jira.generate_web_link(sample_error)
    print(f"생성된 웹 링크:")
    print(f"{web_link}")

    print("\n" + "="*60)
    print("테스트 완료")
    print("="*60)


if __name__ == "__main__":
    test_jira_integration()
