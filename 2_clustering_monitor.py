"""
파일명: 2_clustering_monitor.py
목적: Drain3를 이용한 실시간 로그 클러스터링 모니터링 + RAG 기반 지능형 분석
기능:
  - 파일 변경 실시간 감지 (Watchdog)
  - 로그 패턴 클러스터링 (Drain3)
  - 빈발 에러 패턴 감지 및 알림
  - RAG 시스템 통합 지능형 분석
  - Slack 연동 알림
"""

import os
import re
import time
import json
import logging
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from drain3 import TemplateMiner
from drain3.template import Template

# Slack 연동 import
try:
    from slack_integration import SlackNotifier
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False

# RAG 시스템 import
try:
    from rag_system import analyze_log_with_rag, get_rag_system
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    print("⚠️ RAG 시스템을 찾을 수 없습니다. 기본 분석 모드로 진행합니다.")

class LogClusteringHandler(FileSystemEventHandler):
    """로그 파일 변경 감지 및 클러스터링 처리"""

    def __init__(self, watch_dir="./logs"):
        self.watch_dir = Path(watch_dir)
        self.last_position = {}

        # 로그 분석 설정
        self.error_keywords = [
            'ERROR', 'Exception', 'Failed', 'Error', 'FATAL', 'CRITICAL',
            'NullPointer', 'OutOfMemory', 'SQLException', 'timeout',
            'refused', 'denied', 'not found', 'cannot'
        ]

        # 통계 카운터
        self.total_logs = 0
        self.error_logs = 0
        self.pattern_clusters = defaultdict(int)

        # Drain3 템플릿 마이너 초기화
        self.template_miner = None
        self.initialize_drain3()

        # 클러스터 상세 정보 저장
        self.cluster_details = {}
        self.cluster_templates = {}
        self.frequent_patterns = set()

        # Slack 연동 초기화
        if SLACK_AVAILABLE:
            try:
                self.slack_notifier = SlackNotifier()
                print("✅ Slack 연동 활성화")
            except Exception as e:
                print(f"⚠️ Slack 연동 실패: {e}")
                self.slack_notifier = None
        else:
            self.slack_notifier = None
            print("ℹ️ Slack 연동 비활성화 (slack_integration.py 없음)")

        # RAG 시스템 초기화
        if RAG_AVAILABLE:
            try:
                self.rag_system = get_rag_system()
                print("✅ RAG 시스템 활성화")
            except Exception as e:
                print(f"⚠️ RAG 시스템 초기화 실패: {e}")
                self.rag_system = None
        else:
            self.rag_system = None
            print("ℹ️ RAG 시스템 비활성화")

    def initialize_drain3(self):
        """Drain3 템플릿 마이너 초기화"""
        try:
            config = {
                'drain_extra_delimiters': ['=', ':', ',', ';', '|'],
                'drain_sim_th': 0.8,
                'drain_depth': 5,
                'drain_max_children': 100,
                'drain_max_clusters': 1000,
            }

            self.template_miner = TemplateMiner(config=config)
            print("✅ Drain3 템플릿 마이너 초기화 완료")
        except Exception as e:
            print(f"❌ Drain3 초기화 실패: {e}")
            self.template_miner = None

    def on_modified(self, event):
        """파일 변경 감지 시 호출"""
        if not event.is_directory and event.src_path.endswith('.log'):
            try:
                self.process_new_logs(event.src_path)
            except Exception as e:
                print(f"❌ 로그 처리 중 오류: {e}")

    def process_new_logs(self, file_path):
        """새로 추가된 로그 라인들 처리"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                # 이전 위치부터 읽기
                current_position = self.last_position.get(file_path, 0)
                f.seek(current_position)

                new_lines = f.readlines()
                self.last_position[file_path] = f.tell()

                for line in new_lines:
                    line = line.strip()
                    if line:
                        self.total_logs += 1

                        # 에러 로그 감지 및 처리
                        if self.is_error_line(line):
                            self.error_logs += 1
                            self.handle_error_clustering(line)

                        # 로그 출력 (옵션)
                        if self.total_logs % 10 == 0:  # 10개마다 진행상황 출력
                            self.print_progress()

        except Exception as e:
            print(f"❌ 파일 읽기 오류 ({file_path}): {e}")

    def is_error_line(self, line):
        """에러 로그 라인 판별"""
        line_upper = line.upper()
        return any(keyword.upper() in line_upper for keyword in self.error_keywords)

    def handle_error_clustering(self, error_line):
        """에러 로그 클러스터링 처리 및 RAG 분석"""
        if not self.template_miner:
            return

        try:
            # Drain3를 이용한 로그 클러스터링
            clustering_result = self.template_miner.add_log_message(error_line)

            if clustering_result["change_type"] != "none":
                cluster_id = clustering_result["cluster_id"]
                template_str = str(clustering_result["template_mined"])

                # 현재 클러스터 ID 저장
                self.current_cluster_id = cluster_id

                # 클러스터 발생 횟수 업데이트
                self.pattern_clusters[cluster_id] += 1
                count = self.pattern_clusters[cluster_id]

                # 클러스터 상세 정보 저장
                self.cluster_details[cluster_id] = {
                    'template': template_str,
                    'count': count,
                    'last_seen': datetime.now(),
                    'sample_log': error_line
                }

                # 빈발 패턴 감지 (3회 이상)
                if count >= 3 and cluster_id not in self.frequent_patterns:
                    self.frequent_patterns.add(cluster_id)
                    print(f"\n🚨 빈발 패턴 감지!")
                    print(f"클러스터 ID: {cluster_id}")
                    print(f"패턴: {template_str}")
                    print(f"발생 횟수: {count}")

                    # RAG 기반 지능형 분석 실행
                    self.alert_frequent_error(template_str, count, error_line)
                elif count >= 3:
                    # 이미 감지된 패턴의 추가 발생
                    if count % 10 == 0:  # 10의 배수마다 업데이트
                        print(f"🔄 기존 패턴 지속 발생: {template_str} ({count}회)")
                        # RAG 재분석 (선택적)
                        if count % 20 == 0:  # 20회마다 재분석
                            self.alert_frequent_error(template_str, count, error_line)

        except Exception as e:
            print(f"❌ 클러스터링 처리 오류: {e}")

    def alert_frequent_error(self, template, count, sample_log=""):
        """빈발 에러 알림 (RAG + LLM 통합)"""
        print(f"\n{'='*80}")
        print(f"🔥 긴급! 반복 에러 패턴 감지")
        print(f"{'='*80}")
        print(f"📈 발생 횟수: {count}번")
        print(f"📝 패턴: {template}")
        if sample_log:
            print(f"💡 샘플 로그: {sample_log[:100]}...")

        # 1단계: RAG 시스템을 통한 지능형 분석
        rag_result = None
        if RAG_AVAILABLE and self.rag_system:
            print(f"\n🧠 RAG 시스템 분석 시작...")
            try:
                # 원본 로그와 패턴을 모두 분석에 활용
                analysis_text = f"Error Pattern: {template}\nSample Log: {sample_log}\nOccurrence Count: {count}"
                rag_result = analyze_log_with_rag(analysis_text)

                if rag_result["success"]:
                    print(f"✅ RAG 분석 완료!")
                    print(f"🔍 검색된 관련 지식: {len(rag_result.get('search_results', []))}개")
                    print(f"\n🎯 AI 분석 결과:")
                    print("=" * 60)
                    print(rag_result["analysis_result"])
                    print("=" * 60)

                    # 웹 대시보드로 RAG 결과 전송
                    self.send_rag_results_to_dashboard(template, count, rag_result)
                else:
                    print(f"❌ RAG 분석 실패: {rag_result.get('error_message', '알 수 없는 오류')}")
                    # 실패시 기본 분석으로 폴백
                    self._fallback_to_basic_analysis(template, count)

            except Exception as e:
                print(f"❌ RAG 시스템 오류: {e}")
                self._fallback_to_basic_analysis(template, count)
        else:
            # RAG 시스템이 없으면 기본 분석
            print(f"⚠️ RAG 시스템 비활성화 - 기본 분석 모드")
            self._fallback_to_basic_analysis(template, count)

        # 2단계: Slack 알림 전송
        if self.slack_notifier:
            try:
                cluster_id = getattr(self, 'current_cluster_id', 0)

                # RAG 결과가 있으면 함께 전송
                if rag_result and rag_result["success"]:
                    # RAG 분석 결과를 Slack 메시지에 포함
                    rag_summary = rag_result["analysis_result"][:500] + "..." if len(rag_result["analysis_result"]) > 500 else rag_result["analysis_result"]

                    enhanced_message = f"""
