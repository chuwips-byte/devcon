"""
Slack 연동 모듈
빈발 에러 패턴을 Slack으로 알림 전송
"""

import requests
import json
import os
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
load_dotenv()  # .env 파일 로드

class SlackNotifier:
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv('SLACK_WEBHOOK_URL')
        self.enabled = bool(self.webhook_url)
        
        if not self.enabled:
            print("Slack Webhook URL이 설정되지 않았습니다. 콘솔 출력만 진행합니다.")
    
    def test_connection(self) -> bool:
        """Slack 연결 테스트"""
        if not self.enabled:
            print("Slack이 비활성화되어 있습니다.")
            return False
        
        test_message = {
            "text": "로그 모니터링 시스템 연결 테스트",
            "attachments": [
                {
                    "color": "good",
                    "fields": [
                        {
                            "title": "상태",
                            "value": "정상 연결됨",
                            "short": True
                        },
                        {
                            "title": "테스트 시간",
                            "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "short": True
                        }
                    ]
                }
            ]
        }
        
        try:
            response = requests.post(self.webhook_url, json=test_message, timeout=10)
            if response.status_code == 200:
                print("Slack 연결 테스트 성공!")
                return True
            else:
                print(f"Slack 연결 실패: HTTP {response.status_code}")
                print(f"응답: {response.text}")
                return False
        except Exception as e:
            print(f"Slack 연결 오류: {e}")
            return False
    
    def send_error_alert(self, template: str, count: int, cluster_id: int) -> bool:
        """빈발 에러 알림 전송"""
        
        # 심각도 결정
        if count >= 50:
            severity = "매우 심각"
            color = "danger"
            emoji = "🔴"
        elif count >= 20:
            severity = "심각"
            color = "warning"
            emoji = "🟠"
        elif count >= 10:
            severity = "주의"
            color = "warning"
            emoji = "🟡"
        else:
            severity = "경미"
            color = "good"
            emoji = "🟢"
        
        # 권장사항 생성
        recommendations = self._get_recommendations(template)
        
        # 콘솔 출력 (항상 실행)
        self._print_console_alert(template, count, severity, recommendations)
        
        # Slack 전송 (활성화된 경우만)
        if not self.enabled:
            return True
        
        message = {
            "text": f"{emoji} 빈발 에러 패턴 감지 - {severity}",
            "attachments": [
                {
                    "color": color,
                    "fields": [
                        {
                            "title": "에러 패턴",
                            "value": f"```{template}```",
                            "short": False
                        },
                        {
                            "title": "발생 횟수",
                            "value": f"{count}번",
                            "short": True
                        },
                        {
                            "title": "클러스터 ID",
                            "value": str(cluster_id),
                            "short": True
                        },
                        {
                            "title": "심각도",
                            "value": f"{emoji} {severity}",
                            "short": True
                        },
                        {
                            "title": "감지 시간",
                            "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "short": True
                        },
                        {
                            "title": "권장 조치사항",
                            "value": recommendations,
                            "short": False
                        }
                    ],
                    "footer": "Log Monitoring System",
                    "ts": int(datetime.now().timestamp())
                }
            ]
        }
        
        try:
            response = requests.post(self.webhook_url, json=message, timeout=10)
            if response.status_code == 200:
                print("Slack 알림 전송 성공")
                return True
            else:
                print(f"Slack 알림 전송 실패: HTTP {response.status_code}")
                return False
        except Exception as e:
            print(f"Slack 전송 오류: {e}")
            return False
    
    def _get_recommendations(self, template: str) -> str:
        """에러 패턴에 따른 권장사항 생성"""
        template_lower = template.lower()
        
        if 'nullpointer' in template_lower:
            return "• 널체크 로직 추가 필요\n• Optional 패턴 사용 검토\n• 단위 테스트에서 널 케이스 추가"
        elif 'database' in template_lower or 'connection' in template_lower:
            return "• DB 커넥션 풀 설정 확인\n• 커넥션 누수 점검\n• DB 서버 상태 모니터링"
        elif 'outofmemory' in template_lower:
            return "• JVM 힙 크기 조정\n• 메모리 프로파일링 실행\n• GC 로그 분석"
        elif 'filenotfound' in template_lower:
            return "• 파일 경로 확인\n• 파일 권한 점검\n• 설정 파일 존재 여부 확인"
        elif 'authentication' in template_lower:
            return "• 인증 로직 점검\n• 토큰 만료 확인\n• 보안 로그 분석"
        elif 'sql' in template_lower and 'duplicate' in template_lower:
            return "• DB 제약조건 확인\n• 중복 데이터 처리 로직 개선\n• 트랜잭션 격리 수준 점검"
        else:
            return "• 상세 로그 분석 필요\n• 관련 시스템 상태 확인\n• 개발팀 리뷰 요청"
    
    def _print_console_alert(self, template: str, count: int, severity: str, recommendations: str):
        """콘솔에 알림 출력"""
        print("\n" + "="*60)
        print(f"SLACK 알림 - {severity}")
        print("="*60)
        print(f"패턴: {template}")
        print(f"횟수: {count}번")
        print(f"권장사항:")
        for line in recommendations.split('\n'):
            print(f"  {line}")
        print("="*60)

def test_slack_integration():
    """Slack 연동 테스트 함수"""
    print("Slack 연동 테스트 시작")
    print("-" * 30)
    
    # SlackNotifier 생성 (환경변수 자동 로드)
    notifier = SlackNotifier()
    
    if notifier.enabled:
        print(f"✅ Slack Webhook URL 로드됨")
        print("\n1. 연결 테스트 실행 중...")
        if notifier.test_connection():
            print("\n2. 샘플 알림 전송 중...")
            notifier.send_error_alert(
                template="ERROR NullPointerException at UserService.findById(<*>)",
                count=25,
                cluster_id=1
            )
        else:
            print("연결 테스트 실패. 설정을 확인하세요.")
    else:
        print("❌ SLACK_WEBHOOK_URL이 .env 파일에 설정되지 않았습니다.")
        print("\n콘솔 출력 테스트만 실행:")
        notifier.send_error_alert(
            template="ERROR Database connection failed - timeout after <*>",
            count=15,
            cluster_id=2
        )

if __name__ == "__main__":
    test_slack_integration()