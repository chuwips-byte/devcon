"""
Slack 연동 모듈 (향상된 버전)
기존 기능 + 로그 블록 전송 + 요약 리포트 기능 추가
"""

import requests
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
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
    
    def send_error_alert(self, template: str, count: int, cluster_id: int, examples: List[Dict] = None) -> bool:
        """빈발 에러 알림 전송 (향상된 버전 - 원본 로그 예시 포함)"""
        
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
        self._print_console_alert(template, count, severity, recommendations, examples)
        
        # Slack 전송 (활성화된 경우만)
        if not self.enabled:
            return True
        
        # 기본 메시지 구조
        fields = [
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
            }
        ]
        
        # 원본 로그 예시 추가 (새로운 기능!)
        if examples and len(examples) > 0:
            example_text = self._format_log_examples(examples)
            fields.append({
                "title": "📝 원본 로그 예시",
                "value": example_text,
                "short": False
            })
        
        # 권장사항 추가
        fields.append({
            "title": "권장 조치사항",
            "value": recommendations,
            "short": False
        })
        
        message = {
            "text": f"{emoji} 빈발 에러 패턴 감지 - {severity}",
            "attachments": [
                {
                    "color": color,
                    "fields": fields,
                    "footer": "Log Monitoring System",
                    "ts": int(datetime.now().timestamp())
                }
            ]
        }
        
        try:
            response = requests.post(self.webhook_url, json=message, timeout=10)
            if response.status_code == 200:
                print("✅ Slack 알림 전송 성공")
                return True
            else:
                print(f"❌ Slack 알림 전송 실패: HTTP {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Slack 전송 오류: {e}")
            return False
    
    def send_clustering_summary(self, handler_stats: Dict[str, Any]) -> bool:
        """클러스터링 요약 정보를 Slack으로 전송 (새로운 기능!)"""
        if not self.enabled:
            print("📤 Slack 비활성화 - 요약 정보 콘솔 출력만")
            return False
        
        try:
            # 통계 정보 추출
            total_logs = handler_stats.get('total_logs', 0)
            error_logs = handler_stats.get('error_logs', 0)
            clustered_logs = handler_stats.get('clustered_logs', 0)
            top_clusters = handler_stats.get('top_clusters', [])
            
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            error_rate = (error_logs / total_logs * 100) if total_logs > 0 else 0
            clustering_rate = (clustered_logs / error_logs * 100) if error_logs > 0 else 0
            
            # 심각도 분석
            severity_stats = self._analyze_cluster_severity(top_clusters)
            
            # 메시지 구성
            fields = [
                {
                    "title": "📋 총 로그",
                    "value": f"{total_logs:,}개",
                    "short": True
                },
                {
                    "title": "🚨 에러 로그",
                    "value": f"{error_logs:,}개",
                    "short": True
                },
                {
                    "title": "🏷️ 클러스터링",
                    "value": f"{clustered_logs:,}개",
                    "short": True
                },
                {
                    "title": "📊 클러스터 수",
                    "value": f"{len(top_clusters)}개",
                    "short": True
                },
                {
                    "title": "📈 에러율",
                    "value": f"{error_rate:.1f}%",
                    "short": True
                },
                {
                    "title": "🎯 클러스터링율",
                    "value": f"{clustering_rate:.1f}%",
                    "short": True
                }
            ]
            
            # 심각도별 통계 추가
            if severity_stats:
                severity_text = []
                for level, count in severity_stats.items():
                    emoji_map = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
                    emoji = emoji_map.get(level, "⚪")
                    severity_text.append(f"{emoji} {level.upper()}: {count}개")
                
                fields.append({
                    "title": "🚦 심각도별 분포",
                    "value": " | ".join(severity_text),
                    "short": False
                })
            
            # TOP 클러스터 추가
            if top_clusters:
                cluster_text = self._format_top_clusters(top_clusters[:5])
                fields.append({
                    "title": "🏆 TOP 5 에러 패턴",
                    "value": cluster_text,
                    "short": False
                })
            
            # 시스템 상태 판단
            system_status = self._get_system_status(error_rate)
            color = system_status["color"]
            
            message = {
                "text": f"📊 로그 모니터링 요약 - {current_time}",
                "attachments": [
                    {
                        "color": color,
                        "fields": fields,
                        "footer": f"Log Monitoring System | {system_status['message']}",
                        "ts": int(datetime.now().timestamp())
                    }
                ]
            }
            
            response = requests.post(self.webhook_url, json=message, timeout=10)
            
            if response.status_code == 200:
                print("✅ Slack 요약 전송 성공")
                return True
            else:
                print(f"❌ Slack 요약 전송 실패: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Slack 요약 전송 오류: {e}")
            return False
    
    def _format_log_examples(self, examples: List[Dict]) -> str:
        """로그 예시를 포맷팅"""
        if not examples:
            return "예시 없음"
        
        formatted_examples = []
        for i, example in enumerate(examples[:3], 1):  # 최대 3개
            if isinstance(example, dict):
                text = example.get('text', str(example))
                timestamp = example.get('timestamp', 'Unknown time')
            else:
                text = str(example)
                timestamp = 'Unknown time'
            
            # 로그 길이 제한 (150자)
            if len(text) > 150:
                text = text[:150] + "..."
            
            formatted_examples.append(f"**예시 {i}:**\n```{text}```")
        
        return "\n\n".join(formatted_examples)
    
    def _format_top_clusters(self, clusters: List) -> str:
        """TOP 클러스터를 포맷팅"""
        formatted = []
        for i, (cluster_id, template, count) in enumerate(clusters, 1):
            severity = self._get_count_severity(count)
            emoji_map = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
            emoji = emoji_map.get(severity, "⚪")
            
            # 템플릿 길이 제한
            short_template = (template[:40] + "...") if len(template) > 40 else template
            formatted.append(f"{i}. {emoji} `[{count}번]` {short_template}")
        
        return "\n".join(formatted)
    
    def _analyze_cluster_severity(self, clusters: List) -> Dict[str, int]:
        """클러스터들의 심각도 분석"""
        severity_stats = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        
        for _, _, count in clusters:
            severity = self._get_count_severity(count)
            severity_stats[severity] += 1
        
        return severity_stats
    
    def _get_count_severity(self, count: int) -> str:
        """발생 횟수에 따른 심각도 판단"""
        if count >= 50:
            return "critical"
        elif count >= 20:
            return "high"
        elif count >= 10:
            return "medium"
        else:
            return "low"
    
    def _get_system_status(self, error_rate: float) -> Dict[str, str]:
        """에러율에 따른 시스템 상태 판단"""
        if error_rate > 80:
            return {"color": "danger", "message": "🚨 시스템 상태 위험!"}
        elif error_rate > 50:
            return {"color": "warning", "message": "⚠️ 시스템 상태 주의!"}
        elif error_rate > 25:
            return {"color": "warning", "message": "🟡 모니터링 필요"}
        else:
            return {"color": "good", "message": "🟢 시스템 정상"}
    
    def _get_recommendations(self, template: str) -> str:
        """에러 패턴에 따른 권장사항 생성 (기존 유지)"""
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
    
    def _print_console_alert(self, template: str, count: int, severity: str, recommendations: str, examples: List = None):
        """콘솔에 알림 출력 (향상된 버전)"""
        print("\n" + "="*60)
        print(f"SLACK 알림 - {severity}")
        print("="*60)
        print(f"패턴: {template}")
        print(f"횟수: {count}번")
        print(f"권장사항:")
        for line in recommendations.split('\n'):
            print(f"  {line}")
        
        # 원본 로그 예시 출력 (새로운 기능!)
        if examples and len(examples) > 0:
            print(f"\n📝 원본 로그 예시:")
            for i, example in enumerate(examples[:2], 1):  # 콘솔에는 2개만
                if isinstance(example, dict):
                    text = example.get('text', str(example))
                else:
                    text = str(example)
                
                # 길이 제한
                if len(text) > 100:
                    text = text[:100] + "..."
                print(f"  예시 {i}: {text}")
        
        print("="*60)