🧠 **RAG 기반 지능형 분석 결과**

📊 **패턴**: {template}
📈 **발생 횟수**: {count}번
🤖 **AI 분석**: {rag_summary}
🔍 **관련 지식**: {len(rag_result.get('search_results', []))}개 항목 발견
                    """

                    self.slack_notifier.send_error_alert(
                        template, count, cluster_id,
                        additional_info=enhanced_message
                    )
                else:
                    # 기본 Slack 알림
                    self.slack_notifier.send_error_alert(template, count, cluster_id)

                print(f"✅ Slack 알림 전송 완료")
            except Exception as e:
                print(f"❌ Slack 알림 실패: {e}")

        print(f"{'='*80}")
        print(f"💡 RAG 기반 지능형 분석 완료")
        print(f"{'='*80}\n")

    def _fallback_to_basic_analysis(self, template, count):
        """RAG 시스템 실패시 기본 분석"""
        print(f"\n🔄 기본 패턴 분석 모드")
        print(f"=" * 50)

        template_str = str(template).lower()

        if 'nullpointer' in template_str or 'npe' in template_str:
            print(f"🎯 **NullPointerException 감지**")
            print(f"💡 **권장 해결방법**:")
            print(f"   - null 체크 조건문 추가: if (object != null)")
            print(f"   - Optional 클래스 사용 고려")
            print(f"   - 디펜시브 프로그래밍 적용")
            print(f"   - IDE의 정적 분석 도구 활용")

        elif 'database' in template_str or 'connection' in template_str or 'sql' in template_str:
            print(f"🎯 **데이터베이스 연결 오류 감지**")
            print(f"💡 **권장 해결방법**:")
            print(f"   - 커넥션 풀 상태 확인")
            print(f"   - DB 서버 리소스 모니터링")
            print(f"   - 타임아웃 설정 검토")
            print(f"   - 네트워크 연결 상태 점검")

        elif 'outofmemory' in template_str or 'memory' in template_str:
            print(f"🎯 **메모리 부족 오류 감지**")
            print(f"💡 **권장 해결방법**:")
            print(f"   - JVM 힙 메모리 크기 증설 (-Xmx 옵션)")
            print(f"   - 메모리 누수 지점 분석")
            print(f"   - GC 로그 분석 및 튜닝")
            print(f"   - 메모리 프로파일링 도구 사용")

        elif 'filenotfound' in template_str or 'no such file' in template_str:
            print(f"🎯 **파일 접근 오류 감지**")
            print(f"💡 **권장 해결방법**:")
            print(f"   - 파일 경로 정확성 확인")
            print(f"   - 파일 권한 설정 점검")
            print(f"   - 절대 경로 사용 고려")
            print(f"   - 파일 존재 여부 사전 체크")

        elif 'timeout' in template_str:
            print(f"🎯 **타임아웃 오류 감지**")
            print(f"💡 **권장 해결방법**:")
            print(f"   - 타임아웃 설정값 조정")
            print(f"   - 네트워크 지연 원인 분석")
            print(f"   - 재시도 로직 구현")
            print(f"   - Circuit Breaker 패턴 적용")

        else:
            print(f"🎯 **일반 오류 패턴 감지**")
            print(f"💡 **권장 해결방법**:")
            print(f"   - 로그 레벨 상세 확인")
            print(f"   - 스택 트레이스 분석")
            print(f"   - 최근 변경사항 검토")
            print(f"   - 시스템 리소스 모니터링")

        print(f"=" * 50)

    def send_rag_results_to_dashboard(self, template, count, rag_result):
        """RAG 분석 결과를 웹 대시보드로 전송"""
        try:
            # RAG 결과를 웹 대시보드 형식으로 변환
            dashboard_result = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'template': str(template),
                'count': count,
                'rag_analysis': rag_result["analysis_result"],
                'search_results': rag_result.get("search_results", []),
                'source': 'rag_system',
                'success': rag_result["success"],
                'severity': self.get_severity_level(count),
                'cluster_id': getattr(self, 'current_cluster_id', 0)
            }

            # 파일로 저장하여 웹 대시보드가 읽을 수 있도록 함
            rag_results_file = 'rag_analysis_results.json'
            try:
                with open(rag_results_file, 'r', encoding='utf-8') as f:
                    results = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                results = []

            results.append(dashboard_result)
            # 최근 20개만 유지
            results = results[-20:]

            with open(rag_results_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

            print(f"✅ RAG 분석 결과를 웹 대시보드로 전송 완료")

        except Exception as e:
            print(f"❌ RAG 결과 대시보드 전송 실패: {e}")

    def get_severity_level(self, count):
        """발생 횟수에 따른 심각도 레벨 반환"""
        if count >= 50:
            return 'critical'
        elif count >= 20:
            return 'warning'
        elif count >= 10:
            return 'info'
        else:
            return 'low'

    def print_progress(self):
        """진행 상황 출력"""
        error_rate = (self.error_logs / self.total_logs * 100) if self.total_logs > 0 else 0
        print(f"\r📊 처리됨: {self.total_logs} | 에러: {self.error_logs} | 에러율: {error_rate:.1f}% | 패턴: {len(self.pattern_clusters)}", end="", flush=True)

    def get_cluster_id(self, clustering_result):
        """클러스터 ID 추출"""
        try:
            return clustering_result.get("cluster_id", 0)
        except Exception:
            return 0

    def get_template(self, clustering_result):
        """템플릿 추출"""
        try:
            template = clustering_result.get("template_mined")
            return str(template) if template else "Unknown Template"
        except Exception:
            return "Unknown Template"

    def get_cluster_size(self, cluster_id):
        """특정 클러스터의 크기 반환"""
        try:
            cluster = self.template_miner.drain.id_to_cluster.get(cluster_id)
            return cluster.size if cluster else 0
        except Exception:
            return self.pattern_clusters.get(cluster_id, 0)

    def get_clusters_dict(self):
        """현재 모든 클러스터 정보를 딕셔너리로 반환"""
        clusters = {}

        try:
            # Drain3에서 클러스터 정보 추출
            if self.template_miner and hasattr(self.template_miner.drain, 'id_to_cluster'):
                for cluster_id, cluster in self.template_miner.drain.id_to_cluster.items():
                    if cluster_id in self.cluster_details:
                        detail = self.cluster_details[cluster_id]
                        clusters[cluster_id] = {
                            'id': cluster_id,
                            'template': detail['template'],
                            'count': detail['count'],
                            'size': cluster.size,
                            'last_seen': detail['last_seen'].isoformat(),
                            'sample_log': detail.get('sample_log', ''),
                            'severity': self.get_severity_level(detail['count'])
                        }

            # 추가로 pattern_clusters에 있는 정보도 포함
            for cluster_id, count in self.pattern_clusters.items():
                if cluster_id not in clusters and cluster_id in self.cluster_details:
                    detail = self.cluster_details[cluster_id]
                    clusters[cluster_id] = {
                        'id': cluster_id,
                        'template': detail['template'],
                        'count': count,
                        'size': count,
                        'last_seen': detail['last_seen'].isoformat(),
                        'sample_log': detail.get('sample_log', ''),
                        'severity': self.get_severity_level(count)
                    }

        except Exception as e:
            print(f"❌ 클러스터 정보 수집 오류: {e}")

        return clusters

    def print_summary(self):
        """모니터링 요약 정보 출력"""
        print(f"\n{'='*80}")
        print(f"📊 로그 모니터링 요약 리포트")
        print(f"{'='*80}")
        print(f"📈 총 로그 수: {self.total_logs:,}")
        print(f"🚨 에러 로그 수: {self.error_logs:,}")
        print(f"📊 에러율: {(self.error_logs/self.total_logs*100):.2f}%" if self.total_logs > 0 else "📊 에러율: 0%")
        print(f"🔍 발견된 패턴: {len(self.pattern_clusters)}개")
        print(f"⚠️ 빈발 패턴: {len(self.frequent_patterns)}개")

        if self.pattern_clusters:
            print(f"\n🔥 상위 빈발 패턴:")
            sorted_patterns = sorted(self.pattern_clusters.items(), key=lambda x: x[1], reverse=True)[:5]

            for i, (cluster_id, count) in enumerate(sorted_patterns, 1):
                detail = self.cluster_details.get(cluster_id, {})
                template = detail.get('template', f'클러스터 {cluster_id}')
                severity = self.get_severity_level(count)

                # 심각도 이모지
                severity_emoji = {
                    'critical': '🔴',
                    'warning': '🟠',
                    'info': '🟡',
                    'low': '🟢'
                }.get(severity, '⚪')

                print(f"   {i}. {severity_emoji} [{cluster_id}] {count}회 - {template[:60]}...")

        if RAG_AVAILABLE and self.rag_system:
            try:
                rag_stats = self.rag_system.get_knowledge_stats()
                print(f"\n🧠 RAG 시스템 상태:")
                print(f"   📚 지식베이스: {rag_stats.get('total_documents', 0)}개 문서")
                print(f"   🔍 임베딩 모델: {rag_stats.get('embedding_model', 'Unknown')}")
                print(f"   ✅ 시스템 상태: {rag_stats.get('status', 'Unknown')}")
            except Exception as e:
                print(f"   ❌ RAG 시스템 상태 확인 실패: {e}")

        print(f"{'='*80}\n")

    def get_cluster_template(self, cluster_id):
        """특정 클러스터의 템플릿 반환"""
        try:
            if cluster_id in self.cluster_details:
                return self.cluster_details[cluster_id]['template']

            cluster = self.template_miner.drain.id_to_cluster.get(cluster_id)
            return str(cluster.get_template()) if cluster else f"클러스터 {cluster_id}"
        except Exception:
            return f"클러스터 {cluster_id}"

def start_monitoring(watch_dir="./logs"):
    """모니터링 시작"""
    print(f"🚀 로그 모니터링 시스템 시작")
    print(f"📁 모니터링 디렉토리: {os.path.abspath(watch_dir)}")
    print(f"🔍 감지 대상: *.log 파일")

    if RAG_AVAILABLE:
        print(f"🧠 RAG 시스템: ✅ 활성")
    else:
        print(f"🧠 RAG 시스템: ❌ 비활성")

    if SLACK_AVAILABLE:
        print(f"📱 Slack 연동: ✅ 활성")
    else:
        print(f"📱 Slack 연동: ❌ 비활성")

    print(f"=" * 60)

    # 모니터링 디렉토리 생성
    os.makedirs(watch_dir, exist_ok=True)

    # 이벤트 핸들러 생성
    event_handler = LogClusteringHandler(watch_dir)

    # 파일 관찰자 설정
    observer = Observer()
    observer.schedule(event_handler, watch_dir, recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(5)  # 5초마다 요약 출력
            if event_handler.total_logs > 0:
                event_handler.print_progress()

            # 10초마다 상세 요약
            if int(time.time()) % 20 == 0:
                event_handler.print_summary()

    except KeyboardInterrupt:
        print(f"\n\n⏹️ 모니터링 중단됨")
        event_handler.print_summary()
    finally:
        observer.stop()
        observer.join()

if __name__ == "__main__":
    start_monitoring()