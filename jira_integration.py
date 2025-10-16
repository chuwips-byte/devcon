# -*- coding: utf-8 -*-
"""
Jira 통합 모듈
- Slack 알림에서 Jira 이슈 자동 생성
- Jira 이슈 조회 및 RAG 학습 데이터 수집
"""

import os
import sys
import json
import requests
from datetime import datetime
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv
from urllib.parse import quote
from requests.auth import HTTPBasicAuth

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
        self.jira_username = os.getenv('JIRA_USERNAME')
        self.jira_password = os.getenv('JIRA_PASSWORD')

        # 인증 정보 우선순위: API 토큰 > Username/Password
        if self.jira_email and self.jira_api_token:
            self.auth = HTTPBasicAuth(self.jira_email, self.jira_api_token)
            self.auth_type = "api_token"
        elif self.jira_username and self.jira_password:
            self.auth = HTTPBasicAuth(self.jira_username, self.jira_password)
            self.auth_type = "basic"
        else:
            self.auth = None
            self.auth_type = None

        # API 연동 가능 여부 확인
        self.api_enabled = bool(self.jira_url and self.auth)

        if not self.api_enabled:
            if not self.auth:
                print("⚠️ Jira 인증 정보가 없습니다. 웹 링크 방식만 사용 가능합니다.")
            else:
                print("⚠️ Jira API 설정이 완전하지 않습니다.")
        else:
            print(f"✅ Jira API 연동 준비 완료: {self.jira_url} (인증: {self.auth_type})")

    # ==================== 이슈 생성 기능 (Slack → Jira) ====================

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

        if not self.jira_project_key:
            print("❌ JIRA_PROJECT_KEY가 설정되지 않았습니다.")
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
                        "name": "Bug"
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

    def generate_web_link(self, error_info: Dict[str, Any]) -> str:
        """
        Jira 이슈 작성 페이지로 바로 이동하는 웹 링크 생성
        (API 사용 불가시 대안)

        Returns:
            Jira 이슈 작성 URL
        """
        if not self.jira_url or not self.jira_project_key:
            return "Jira 설정이 필요합니다."

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

    # ==================== 이슈 조회 기능 (Jira → RAG 학습) ====================

    def fetch_bug_issues(self, max_results: int = 100) -> List[Dict[str, Any]]:
        """
        Jira에서 Bug 이슈 목록 조회

        Args:
            max_results: 최대 조회 개수

        Returns:
            이슈 목록
        """
        if not self.api_enabled:
            print("❌ Jira API가 활성화되지 않았습니다.")
            return []

        try:
            # JQL: 프로젝트 키 있으면 프로젝트 단위, 없으면 전체
            if self.jira_project_key:
                jql = f'project = {self.jira_project_key} AND issuetype = Bug ORDER BY created DESC'
            else:
                jql = 'issuetype = Bug ORDER BY created DESC'

            url = f"{self.jira_url}/rest/api/2/search"
            params = {
                "jql": jql,
                "maxResults": max_results
            }

            response = requests.get(
                url,
                auth=self.auth,
                params=params,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                issues = data.get("issues", [])
                print(f"✅ Jira 이슈 조회 성공: {len(issues)}개")
                return issues
            else:
                print(f"❌ Jira 이슈 조회 실패: HTTP {response.status_code}")
                print(f"응답: {response.text}")
                return []

        except Exception as e:
            print(f"❌ Jira 이슈 조회 오류: {e}")
            return []

    def parse_issue_for_training(self, issue: Dict[str, Any]) -> Dict[str, str]:
        """
        Jira 이슈를 RAG 학습용 데이터로 파싱

        Args:
            issue: Jira API에서 반환된 이슈 객체

        Returns:
            파싱된 데이터 (key, 신고내용, 처리내용)
        """
        key = issue.get("key", "")
        fields = issue.get("fields", {})
        description = fields.get("description") or ""

        # 신고내용과 처리내용 분리
        신고내용, 처리내용 = "", ""

        if "신고내용" in description:
            parts = description.split("처리내용")
            신고내용 = parts[0].replace("신고내용", "").strip()
            처리내용 = parts[1].strip() if len(parts) > 1 else ""
        else:
            신고내용 = description.strip()

        return {
            "key": key,
            "신고내용": 신고내용,
            "처리내용": 처리내용
        }

    def fetch_and_train_issues(self, max_results: int = 100, train_callback=None):
        """
        Jira 이슈를 조회하고 RAG 학습 함수에 전달

        Args:
            max_results: 최대 조회 개수
            train_callback: 학습 콜백 함수 (key, 신고내용, 처리내용)
        """
        print(f"🚀 Jira BUG 이슈 학습 시작 (최대 {max_results}개)")

        issues = self.fetch_bug_issues(max_results)

        if not issues:
            print("⚠️ 조회된 이슈가 없습니다.")
            return

        for issue in issues:
            parsed = self.parse_issue_for_training(issue)

            if train_callback:
                try:
                    train_callback(
                        parsed["key"],
                        parsed["신고내용"],
                        parsed["처리내용"]
                    )
                    print(f"  - {parsed['key']} 학습 완료")
                except Exception as e:
                    print(f"  - {parsed['key']} 학습 실패: {e}")

        print("✅ Jira BUG 이슈 학습 완료")

    # ==================== 공통 유틸리티 메서드 ====================

    def test_connection(self) -> bool:
        """Jira API 연결 테스트"""
        if not self.api_enabled:
            print("❌ Jira API 설정이 완전하지 않습니다.")
            return False

        try:
            headers = {"Accept": "application/json"}

            # Jira API 버전 선택
            api_version = "2" if self.auth_type == "basic" else "3"

            # myself 엔드포인트로 인증 테스트
            response = requests.get(
                f"{self.jira_url}/rest/api/{api_version}/myself",
                headers=headers,
                auth=self.auth,
                timeout=10
            )

            if response.status_code == 200:
                user_data = response.json()
                print(f"✅ Jira 연결 성공: {user_data.get('displayName', 'User')}")
                return True
            else:
                print(f"❌ Jira 연결 실패: HTTP {response.status_code}")
                print(f"응답: {response.text}")
                return False

        except Exception as e:
            print(f"❌ Jira 연결 오류: {e}")
            return False

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

    def search_issues(self, jql: str, startAt: int = 0, maxResults: int = 50) -> List:
        """
        JQL로 이슈 검색 (페이지네이션 지원)

        Args:
            jql: JQL 쿼리 문자열
            startAt: 시작 인덱스
            maxResults: 최대 결과 수

        Returns:
            이슈 목록
        """
        if not self.api_enabled:
            print("❌ Jira API가 활성화되지 않았습니다.")
            return []

        try:
            url = f"{self.jira_url}/rest/api/2/search"
            params = {
                "jql": jql,
                "startAt": startAt,
                "maxResults": maxResults
            }

            response = requests.get(
                url,
                auth=self.auth,
                params=params,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                issues = data.get("issues", [])

                # Jira 응답을 객체로 변환 (fields 접근을 위해)
                from types import SimpleNamespace

                def dict_to_obj(d):
                    """딕셔너리를 객체로 변환"""
                    if isinstance(d, dict):
                        return SimpleNamespace(**{k: dict_to_obj(v) for k, v in d.items()})
                    elif isinstance(d, list):
                        return [dict_to_obj(item) for item in d]
                    else:
                        return d

                converted_issues = [dict_to_obj(issue) for issue in issues]
                return converted_issues
            else:
                print(f"❌ Jira 검색 실패: HTTP {response.status_code}")
                print(f"응답: {response.text}")
                return []

        except Exception as e:
            print(f"❌ Jira 검색 오류: {e}")
            return []

    # jira_integration.py의 JiraIntegration 클래스 안에 추가

    def fetch_bug_issues_for_rag(self, max_results: int = 20) -> dict:
        """RAG 학습용 Bug 이슈 조회 (라벨 정보 포함)"""
        if not self.api_enabled:
            return {
                'issues': [],
                'total_found': 0,
                'issue_keys': [],
                'labels_summary': {}
            }

        print(f"\n🔍 Jira Bug 이슈 검색 중 (최대 {max_results}개)...")

        jql = 'issuetype = Bug ORDER BY created DESC'

        all_issues = []
        labels_count = {}
        start_at = 0
        batch_size = 50

        while len(all_issues) < max_results:
            remaining = max_results - len(all_issues)
            current_batch = min(batch_size, remaining)

            issues_batch = self.search_issues(
                jql=jql,
                startAt=start_at,
                maxResults=current_batch
            )

            if not issues_batch:
                break

            for issue in issues_batch:
                all_issues.append(issue)

                # 🔥 라벨 집계
                if hasattr(issue.fields, 'labels') and issue.fields.labels:
                    for label in issue.fields.labels:
                        labels_count[label] = labels_count.get(label, 0) + 1

                if len(all_issues) >= max_results:
                    break

            start_at += current_batch

            if start_at > 1000:
                break

        issue_keys = [issue.key for issue in all_issues]

        return {
            'issues': all_issues,
            'total_found': len(all_issues),
            'issue_keys': issue_keys,
            'labels_summary': labels_count
        }
# ==================== 테스트 함수 ====================

def test_jira_integration():
    """Jira 연동 통합 테스트"""
    print("="*60)
    print("Jira 통합 모듈 테스트 시작")
    print("="*60)

    jira = JiraIntegration()

    # 1. 연결 테스트
    print("\n1. Jira API 연결 테스트...")
    if not jira.test_connection():
        print("⚠️ 연결 실패. 나머지 테스트를 건너뜁니다.")
        return

    # 2. 이슈 생성 테스트 (Slack → Jira)
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

    # 3. 이슈 조회 테스트 (Jira → RAG)
    print("\n3. Bug 이슈 조회 테스트 (최대 5개)...")
    issues = jira.fetch_bug_issues(max_results=5)

    if issues:
        print(f"\n조회된 이슈 목록:")
        for issue in issues:
            parsed = jira.parse_issue_for_training(issue)
            print(f"  - {parsed['key']}: {parsed['신고내용'][:50]}...")

    # 4. 웹 링크 생성 테스트
    print("\n4. Jira 웹 링크 생성 테스트...")
    web_link = jira.generate_web_link(sample_error)
    print(f"생성된 웹 링크: {web_link}")

    print("\n" + "="*60)
    print("테스트 완료")
    print("="*60)


if __name__ == "__main__":
    test_jira_integration()