def test_slack_integration():
    """Slack 연동 테스트 함수 (향상된 버전)"""
    print("향상된 Slack 연동 테스트 시작")
    print("-" * 40)
    
    # SlackNotifier 생성 (환경변수 자동 로드)
    notifier = SlackNotifier()
    
    if notifier.enabled:
        print(f"✅ Slack Webhook URL 로드됨")
        print("\n1. 연결 테스트 실행 중...")
        if notifier.test_connection():
            print("\n2. 샘플 에러 알림 전송 중... (원본 로그 포함)")
            
            # 샘플 예시 로그들
            sample_examples = [
                {
                    'text': '[2024-01-15 08:25:32] ERROR NullPointerException at UserService.findById(UserService.java:123)',
                    'timestamp': datetime.now()
                },
                {
                    'text': '[2024-01-15 08:26:45] ERROR NullPointerException at UserController.getUser(UserController.java:45)',
                    'timestamp': datetime.now()
                }
            ]
            
            notifier.send_error_alert(
                template="ERROR NullPointerException at <*>",
                count=25,
                cluster_id=1,
                examples=sample_examples
            )
            
            print("\n3. 샘플 요약 리포트 전송 중...")
            sample_stats = {
                'total_logs': 850,
                'error_logs': 230,
                'clustered_logs': 230,
                'top_clusters': [
                    (1, "ERROR NullPointerException at <*>", 48),
                    (2, "ERROR FileNotFoundException: <*> not found", 35),
                    (3, "ERROR Database connection timeout", 22),
                    (4, "ERROR OutOfMemoryError: Java heap space", 18),
                    (5, "WARN Authentication failed for user <*>", 8)
                ]
            }
            notifier.send_clustering_summary(sample_stats)
            
        else:
            print("연결 테스트 실패. 설정을 확인하세요.")
    else:
        print("❌ SLACK_WEBHOOK_URL이 .env 파일에 설정되지 않았습니다.")
        print("\n콘솔 출력 테스트만 실행:")
        notifier.send_error_alert(
            template="ERROR Database connection failed - timeout after <*>",
            count=15,
            cluster_id=2,
            examples=[{'text': 'Sample log for console test', 'timestamp': datetime.now()}]
        )

if __name__ == "__main__":
    test_slack_integration()