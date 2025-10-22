"""
통합 웹 대시보드 - Flask 기반 실시간 모니터링 (리팩토링 버전)
- clustering_monitor의 LogClusteringHandler 상속
- ollama_integration의 AI 분석 통합
- SSH 연결 후 에러 발생 시 자동 AI 분석 및 대시보드 표시
"""

# 필수 라이브러리 import
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import threading
import time
from datetime import datetime
from collections import defaultdict, deque
import os
import psutil
import paramiko
import glob
from typing import Optional, Dict

# 🔥 clustering_monitor에서 LogClusteringHandler import
try:
    from clustering_monitor import LogClusteringHandler
    CLUSTERING_AVAILABLE = True
    print("✅ LogClusteringHandler 클래스 로드 성공")
except ImportError as e:
    CLUSTERING_AVAILABLE = False
    print(f"❌ clustering_monitor 로드 실패: {e}")

# 🔥 ollama_integration에서 AI 분석기 import (수정된 버전)
try:
    from ollama_integration import RagIntegratedOllamaAnalyzer
    RAG_OLLAMA_AVAILABLE = True
    print("✅ RAG 통합 Ollama 분석기 로드 성공")
except ImportError as e:
    RAG_OLLAMA_AVAILABLE = False
    print(f"❌ RAG 통합 Ollama 분석기 로드 실패: {e}")

# 기존 OllamaErrorAnalyzer는 더 이상 시도하지 않음 (존재하지 않으므로)
OLLAMA_AVAILABLE = RAG_OLLAMA_AVAILABLE


# Jira 연동 import
try:
    from jira_integration import JiraIntegration
    JIRA_AVAILABLE = True
    print("✅ Jira 연동 모듈 로드 성공")
except ImportError as e:
    JIRA_AVAILABLE = False
    print(f"❌ Jira 연동 모듈 로드 실패: {e}")

# RAG Trainer import
try:
    from rag_trainer import RAGTrainer
    RAG_TRAINER_AVAILABLE = True
    print("✅ RAG Trainer 모듈 로드 성공")
except ImportError as e:
    RAG_TRAINER_AVAILABLE = False
    print(f"❌ RAG Trainer 모듈 로드 실패: {e}")

# RAG 학습 가능 여부
RAG_AVAILABLE = JIRA_AVAILABLE and RAG_TRAINER_AVAILABLE
print("✅ RAG 학습 가능: Jira 연동 + RAG Trainer" if RAG_AVAILABLE else "❌ RAG 학습 불가: Jira 연동 또는 RAG Trainer 필요")

# Slack 연동 (선택사항)
try:
    from slack_integration import SlackNotifier
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False
    print("Slack 연동 모듈을 찾을 수 없습니다.")

# Drain3 / Watchdog
try:
    from drain3 import TemplateMiner
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError as e:
    print(f"필수 모듈 import 실패: {e}")
    print("pip install -r requirements.txt를 실행하세요.")

# Flask 앱
app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*")

# 전역 데이터 저장소
dashboard_data = {
    'total_logs': 0,
    'error_logs': 0,
    'recent_logs': deque(maxlen=100),
    'clusters': {},  # cluster_id -> cluster info
    'error_timeline': deque(maxlen=50),
    'cluster_stats': defaultdict(int),
    'last_frequent_alert': {},
    'ssh_logs': deque(maxlen=500),
    'ai_analyses': deque(maxlen=50),
    'rag_training_history': deque(maxlen=10),
    'last_rag_result': None
}

# 모듈 상태
module_status = {
    'log_monitoring': {'status': 'running', 'process': None},
    'ssh_connection': {
        'status': 'disconnected',
        'process': None,
        'log_path': None,
        'host': None,
        'username': None
    },
    'rag_learning': {
        'status': 'stopped',
        'process': None,
        'progress': {'stage': '', 'current': 0, 'total': 0, 'message': ''}
    },
    'ai_analyzer': {
        'status': 'unknown',
        'enabled': False,
        'last_analysis': None
    }
}

# 🔥 LogClusteringHandler를 상속받아 웹 대시보드 전용 핸들러 생성
class WebDashboardHandler(LogClusteringHandler if CLUSTERING_AVAILABLE else FileSystemEventHandler):
    def __init__(self, watch_dir="logs"):
        # 부모 초기화
        if CLUSTERING_AVAILABLE:
            super().__init__()
            print("✅ LogClusteringHandler 상속 완료")
        else:
            print("⚠️ LogClusteringHandler 없음 - 기본 핸들러 사용")
            self.last_position = {}
            self.error_keywords = ['ERROR', 'FATAL', 'Exception', 'Failed', 'Error:']
            self.template_miner = None
            self.total_logs = 0
            self.error_logs = 0
            self.slack_notifier = None
            self.ollama_analyzer = None

        self.watch_dir = watch_dir

        # 🔥 Slack Notifier 명시적 초기화 (부모 클래스와 관계없이 항상 실행)
        if SLACK_AVAILABLE:
            try:
                from slack_integration import SlackNotifier
                self.slack_notifier = SlackNotifier()
                if self.slack_notifier.enabled:
                    print("✅ Slack 연동 활성화 (Webhook 설정됨)")
                else:
                    print("💬 Slack Webhook URL 미설정 - 콘솔 출력 모드")
            except Exception as e:
                print(f"⚠️ Slack 초기화 실패: {e}")
                self.slack_notifier = None
        else:
            print("💬 Slack 모듈 로드 안됨 - 콘솔 출력만")
            self.slack_notifier = None

        # RAG 통합 Ollama 분석기 초기화
        self.ollama_analyzer = None
        if RAG_OLLAMA_AVAILABLE:
            try:
                self.ollama_analyzer = RagIntegratedOllamaAnalyzer()
                print("✅ RAG 통합 Ollama 분석기 초기화 성공")
            except Exception as e:
                print(f"❌ RAG 통합 Ollama 분석기 초기화 실패: {e}")
                self.ollama_analyzer = None
        else:
            print("❌ RAG 통합 Ollama 분석기 사용 불가")

        # AI 분석기 상태 반영
        if hasattr(self, 'ollama_analyzer') and self.ollama_analyzer:
            module_status['ai_analyzer']['enabled'] = self.ollama_analyzer.enabled
            module_status['ai_analyzer']['status'] = 'enabled' if self.ollama_analyzer.enabled else 'disabled'
            if self.ollama_analyzer.enabled:
                print("✅ Ollama AI 분석기 활성화 (웹 대시보드 연동)")
        else:
            module_status['ai_analyzer']['status'] = 'unavailable'

        # 🔥 RAG 모델 자동 로딩 추가
        self.rag_trainer = None
        self.rag_available = False
        self.load_latest_rag_model()

        # 🔍 디버깅: 초기화 상태 확인
        print(f"\n🔍 [초기화 완료] Slack Notifier: {self.slack_notifier is not None}")
        if self.slack_notifier:
            print(f"🔍 [초기화 완료] Slack Enabled: {self.slack_notifier.enabled}")

        print("✅ 웹 대시보드 핸들러 초기화 완료")

    def load_latest_rag_model(self):
        """가장 최신 RAG 모델 자동 로드"""
        try:
            model_dirs = glob.glob("models/bug_rag_model_*")
            if not model_dirs:
                print("⚠️ 학습된 RAG 모델이 없습니다. AI 분석만 사용됩니다.")
                return

            # 가장 최신 모델 선택 (디렉토리명 기준)
            latest_model = sorted(model_dirs)[-1]

            print(f"🔄 RAG 모델 로드 시도: {latest_model}")
            if not RAG_TRAINER_AVAILABLE:
                print("⚠️ RAG Trainer 모듈이 없어서 모델을 로드할 수 없습니다.")
                return

            self.rag_trainer = RAGTrainer()
            self.rag_trainer.load_model(latest_model)
            self.rag_available = True

            stats = self.rag_trainer.get_stats()
            print(f"✅ RAG 모델 로드 완료: {stats['num_documents']}개 문서")

        except Exception as e:
            print(f"⚠️ RAG 모델 로드 실패: {e}")
            self.rag_available = False

    def search_rag_knowledge(self, error_log: str, template: str, top_k: int = 3,
                             similarity_threshold: float = 0.4) -> Optional[Dict]:
        """
        RAG 지식베이스에서 유사한 에러 검색

        Args:
            error_log: 에러 로그 원문
            template: Drain3로 추출한 템플릿
            top_k: 상위 몇 개 결과 반환
            similarity_threshold: 유사도 임계값 (0.0 ~ 1.0)

        Returns:
            유사한 이슈가 있으면 결과 딕셔너리, 없으면 None
        """
        if not self.rag_available or not self.rag_trainer:
            return None

        try:
            # 템플릿과 원문을 결합하여 검색 쿼리 생성
            query = f"{template}\n{error_log}"

            print(f"🔍 RAG 지식베이스 검색 중...")
            results = self.rag_trainer.search(query, top_k=top_k)

            # 유사도가 임계값 이상인 결과만 필터링
            filtered_results = [r for r in results if r['similarity'] >= similarity_threshold]

            if not filtered_results:
                print(f"   ❌ 유사도 {similarity_threshold} 이상인 결과 없음")
                return None

            best_match = filtered_results[0]
            print(f"   ✅ 유사 이슈 발견: {best_match['document'].get('id')} "
                  f"(유사도: {best_match['similarity']:.3f})")

            # RAG 검색 결과를 AI 분석 포맷으로 변환
            doc = best_match['document']
            metadata = doc.get('metadata', {})

            rag_result = {
                'source': 'RAG',  # 🔥 RAG 검색 결과임을 표시
                'issue_key': doc.get('id', 'Unknown'),
                'similarity': best_match['similarity'],
                'error_type': metadata.get('summary', 'Unknown Error'),
                'severity': metadata.get('priority', 'Medium'),
                'root_cause': doc.get('text', '')[:200],  # 설명 일부
                'status': metadata.get('status', 'Unknown'),
                'labels': metadata.get('labels', []),
                'immediate_actions': [
                    f"유사 이슈 참고: {doc.get('id')}",
                    f"우선순위: {metadata.get('priority', 'Unknown')}",
                    "Jira에서 해결 방법 확인"
                ],
                'confidence': int(best_match['similarity'] * 100),
                'related_issues': [
                    {
                        'issue_key': r['document'].get('id'),
                        'similarity': r['similarity'],
                        'summary': r['document'].get('metadata', {}).get('summary', '')
                    }
                    for r in filtered_results[:3]
                ]
            }

            return rag_result

        except Exception as e:
            print(f"❌ RAG 검색 실패: {e}")
            return None

    def send_rag_alert(self, cluster_id, cluster, error_log, template, rag_result):
        """RAG 검색 결과로 Slack 알림 전송 - slack_integration 메서드 호출"""
        try:
            if not self.slack_notifier:
                print("⚠️ Slack Notifier 없음 - RAG 알림 전송 생략")
                return

            # 🔥 slack_integration의 send_rag_alert 메서드를 직접 호출
            self.slack_notifier.send_rag_alert(
                cluster_id=cluster_id,
                cluster={'count': getattr(cluster, 'size', 0)},  # cluster 객체를 dict로 변환
                error_log=error_log,
                template=template,
                rag_result=rag_result
            )

            print("✅ Slack RAG 알림 전송 완료 (slack_integration 메서드 사용)")

        except Exception as e:
            print(f"⚠️ Slack RAG 알림 실패: {e}")

    def process_new_logs(self, file_path):
        """새로운 로그 라인 처리 - 부모 메서드 오버라이드"""
        if not self.template_miner:
            return

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                last_pos = self.last_position.get(file_path, 0)
                # [호출] 파일 포인터 이동: 마지막 읽은 위치로 점프
                f.seek(last_pos)

                new_lines = f.readlines()
                self.last_position[file_path] = f.tell()
                print(f"   📄 새 라인: {len(new_lines)}개")

                for line in new_lines:
                    line = line.strip()
                    if not line:
                        continue

                    self.total_logs += 1
                    dashboard_data['total_logs'] += 1

                    # [호출] 에러 여부 판단
                    if self.is_error_line(line):
                        self.error_logs += 1
                        dashboard_data['error_logs'] += 1

                        # [호출] 대시보드 데이터 갱신
                        self.update_dashboard_data(line, is_error=True)

                        # [호출] 클러스터링 + (조건부) AI 분석
                        self.handle_error_clustering(line)

                        # [호출] 실시간 에러 로그 푸시 (Socket.IO)
                        try:
                            socketio.emit('new_error_log', {
                                'timestamp': datetime.now().isoformat(),
                                'content': line,
                                'type': 'error'
                            })
                        except Exception as e:
                            print(f"Socket 전송 오류: {e}")
                    else:
                        # [호출] 일반 로그도 대시보드 반영
                        self.update_dashboard_data(line, is_error=False)

        except Exception as e:
            print(f"❌ 파일 읽기 오류: {e}")

    def update_dashboard_data(self, line, is_error=False):
        """대시보드 데이터 업데이트"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'content': line,
            'type': 'error' if is_error else 'info',
            'severity': self.get_log_severity(line) if is_error else 'info'
        }
        # [호출] 최근 로그 큐에 적재
        dashboard_data['recent_logs'].append(log_entry)

        if is_error:
            # [호출] 에러 타임라인에 카운트 1건 적재
            now = datetime.now()
            timeline_entry = {'timestamp': now.isoformat(), 'count': 1}
            dashboard_data['error_timeline'].append(timeline_entry)
            print(f"🚨 [ERROR] {line[:100]}...")

    def get_log_severity(self, line):
        """로그 심각도 판단"""
        line_upper = line.upper()
        if 'FATAL' in line_upper or 'CRITICAL' in line_upper:
            return 'critical'
        elif 'ERROR' in line_upper or 'EXCEPTION' in line_upper:
            return 'error'
        elif 'WARN' in line_upper:
            return 'warning'
        else:
            return 'info'

    def handle_error_clustering(self, error_line):
        """에러 클러스터링 처리 - 웹 기능 추가"""
        if not self.template_miner:
            print("❌ Drain3 엔진이 초기화되지 않음")
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n🚨 [{timestamp}] 에러 감지!")
        print(f"📝 로그: {error_line}")

        try:
            # [호출] Drain3로 로그 템플릿/클러스터 식별
            result = self.template_miner.add_log_message(error_line)

            # [호출] 상위/헬퍼 메서드로 클러스터 ID/템플릿 추출
            cluster_id = self.get_cluster_id(result)
            template = self.get_template(result)

            print(f"🏷️  클러스터 ID: {cluster_id}")
            print(f"📋 템플릿: {template}")

            # [호출] 대시보드 클러스터 정보 준비(없으면 생성)
            if cluster_id not in dashboard_data['clusters']:
                dashboard_data['clusters'][cluster_id] = {
                    'template': template,
                    'count': 0,
                    'first_seen': datetime.now().isoformat(),
                    'last_seen': datetime.now().isoformat(),
                    'severity': '경미',
                    'recent_logs': deque(maxlen=10),
                    'ai_analysis': None
                }

            cluster = dashboard_data['clusters'][cluster_id]
            cluster['count'] += 1
            cluster['last_seen'] = datetime.now().isoformat()
            cluster['severity'] = self.get_severity(cluster['count'])
            # [호출] 최근 로그 예시 저장
            cluster['recent_logs'].append({'content': error_line, 'timestamp': datetime.now().isoformat()})
            # [호출] 집계
            dashboard_data['cluster_stats'][cluster_id] += 1

            cluster_size = cluster['count']
            print(f"📊 발생 횟수: {cluster_size}번")

            # 🔥 빈발(>=3) 시 RAG → AI 순서로 처리
            if cluster_size >= 3:
                print(f"⚠️  빈발 패턴 감지! {cluster_size}번 발생")

                # 🔥 1단계: RAG 지식베이스 검색
                rag_result = self.search_rag_knowledge(error_line, template)

                if rag_result:
                    # ✅ RAG에서 유사 이슈 발견
                    print("✅ RAG 지식베이스에서 유사 이슈 발견 - AI 분석 생략")
                    cluster['ai_analysis'] = rag_result

                    # 대시보드에 기록
                    dashboard_data['ai_analyses'].append({
                        'cluster_id': cluster_id,
                        'template': template,
                        'analysis': rag_result,
                        'timestamp': datetime.now().isoformat(),
                        'source': 'RAG'  # 🔥 출처 표시
                    })
                    module_status['ai_analyzer']['last_analysis'] = datetime.now().isoformat()

                    # Slack 알림 (RAG 결과 포함)
                    self.send_rag_alert(cluster_id, cluster, error_line, template, rag_result)

                    # [호출] 웹으로 AI 완료 이벤트 푸시 (RAG 결과)
                    try:
                        socketio.emit('ai_analysis_complete', {
                            'cluster_id': cluster_id,
                            'template': template,
                            'analysis': rag_result,
                            'timestamp': datetime.now().isoformat(),
                            'source': 'RAG'
                        })
                        print("✅ RAG 분석 결과 웹 대시보드로 전송 완료")
                    except Exception as e:
                        print(f"Socket 전송 오류: {e}")

                else:
                    # ❌ RAG에서 유사 이슈 없음 → AI 분석 수행
                    print("💬 RAG 지식베이스에 유사 이슈 없음 - AI 분석 시작")

                    if self.ollama_analyzer and self.ollama_analyzer.enabled:
                        print("🤖 AI 분석기 활성화됨 - AI 분석 시작")
                        self.perform_ai_analysis_for_web(cluster_id, cluster, error_line, template)
                    else:
                        print("💬 AI 분석기 비활성화 - 기본 알림만 전송")
                        self.alert_frequent_error(error_line, template, cluster_size, cluster_id)

            # [호출] 클러스터 업데이트를 웹으로 푸시
            try:
                socketio.emit('cluster_update', {
                    'cluster_id': cluster_id,
                    'template': template,
                    'count': cluster['count'],
                    'severity': cluster['severity'],
                    'last_seen': cluster['last_seen'],
                    'ai_analysis': cluster.get('ai_analysis')
                })
            except Exception as e:
                print(f"Socket 전송 오류: {e}")

        except Exception as e:
            print(f"❌ 클러스터링 처리 오류: {e}")

        print("-" * 50)

    def get_severity(self, count):
        """발생 횟수에 따른 심각도 판단"""
        if count >= 50:
            return '매우 심각'
        elif count >= 20:
            return '심각'
        elif count >= 10:
            return '주의'
        else:
            return '경미'

    def alert_frequent_error(self, error_line, template, count, cluster_id):
        """빈발 에러 Slack 알림 (AI 분석 없는 기본 버전)"""
        try:
            if self.slack_notifier and self.slack_notifier.enabled:
                examples = [{'text': error_line, 'timestamp': datetime.now().isoformat()}]
                # [호출] Slack 알림 전송
                self.slack_notifier.send_error_alert(
                    template=template,
                    count=count,
                    cluster_id=cluster_id,
                    examples=examples
                )
                print("✅ Slack 알림 (기본) 전송 완료")
            else:
                print("💬 Slack 비활성화 - 콘솔 출력만")
        except Exception as e:
            print(f"⚠️ Slack 알림 실패: {e}")

    def perform_ai_analysis_for_web(self, cluster_id, cluster, error_log, template):
        """웹 대시보드용 AI 분석 수행 (ollama_integration 사용)"""
        print(f"🤖 웹 대시보드 AI 분석 시작: {template[:50]}...")

        try:
            # [호출] AI 분석 실행
            ai_analysis = self.ollama_analyzer.analyze_error(
                error_log=error_log,
                error_template=template,
                occurrence_count=cluster['count'],
                context={
                    "cluster_id": cluster_id,
                    "detection_time": datetime.now().isoformat(),
                    "total_logs": dashboard_data['total_logs'],
                    "error_logs": dashboard_data['error_logs'],
                    "source": "web_dashboard"
                }
            )

            # [호출] 분석 결과를 메모리/히스토리에 반영
            cluster['ai_analysis'] = ai_analysis
            dashboard_data['ai_analyses'].append({
                'cluster_id': cluster_id,
                'template': template,
                'analysis': ai_analysis,
                'timestamp': datetime.now().isoformat()
            })
            module_status['ai_analyzer']['last_analysis'] = datetime.now().isoformat()

            print(f"\n🧠 AI 분석 완료: {ai_analysis.get('error_type')} / {ai_analysis.get('severity')}")

            # [호출] Slack (AI 포함) 알림
            try:
                if self.slack_notifier and self.slack_notifier.enabled:
                    examples = [{'text': error_log, 'timestamp': datetime.now().isoformat()}]
                    self.slack_notifier.send_error_alert_with_ai(
                        template=template,
                        count=cluster['count'],
                        cluster_id=cluster_id,
                        ai_analysis=ai_analysis,
                        examples=examples
                    )
                    print("✅ Slack 알림 (AI 분석 포함) 전송 완료")
            except Exception as e:
                print(f"⚠️ Slack 알림 실패: {e}")

            # [호출] 웹으로 AI 완료 이벤트 푸시
            try:
                socketio.emit('ai_analysis_complete', {
                    'cluster_id': cluster_id,
                    'template': template,
                    'analysis': ai_analysis,
                    'timestamp': datetime.now().isoformat()
                })
                print("✅ AI 분석 결과 웹 대시보드로 전송 완료")
            except Exception as e:
                print(f"Socket 전송 오류: {e}")

        except Exception as e:
            print(f"❌ AI 분석 실패: {e}")
            cluster['ai_analysis'] = None


def monitor_ssh_logs(ssh_client, log_path):
    """SSH 원격 로그 모니터링 + 자동 AI 분석"""
    try:
        print(f"🔍 SSH 로그 모니터링 시작: {log_path}")

        # [호출] 원격 tail -f 실행
        stdin, stdout, stderr = ssh_client.exec_command(f'tail -f {log_path}')

        # [호출] 웹 핸들러 전역 준비 (1회)
        if 'web_handler' not in globals():
            global web_handler
            web_handler = WebDashboardHandler()

        for line in iter(stdout.readline, ""):
            if not line:
                break

            line = line.strip()
            if not line:
                continue

            is_error = web_handler.is_error_line(line)

            # [호출] SSH 로그 버퍼에 적재
            ssh_log_entry = {
                'timestamp': datetime.now().isoformat(),
                'content': line,
                'type': 'error' if is_error else 'info',
                'source': 'ssh'
            }
            dashboard_data['ssh_logs'].append(ssh_log_entry)

            # [호출] 대시보드 데이터 갱신
            web_handler.update_dashboard_data(line, is_error)

            # [호출] 에러면 클러스터링(+AI) 수행
            if is_error:
                web_handler.handle_error_clustering(line)

            # [호출] 실시간 SSH 로그 푸시
            socketio.emit('ssh_log_update', ssh_log_entry)

    except Exception as e:
        print(f"❌ SSH 로그 모니터링 오류: {e}")
        module_status['ssh_connection']['status'] = 'disconnected'
        module_status['ssh_connection']['process'] = None


def rag_learning_process(model_name='sentence-transformers/all-MiniLM-L6-v2', max_results=20):
    """RAG 학습 프로세스 (Jira 연동)"""
    try:
        # [호출] 프런트에 진행률 전송 (초기)
        socketio.emit('rag_progress', {'stage': 'init', 'progress': 0, 'total': 100})

        if not JIRA_AVAILABLE:
            raise Exception("Jira 모듈을 사용할 수 없습니다")
        if not RAG_TRAINER_AVAILABLE:
            raise Exception("RAG Trainer 모듈을 사용할 수 없습니다")

        socketio.emit('rag_progress', {'stage': 'connecting', 'progress': 10, 'total': 100, 'detail': 'Jira 연결 중...'})
        # [호출] Jira 연결
        jira = JiraIntegration()

        socketio.emit('rag_progress', {'stage': 'searching', 'progress': 20, 'total': 100, 'detail': 'Bug 이슈 검색 중...'})
        # [호출] Bug 이슈 수집
        fetch_count = max_results * 2
        bug_data = jira.fetch_bug_issues_for_rag(max_results=fetch_count)
        all_issues = bug_data['issues']
        issue_keys = bug_data['issue_keys']
        labels_summary = bug_data['labels_summary']

        print(f"\n✅ {len(all_issues)}개의 Bug 이슈 수집 완료")
        if len(all_issues) == 0:
            raise Exception("Bug 타입의 이슈를 찾을 수 없습니다")

        socketio.emit('rag_progress', {'stage': 'preprocessing', 'progress': 50, 'total': 100, 'detail': 'Bug 데이터 전처리 중...'})

        # [호출] RAG 문서화
        documents = []
        excluded_count = 0

        for i, issue in enumerate(all_issues):
            # 목표 개수에 도달하면 중단
            if len(documents) >= max_results:
                break

            try:
                status = issue.fields.status.name if hasattr(issue.fields, 'status') and issue.fields.status else 'Unknown'

                # Closed/Done 상태 제외
                if status.lower() in ['closed', 'done']:
                    excluded_count += 1
                    print(f"   제외: {issue.key} (status: {status})")
                    continue
                doc_text = f"Bug ID: {issue.key}\n"
                doc_text += f"Summary: {issue.fields.summary}\n"

                status = issue.fields.status.name if hasattr(issue.fields, 'status') and issue.fields.status else 'Unknown'
                if status.lower() == 'closed' or status.lower() == 'done':
                    print(f"   제외: {issue.key} (status: {status})")
                    continue

                doc_text = f"Bug ID: {issue.key}\n"
                doc_text += f"Summary: {issue.fields.summary}\n"

                if hasattr(issue.fields, 'description') and issue.fields.description:
                    doc_text += f"Description: {issue.fields.description}\n"
                if hasattr(issue.fields, 'priority') and issue.fields.priority:
                    doc_text += f"Priority: {issue.fields.priority.name}\n"
                if hasattr(issue.fields, 'status') and issue.fields.status:
                    doc_text += f"Status: {issue.fields.status.name}\n"
                if hasattr(issue.fields, 'components') and issue.fields.components:
                    components = [comp.name for comp in issue.fields.components]
                    doc_text += f"Components: {', '.join(components)}\n"
                if hasattr(issue.fields, 'labels') and issue.fields.labels:
                    doc_text += f"Labels: {', '.join(issue.fields.labels)}\n"

                documents.append({
                    'id': issue.key,
                    'text': doc_text,
                    'type': 'bug',
                    'metadata': {
                        'issue_key': issue.key,
                        'summary': issue.fields.summary,
                        'priority': issue.fields.priority.name if hasattr(issue.fields, 'priority') and issue.fields.priority else 'Unknown',
                        'status': status,  # 여기도 동일한 status 변수 사용
                        'labels': issue.fields.labels if hasattr(issue.fields, 'labels') else []
                    }
                })

                progress = 50 + (len(documents) / max_results) * 20
                # [호출] 프런트 진행률 업데이트
                socketio.emit('rag_progress', {
                    'stage': 'preprocessing',
                    'progress': int(progress),
                    'total': 100,
                    'detail': f'Bug 데이터 전처리 중... ({len(documents)}/{max_results})'
                })

            except Exception as e:
                print(f"❌ 이슈 {issue.key} 처리 중 오류: {e}")
                continue

        if not documents:
            raise Exception("처리 가능한 Bug 이슈가 없습니다")

        print(f"\n✅ {len(documents)}개 문서 전처리 완료")
        socketio.emit('rag_progress', {'stage': 'training', 'progress': 70, 'total': 100, 'detail': 'RAG 모델 학습 중...'})

        # [호출] 트레이너 생성
        trainer = RAGTrainer(model_name=model_name)

        socketio.emit('rag_progress', {'stage': 'indexing', 'progress': 80, 'total': 100, 'detail': 'Bug 데이터 인덱싱 중...'})
        # [호출] 벡터 DB 구축
        trainer.build_vector_database(documents)

        socketio.emit('rag_progress', {'stage': 'saving', 'progress': 90, 'total': 100, 'detail': '모델 저장 중...'})
        model_path = f"models/bug_rag_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        # [호출] 모델 저장
        save_result = trainer.save_model(model_path)

        # [호출] 학습 완료 이벤트(간단 버전) → 중복 삭제하고 아래 상세 결과로 통합
        # socketio.emit('rag_complete', {...})  # (삭제됨)

        socketio.emit('rag_progress', {'stage': 'complete', 'progress': 100, 'total': 100, 'detail': '학습 완료!'})

        # 실제 학습된 이슈 키만 추출
        trained_issue_keys = [doc['id'] for doc in documents]

        # 상세 결과 구성
        result = {
            'success': True,
            'message': f'✅ Bug RAG 학습 완료! {len(documents)}개 이슈 학습됨',
            'model_path': model_path,
            'model_name': model_name,
            'bug_count': len(documents),
            'documents_processed': len(documents),
            'issue_keys': trained_issue_keys,  # ← 실제 학습된 이슈만
            'labels_summary': labels_summary,
            'top_labels': sorted(labels_summary.items(), key=lambda x: x[1], reverse=True)[:10],
            'timestamp': datetime.now().isoformat()
        }

        # [호출] 메모리/히스토리 기록
        dashboard_data['last_rag_result'] = result
        dashboard_data['rag_training_history'].append(result)

        # [호출] 프런트에 최종 결과 전송
        socketio.emit('rag_complete', result)

        # 🔥 학습 완료 후 웹 핸들러에 새 모델 로드
        if 'web_handler' in globals() and hasattr(web_handler, 'load_latest_rag_model'):
            print("🔄 웹 핸들러에 새 RAG 모델 로드 중...")
            web_handler.load_latest_rag_model()

        # [호출] 상태 업데이트
        module_status['rag_learning']['status'] = 'completed'
        module_status['rag_learning']['process'] = None

        return result

    except Exception as e:
        error_result = {
            'success': False,
            'message': f'RAG 학습 실패: {str(e)}',
            'timestamp': datetime.now().isoformat()
        }

        # [호출] 실패 이력 적재/전송
        dashboard_data['rag_training_history'].append(error_result)
        socketio.emit('rag_error', error_result)

        module_status['rag_learning']['status'] = 'failed'
        module_status['rag_learning']['process'] = None

        return error_result


# 파일 모니터링 시작
def start_file_monitoring(watch_dir="logs"):
    """파일 모니터링 시작"""
    global web_handler, observer

    if not os.path.exists(watch_dir):
        os.makedirs(watch_dir)

    if not hasattr(start_file_monitoring, 'started'):
        # [호출] 파일 변경 감시 핸들러/옵저버 구성
        web_handler = WebDashboardHandler(watch_dir)
        observer = Observer()
        # [호출] 디렉터리 감시 등록
        observer.schedule(web_handler, watch_dir, recursive=True)
        # [호출] 감시 스레드 시작
        observer.start()
        start_file_monitoring.started = True
        print(f"✅ 파일 모니터링 시작: {watch_dir}")


# Flask 라우트들
@app.route('/')
def index():
    """메인 페이지"""
    # [호출] dashboard.html 렌더링 (템플릿은 사전에 준비되어 있어야 함)
    return render_template('dashboard.html')


@app.route('/api/stats')
def get_stats():
    """통계 정보 API"""
    return jsonify({
        'total_logs': dashboard_data['total_logs'],
        'error_logs': dashboard_data['error_logs'],
        'error_rate': (dashboard_data['error_logs'] / max(dashboard_data['total_logs'], 1)) * 100,
        'cluster_count': len(dashboard_data['clusters']),
    })


@app.route('/api/rag-history')
def get_rag_history():
    """RAG 학습 이력/최근 결과"""
    last = dashboard_data['last_rag_result'] or {}
    return jsonify({
        'history': list(dashboard_data['rag_training_history']),
        'last_result': last,
        'issue_keys': last.get('issue_keys', [])
    })


@app.route('/api/clusters')
def get_clusters():
    """클러스터 정보 API"""
    clusters = []
    for cluster_id, cluster_info in dashboard_data['clusters'].items():
        cluster_data = {
            'id': cluster_id,
            'template': cluster_info['template'],
            'count': cluster_info['count'],
            'severity': cluster_info['severity'],
            'last_seen': cluster_info['last_seen'],
            'first_seen': cluster_info['first_seen'],
            'ai_analysis': cluster_info.get('ai_analysis')
        }
        clusters.append(cluster_data)

    clusters.sort(key=lambda x: x['count'], reverse=True)
    return jsonify(clusters)


@app.route('/api/recent-logs')
def get_recent_logs():
    """최근 로그 API"""
    return jsonify(list(dashboard_data['recent_logs']))


@app.route('/api/ssh-logs')
def get_ssh_logs():
    """SSH 로그 API"""
    return jsonify(list(dashboard_data['ssh_logs']))


@app.route('/api/error-timeline')
def get_error_timeline():
    """에러 타임라인 API"""
    return jsonify(list(dashboard_data['error_timeline']))


@app.route('/api/ai-analyses')
def get_ai_analyses():
    """AI 분석 결과 API"""
    return jsonify(list(dashboard_data['ai_analyses']))


@app.route('/api/system-info')
def get_system_info():
    """시스템 정보 API"""
    try:
        # [호출] 시스템 리소스 측정
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        return jsonify({
            'cpu_percent': round(cpu_percent, 1),
            'memory_percent': round(memory.percent, 1),
            'disk_usage': round(disk.percent, 1),
            'active_processes': len(psutil.pids()),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/module-status')
def get_module_status():
    """모듈 상태 API"""
    return jsonify({
        'log_monitoring': {
            'status': 'running',
            'description': '웹 대시보드 실행 중'
        },
        'ssh_connection': {
            'status': module_status['ssh_connection']['status'],
            'description': f"SSH 연결 {module_status['ssh_connection']['status']}",
            'log_path': module_status['ssh_connection']['log_path'],
            'host': module_status['ssh_connection']['host']
        },
        'rag_learning': {
            'status': module_status['rag_learning']['status'],
            'description': f"RAG 학습 {module_status['rag_learning']['status']}",
            'progress': module_status['rag_learning']['progress'],
            'jira_available': JIRA_AVAILABLE,
            'trainer_available': RAG_TRAINER_AVAILABLE
        },
        'ai_analyzer': {
            'status': module_status['ai_analyzer']['status'],
            'enabled': module_status['ai_analyzer']['enabled'],
            'last_analysis': module_status['ai_analyzer']['last_analysis'],
            'description': f"AI 분석기 {module_status['ai_analyzer']['status']}"
        }
    })


@app.route('/api/start-ssh', methods=['POST'])
def start_ssh():
    """SSH 연결 시작 (로그 파일 지정 포함)"""
    try:
        data = request.get_json()
        host = data.get('host', 'localhost')
        username = data.get('username', 'user')
        password = data.get('password', '')
        log_path = data.get('log_path', '/var/log/application.log')

        if module_status['ssh_connection']['process']:
            return jsonify({'error': 'SSH 연결이 이미 활성화되어 있습니다'}), 400
        if not host or not username or not log_path:
            return jsonify({'error': '호스트, 사용자명, 로그 경로를 모두 입력하세요'}), 400

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        # [호출] SSH 접속
        client.connect(host, username=username, password=password, timeout=10)

        # [호출] 로그 경로 존재 여부 확인
        stdin, stdout, stderr = client.exec_command(f'ls -la {log_path}')
        output = stdout.read().decode().strip()
        error_output = stderr.read().decode().strip()

        if error_output and ('No such file' in error_output or 'cannot access' in error_output):
            client.close()
            return jsonify({'error': f'로그 파일을 찾을 수 없습니다: {log_path}'}), 400

        # 상태 저장
        module_status['ssh_connection']['status'] = 'connected'
        module_status['ssh_connection']['process'] = client
        module_status['ssh_connection']['log_path'] = log_path
        module_status['ssh_connection']['host'] = host
        module_status['ssh_connection']['username'] = username

        # [호출] SSH 로그 모니터링 스레드 시작
        threading.Thread(target=monitor_ssh_logs, args=(client, log_path), daemon=True).start()

        return jsonify({
            'message': f'{host}에 SSH 연결 성공',
            'log_path': log_path,
            'file_info': output
        })
    except Exception as e:
        return jsonify({'error': f'SSH 연결 실패: {str(e)}'}), 500


@app.route('/api/stop-ssh', methods=['POST'])
def stop_ssh():
    """SSH 연결 종료"""
    try:
        if module_status['ssh_connection']['process']:
            # [호출] SSH 세션 종료
            module_status['ssh_connection']['process'].close()

        module_status['ssh_connection']['status'] = 'disconnected'
        module_status['ssh_connection']['process'] = None
        module_status['ssh_connection']['log_path'] = None
        module_status['ssh_connection']['host'] = None

        # [호출] SSH 로그 버퍼 초기화
        dashboard_data['ssh_logs'].clear()

        return jsonify({'message': 'SSH 연결이 종료되었습니다'})
    except Exception as e:
        return jsonify({'error': f'SSH 연결 종료 실패: {str(e)}'}), 500


@app.route('/api/start-rag', methods=['POST'])
def start_rag():
    """RAG 학습 시작 (실제 Jira 연동)"""
    try:
        data = request.get_json() or {}
        model_name = data.get('model_name', 'sentence-transformers/all-MiniLM-L6-v2')
        max_results = data.get('max_results', 20)

        if module_status['rag_learning']['process']:
            return jsonify({'error': 'RAG 학습이 이미 진행 중입니다'}), 400
        if not JIRA_AVAILABLE:
            return jsonify({'error': 'Jira 연동이 설정되지 않았습니다. .env 파일의 JIRA 설정을 확인하세요.'}), 400
        if not RAG_TRAINER_AVAILABLE:
            return jsonify({'error': 'RAG 학습 모듈이 설정되지 않았습니다. rag_trainer 모듈을 확인하세요.'}), 400

        # [호출] 비동기 학습 스레드 시작
        process = threading.Thread(
            target=rag_learning_process,
            kwargs={'model_name': model_name, 'max_results': max_results},
            daemon=True
        )
        process.start()

        module_status['rag_learning']['process'] = process
        module_status['rag_learning']['status'] = 'training'

        return jsonify({
            'message': f'RAG 학습을 시작했습니다 (모델: {model_name}, 최대: {max_results}개)',
            'model_name': model_name,
            'max_results': max_results
        })
    except Exception as e:
        return jsonify({'error': f'RAG 학습 시작 실패: {str(e)}'}), 500


@app.route('/api/stop-rag', methods=['POST'])
def stop_rag():
    """RAG 학습 중지 (소프트 플래그)"""
    try:
        if module_status['rag_learning']['process']:
            # [호출] 상태만 변경(실제 중단 로직은 트레이너/스레드 내부 구현 필요)
            module_status['rag_learning']['status'] = 'stopped'
            module_status['rag_learning']['process'] = None
            module_status['rag_learning']['progress'] = {
                'stage': '중지됨',
                'current': 0,
                'total': 5,
                'message': '사용자에 의해 중지되었습니다.'
            }
        return jsonify({'message': 'RAG 학습이 중지되었습니다'})
    except Exception as e:
        return jsonify({'error': f'RAG 학습 중지 실패: {str(e)}'}), 500


# 정기 상태 체크
def check_module_status():
    """모듈 상태 정기 체크"""
    while True:
        try:
            # RAG 프로세스 상태 체크
            if module_status['rag_learning']['process']:
                if not module_status['rag_learning']['process'].is_alive():
                    if module_status['rag_learning']['status'] not in ['completed', 'failed']:
                        module_status['rag_learning']['status'] = 'completed'
                    module_status['rag_learning']['process'] = None

            # SSH 연결 상태 체크
            if module_status['ssh_connection']['process']:
                try:
                    # [호출] 간단 keep-alive
                    stdin, stdout, stderr = module_status['ssh_connection']['process'].exec_command('echo "alive"', timeout=5)
                    stdout.read()
                except:
                    module_status['ssh_connection']['status'] = 'disconnected'
                    module_status['ssh_connection']['process'] = None
                    module_status['ssh_connection']['log_path'] = None

            time.sleep(5)
        except Exception as e:
            print(f"상태 체크 오류: {e}")


# Socket.IO 이벤트 핸들러
@socketio.on('connect')
def handle_connect():
    print('클라이언트 연결됨')
    # [호출] 연결 상태 전달
    emit('status', {'message': '대시보드에 연결되었습니다'})


@socketio.on('disconnect')
def handle_disconnect():
    print('클라이언트 연결 해제됨')


@socketio.on('request_update')
def handle_request_update():
    """클라이언트 업데이트 요청 처리"""
    # [호출] 대시보드 요약 전송
    emit('dashboard_update', {
        'total_logs': dashboard_data['total_logs'],
        'error_logs': dashboard_data['error_logs'],
        'cluster_count': len(dashboard_data['clusters'])
    })

# HTML 템플릿 생성
def create_templates():
    """HTML 템플릿 디렉토리 및 파일 생성"""
    templates_dir = 'templates'
    if not os.path.exists(templates_dir):
        os.makedirs(templates_dir)

    html_content = '''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>통합 모니터링 대시보드</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #f5f5f5;
            color: #333;
            overflow-x: hidden;
        }
        
        /* 사이드바 스타일 */
        .sidebar {
            position: fixed;
            left: 0;
            top: 0;
            width: 280px;
            height: 100vh;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            z-index: 1000;
            transform: translateX(-280px);
            transition: transform 0.3s ease;
            overflow-y: auto;
        }
        
        .sidebar.active {
            transform: translateX(0);
        }
        
        .sidebar-header {
            padding: 20px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .sidebar-header h2 {
            font-size: 1.5rem;
            margin-bottom: 5px;
        }
        
        .sidebar-header p {
            font-size: 0.9rem;
            opacity: 0.8;
        }
        
        .sidebar-menu {
            padding: 20px 0;
        }
        
        .menu-item {
            display: block;
            padding: 15px 20px;
            color: white;
            text-decoration: none;
            transition: all 0.3s ease;
            border-left: 4px solid transparent;
        }
        
        .menu-item:hover, .menu-item.active {
            background: rgba(255, 255, 255, 0.1);
            border-left-color: #ffd700;
        }
        
        .menu-item i {
            margin-right: 10px;
            font-size: 1.2rem;
        }
        
        .menu-item .status-dot {
            float: right;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-top: 4px;
        }
        
        .status-running { background-color: #28a745; }
        .status-stopped { background-color: #dc3545; }
        .status-connected { background-color: #28a745; }
        .status-disconnected { background-color: #dc3545; }
        .status-training { background-color: #17a2b8; }
        .status-completed { background-color: #28a745; }
        .status-failed { background-color: #dc3545; }
        
        /* 햄버거 메뉴 버튼 */
        .menu-toggle {
            position: fixed;
            top: 20px;
            left: 20px;
            z-index: 1001;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            width: 50px;
            height: 50px;
            border-radius: 50%;
            cursor: pointer;
            font-size: 1.5rem;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            transition: all 0.3s ease;
        }
        
        .menu-toggle:hover {
            transform: scale(1.1);
        }
        
        /* 메인 콘텐츠 영역 */
        .main-content {
            margin-left: 0;
            transition: margin-left 0.3s ease;
            min-height: 100vh;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        
        .main-content.sidebar-open {
            margin-left: 280px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 80px 20px 20px 20px;
        }
        
        .page-header {
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }
        
        .page-header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .page-header p {
            font-size: 1.2em;
            opacity: 0.9;
        }
        
        /* 페이지 콘텐츠 */
        .page-content {
            display: none;
        }
        
        .page-content.active {
            display: block;
        }
        
        /* 통계 카드 */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            text-align: center;
            transition: transform 0.3s ease;
        }
        
        .stat-card:hover {
            transform: translateY(-5px);
        }
        
        .stat-card h3 {
            font-size: 2.5em;
            margin-bottom: 10px;
            color: #667eea;
        }
        
        .stat-card p {
            font-size: 1.1em;
            color: #666;
        }
        
        /* 패널 */
        .main-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 30px;
        }
        
        .panel {
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }
        
        .panel h2 {
            margin-bottom: 20px;
            color: #333;
            border-bottom: 3px solid #667eea;
            padding-bottom: 10px;
        }
        
        /* 로그 엔트리 */
        .log-entry {
            padding: 10px;
            margin: 5px 0;
            border-radius: 8px;
            border-left: 4px solid #ddd;
            background: #f8f9fa;
        }
        
        .log-entry.error {
            border-left-color: #dc3545;
            background: #fff5f5;
        }
        
        .log-entry.info {
            border-left-color: #28a745;
            background: #f0fff4;
        }
        
        .log-timestamp {
            font-size: 0.8em;
            color: #666;
            margin-bottom: 5px;
        }
        
        .log-content {
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }
        
        /* 클러스터 */
        .cluster-item {
            padding: 15px;
            margin: 10px 0;
            border-radius: 10px;
            background: #f8f9fa;
            border-left: 5px solid #667eea;
        }
        
        .cluster-template {
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            margin: 5px 0;
            color: #333;
        }
        
        .cluster-count {
            font-weight: bold;
            color: #667eea;
        }
        
        .severity-critical {
            border-left-color: #dc3545;
            background: #fff5f5;
        }
        
        .severity-warning {
            border-left-color: #ffc107;
            background: #fffbf0;
        }
        
        .severity-info {
            border-left-color: #17a2b8;
            background: #f0f9ff;
        }
        
        /* 폼 요소 */
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #333;
        }
        
        .form-group input, .form-group select {
            width: 100%;
            padding: 12px;
            border: 2px solid #ddd;
            border-radius: 8px;
            font-size: 1rem;
            transition: border-color 0.3s ease;
        }
        
        .form-group input:focus, .form-group select:focus {
            border-color: #667eea;
            outline: none;
        }
        
        /* 버튼 */
        .btn {
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 1rem;
            transition: all 0.3s ease;
            margin: 5px;
        }
        
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
        }
        
        .btn:disabled {
            background: #6c757d;
            cursor: not-allowed;
            transform: none;
        }
        
        .btn-danger {
            background: linear-gradient(45deg, #dc3545, #c82333);
        }
        
        .btn-success {
            background: linear-gradient(45deg, #28a745, #218838);
        }
        
        /* 빠른 템플릿 스타일 */
        .quick-template {
            padding: 15px;
            border: 2px solid #ddd;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s ease;
            background: white;
        }
        
        .quick-template:hover {
            border-color: #667eea;
            background: #f0f9ff;
            transform: translateY(-2px);
        }
        
        .quick-template h4 {
            margin-bottom: 8px;
            color: #333;
        }
        
        .quick-template p {
            color: #667eea;
            font-weight: 600;
            margin: 5px 0;
        }
        
        .quick-template small {
            color: #666;
        }
        
        /* 차트 */
        .chart-container {
            position: relative;
            height: 300px;
            margin-top: 20px;
        }
        
        .full-width {
            grid-column: 1 / -1;
        }
        
        /* 알림 */
        .notification {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 15px 20px;
            background: #28a745;
            color: white;
            border-radius: 8px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
            transform: translateX(120%);
            transition: transform 0.3s ease;
            z-index: 1000;
        }
        
        .notification.show {
            transform: translateX(0);
        }
        
        .notification.error {
            background: #dc3545;
        }
        
        /* 진행률 표시 */
        .progress-container {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
            margin: 15px 0;
        }
        
        .progress-bar {
            width: 100%;
            height: 20px;
            background: #e9ecef;
            border-radius: 10px;
            overflow: hidden;
        }
        
        .progress-bar-fill {
            height: 100%;
            background: linear-gradient(45deg, #667eea, #764ba2);
            transition: width 0.3s ease;
        }
        
        .progress-text {
            margin-top: 10px;
            font-size: 0.9rem;
            color: #666;
        }
        
        /* 반응형 */
        @media (max-width: 768px) {
            .main-grid {
                grid-template-columns: 1fr;
            }
            
            .stats-grid {
                grid-template-columns: 1fr;
            }
            
            .sidebar {
                width: 250px;
                transform: translateX(-250px);
            }
            
            .main-content.sidebar-open {
                margin-left: 250px;
            }
        }
        
        @media (max-width: 480px) {
            .sidebar {
                width: 100%;
                transform: translateX(-100%);
            }
            
            .main-content.sidebar-open {
                margin-left: 0;
            }
            
            .container {
                padding: 80px 10px 20px 10px;
            }
        }
        
        /* 진행률 표시 */
        .progress-container {
            background: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
            margin: 15px 0;
        }
        
        /* 🔥 아래 CSS 추가 */
        .label-item {
            display: flex;
            align-items: center;
            margin-bottom: 10px;
            padding: 8px;
            background: white;
            border-radius: 5px;
            border-left: 4px solid #667eea;
        }
        
        .label-name {
            flex: 0 0 200px;
            font-weight: 600;
            color: #333;
        }
        
        .label-bar-container {
            flex: 1;
            height: 20px;
            background: #e9ecef;
            border-radius: 10px;
            overflow: hidden;
            margin: 0 10px;
        }
        
        .label-bar {
            height: 100%;
            background: linear-gradient(45deg, #667eea, #764ba2);
            transition: width 0.5s ease;
        }
        
        .label-count {
            flex: 0 0 60px;
            text-align: right;
            font-weight: bold;
            color: #667eea;
        }
        
        .history-item {
            padding: 15px;
            margin: 10px 0;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #28a745;
        }
        
        .history-item.failed {
            border-left-color: #dc3545;
        }
    </style>
</head>
<body>
    <!-- 햄버거 메뉴 버튼 -->
    <button class="menu-toggle" onclick="toggleSidebar()">☰</button>
    
    <!-- 사이드바 -->
    <nav class="sidebar" id="sidebar">
        <div class="sidebar-header">
            <h2>🎛️ 통합 대시보드</h2>
            <p>모니터링 & 관리</p>
        </div>
        <div class="sidebar-menu">
            <a href="#" class="menu-item active" onclick="showPage('log-monitoring')" data-page="log-monitoring">
                📊 로그 모니터링
                <span class="status-dot status-running" id="log-status-dot"></span>
            </a>
            <a href="#" class="menu-item" onclick="showPage('rag-learning')" data-page="rag-learning">
                🧠 RAG 학습
                <span class="status-dot status-stopped" id="rag-status-dot"></span>
            </a>
            <a href="#" class="menu-item" onclick="showPage('ssh-connection')" data-page="ssh-connection">
                🔒 SSH 연결
                <span class="status-dot status-disconnected" id="ssh-status-dot"></span>
            </a>
            <a href="#" class="menu-item" onclick="showPage('system-info')" data-page="system-info">
                ⚙️ 시스템 정보
            </a>
        </div>
    </nav>

    <!-- 메인 콘텐츠 -->
    <main class="main-content" id="main-content">
        <div class="container">
            <!-- 로그 모니터링 페이지 -->
            <div class="page-content active" id="log-monitoring-page">
                <div class="page-header">
                    <h1>📊 로그 모니터링 대시보드</h1>
                    <p>실시간 로그 클러스터링 및 에러 패턴 감지</p>
                </div>
                
                <div class="stats-grid">
                    <div class="stat-card">
                        <h3 id="total-logs">0</h3>
                        <p>총 로그 수</p>
                    </div>
                    <div class="stat-card">
                        <h3 id="error-logs">0</h3>
                        <p>에러 로그 수</p>
                    </div>
                    <div class="stat-card">
                        <h3 id="error-rate">0%</h3>
                        <p>에러율</p>
                    </div>
                    <div class="stat-card">
                        <h3 id="cluster-count">0</h3>
                        <p>발견된 패턴</p>
                    </div>
                </div>
                
                <div class="main-grid">
                    <div class="panel">
                        <h2>📋 최근 로그</h2>
                        <div id="recent-logs">
                            <p>로그를 기다리는 중...</p>
                        </div>
                    </div>
                    
                    <div class="panel">
                        <h2>🏷️ 에러 패턴 클러스터</h2>
                        <div id="clusters">
                            <p>클러스터를 기다리는 중...</p>
                        </div>
                    </div>
                </div>
                
                <div class="panel full-width">
                    <h2>📈 에러 발생 타임라인</h2>
                    <div class="chart-container">
                        <canvas id="timeline-chart"></canvas>
                    </div>
                </div>
            </div>

<!-- RAG 학습 페이지 -->
            <div class="page-content" id="rag-learning-page">
                <div class="page-header">
                    <h1>🧠 RAG 학습</h1>
                    <p>검색 증강 생성 모델 학습 및 관리 (Jira 연동)</p>
                </div>
                
                <div class="panel">
                    <h2>학습 설정</h2>

                    <div class="form-group">
                        <label>임베딩 모델:</label>
                        <select id="rag-model">
                            <option value="sentence-transformers/all-MiniLM-L6-v2">all-MiniLM-L6-v2 (빠름)</option>
                            <option value="sentence-transformers/all-mpnet-base-v2">all-mpnet-base-v2 (고성능)</option>
                            <option value="sentence-transformers/distilbert-base-nli-stsb-mean-tokens">distilbert (균형)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>최대 이슈 수:</label>
                        <input type="number" id="rag-max-results" placeholder="5" value="5" min="1" max="100">
                    </div>
                    
                    <div style="margin-top: 20px;">
                        <button class="btn" id="start-rag-btn" onclick="startRAG()">학습 시작</button>
                        <button class="btn btn-danger" id="stop-rag-btn" onclick="stopRAG()" disabled>학습 중지</button>
                    </div>
                    
                    <div id="rag-info" style="margin-top: 15px; padding: 15px; background: #f8f9fa; border-radius: 8px; font-size: 0.9rem;">
                        <strong>상태:</strong> <span id="rag-status-text">대기 중</span><br>
                        <strong>Jira 연동:</strong> <span id="jira-status">❌ 확인 중...</span><br>
                        <strong>RAG 모듈:</strong> <span id="trainer-status">❌ 확인 중...</span>
                    </div>
                    
                    <!-- 진행률 표시 -->
                    <div id="rag-progress-container" class="progress-container" style="display: none;">
                        <div class="progress-bar">
                            <div class="progress-bar-fill" id="rag-progress-bar" style="width: 0%;"></div>
                        </div>
                        <div class="progress-text" id="rag-progress-text">준비 중...</div>
                    </div>
                </div>
                
                <!-- 🔥 학습 결과 패널 (새로 추가) -->
                <div class="panel" id="rag-result-panel" style="display: none;">
                    <h2>📊 마지막 학습 결과</h2>
                    
                    <div style="background: #e8f5e9; padding: 15px; border-radius: 8px; margin-bottom: 15px;">
                        <div style="font-size: 1.1rem; font-weight: bold; color: #2e7d32; margin-bottom: 10px;">
                            ✅ <span id="result-message">학습 완료</span>
                        </div>
                        <div style="font-size: 0.9rem; color: #666;">
                            <strong>학습 시각:</strong> <span id="result-timestamp">-</span><br>
                            <strong>모델:</strong> <span id="result-model">-</span><br>
                            <strong>학습 이슈 수:</strong> <span id="result-count">0</span>개
                        </div>
                    </div>
                    
                    <!-- 학습된 이슈 목록 -->
                    <div style="margin-bottom: 20px;">
                        <h3 style="font-size: 1rem; margin-bottom: 10px;">📋 학습된 Bug 이슈</h3>
                        <div id="trained-issues" style="max-height: 200px; overflow-y: auto; background: #f8f9fa; padding: 10px; border-radius: 8px; font-family: 'Courier New', monospace; font-size: 0.85rem;">
                            이슈 목록이 표시됩니다...
                        </div>
                        <div id="trained-issues"></div>
                    </div>
                    
                    <!-- 🔥 라벨 분포 -->
                    <div>
                        <h3 style="font-size: 1rem; margin-bottom: 10px;">🏷️ Label 분포 (Top 10)</h3>
                        <div id="labels-distribution" style="background: #f8f9fa; padding: 15px; border-radius: 8px;">
                            라벨 분포가 표시됩니다...
                        </div>
                    </div>
                </div>
                
                <!-- 학습 이력 -->
                <div class="panel">
                    <h2>📜 학습 이력</h2>
                    <div id="rag-history" style="max-height: 300px; overflow-y: auto;">
                        <p style="color: #666;">아직 학습 이력이 없습니다.</p>
                    </div>
                </div>
            </div>

            <!-- SSH 연결 페이지 -->
            <div class="page-content" id="ssh-connection-page">
                <div class="page-header">
                    <h1>🔒 SSH 연결</h1>
                    <p>원격 서버 연결 및 로그 모니터링</p>
                </div>
                
                <div class="main-grid">
                    <div class="panel">
                        <h2>연결 설정</h2>
                        <div class="form-group">
                            <label>호스트 주소:</label>
                            <input type="text" id="ssh-host" placeholder="예: 192.168.1.100" value="localhost">
                        </div>
                        <div class="form-group">
                            <label>사용자명:</label>
                            <input type="text" id="ssh-username" placeholder="사용자명" value="user">
                        </div>
                        <div class="form-group">
                            <label>비밀번호:</label>
                            <input type="password" id="ssh-password" placeholder="비밀번호">
                        </div>
                        <div class="form-group">
                            <label>로그 파일 경로:</label>
                            <input type="text" id="ssh-log-path" placeholder="/var/log/application.log" value="/var/log/application.log">
                            <small style="color: #666; font-size: 0.9em; display: block; margin-top: 5px;">
                                📁 일반적인 로그 경로 예시:<br>
                                • Tomcat: /opt/tomcat/logs/catalina.out<br>
                                • Apache: /var/log/apache2/access.log<br>
                                • Nginx: /var/log/nginx/error.log<br>
                                • 시스템: /var/log/syslog<br>
                                • 애플리케이션: /var/log/myapp/app.log
                            </small>
                        </div>
                        <div style="margin-top: 20px;">
                            <button class="btn" id="start-ssh-btn" onclick="startSSH()">연결 & 모니터링 시작</button>
                            <button class="btn btn-danger" id="stop-ssh-btn" onclick="stopSSH()" disabled>연결 해제</button>
                        </div>
                        <div id="ssh-info" style="margin-top: 15px; padding: 15px; background: #f8f9fa; border-radius: 8px; font-size: 0.9rem;">
                            <strong>상태:</strong> <span id="ssh-status-text">연결 해제됨</span><br>
                            <strong>로그 파일:</strong> <span id="ssh-log-file">-</span>
                        </div>
                    </div>
                    
                    <div class="panel">
                        <h2>📋 SSH 로그 (실시간)</h2>
                        <div id="ssh-logs" style="height: 400px; overflow-y: auto; background: #f8f9fa; padding: 15px; border-radius: 8px; font-family: 'Courier New', monospace; font-size: 0.9em;">
                            <p style="color: #666;">SSH 연결 후 실시간 로그가 여기에 표시됩니다...</p>
                        </div>
                        <div style="margin-top: 10px;">
                            <button class="btn" onclick="clearSSHLogs()" style="background: #6c757d;">로그 지우기</button>
                            <button class="btn" onclick="downloadSSHLogs()" style="background: #17a2b8;">로그 다운로드</button>
                        </div>
                    </div>
                </div>

                <!-- 빠른 연결 템플릿 -->
                <div class="panel full-width">
                    <h2>🚀 빠른 연결 템플릿</h2>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px;">
                        <div class="quick-template" onclick="loadTemplate('tomcat')">
                            <h4>🍅 Tomcat 서버</h4>
                            <p>로그: /opt/tomcat/logs/catalina.out</p>
                            <small>포트: 22, 사용자: tomcat</small>
                        </div>
                        <div class="quick-template" onclick="loadTemplate('apache')">
                            <h4>🌐 Apache 서버</h4>
                            <p>로그: /var/log/apache2/error.log</p>
                            <small>포트: 22, 사용자: www-data</small>
                        </div>
                        <div class="quick-template" onclick="loadTemplate('nginx')">
                            <h4>⚡ Nginx 서버</h4>
                            <p>로그: /var/log/nginx/error.log</p>
                            <small>포트: 22, 사용자: nginx</small>
                        </div>
                        <div class="quick-template" onclick="loadTemplate('system')">
                            <h4>🖥️ 시스템 로그</h4>
                            <p>로그: /var/log/syslog</p>
                            <small>포트: 22, 사용자: root</small>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 시스템 정보 페이지 -->
            <div class="page-content" id="system-info-page">
                <div class="page-header">
                    <h1>⚙️ 시스템 정보</h1>
                    <p>서버 리소스 모니터링</p>
                </div>
                
                <div class="stats-grid">
                    <div class="stat-card">
                        <h3 id="cpu-usage">0%</h3>
                        <p>CPU 사용률</p>
                    </div>
                    <div class="stat-card">
                        <h3 id="memory-usage">0%</h3>
                        <p>메모리 사용률</p>
                    </div>
                    <div class="stat-card">
                        <h3 id="disk-usage">0%</h3>
                        <p>디스크 사용률</p>
                    </div>
                    <div class="stat-card">
                        <h3 id="process-count">0</h3>
                        <p>활성 프로세스</p>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <!-- 알림 -->
    <div class="notification" id="notification"></div>

    <script>
        // Socket.IO 연결
        const socket = io();
        
        // Chart.js 설정
        const ctx = document.getElementById('timeline-chart').getContext('2d');
        const timelineChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: '에러 발생 수',
                    data: [],
                    borderColor: '#dc3545',
                    backgroundColor: 'rgba(220, 53, 69, 0.1)',
                    tension: 0.4,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
        
        // 사이드바 토글
        function toggleSidebar() {
            const sidebar = document.getElementById('sidebar');
            const mainContent = document.getElementById('main-content');
            
            sidebar.classList.toggle('active');
            mainContent.classList.toggle('sidebar-open');
        }
        
        // 페이지 전환
        function showPage(pageName) {
            // 모든 페이지 숨기기
            const pages = document.querySelectorAll('.page-content');
            pages.forEach(page => page.classList.remove('active'));
            
            // 선택된 페이지 표시
            document.getElementById(pageName + '-page').classList.add('active');
            
            // 메뉴 활성화 상태 변경
            const menuItems = document.querySelectorAll('.menu-item');
            menuItems.forEach(item => item.classList.remove('active'));
            document.querySelector(`[data-page="${pageName}"]`).classList.add('active');
            
            // 모바일에서는 사이드바 자동 닫기
            if (window.innerWidth <= 768) {
                toggleSidebar();
            }
        }
        
        // 빠른 템플릿 로드
        function loadTemplate(type) {
            const templates = {
                'tomcat': {
                    username: 'tomcat',
                    log_path: '/opt/tomcat/logs/catalina.out'
                },
                'apache': {
                    username: 'www-data', 
                    log_path: '/var/log/apache2/error.log'
                },
                'nginx': {
                    username: 'nginx',
                    log_path: '/var/log/nginx/error.log'
                },
                'system': {
                    username: 'root',
                    log_path: '/var/log/syslog'
                }
            };
            
            const template = templates[type];
            if (template) {
                document.getElementById('ssh-username').value = template.username;
                document.getElementById('ssh-log-path').value = template.log_path;
                showNotification(`${type.toUpperCase()} 템플릿 로드됨`);
            }
        }
        
        // Socket 이벤트 처리
        socket.on('connect', function() {
            console.log('대시보드에 연결됨');
            updateStats();
            updateClusters();
            updateRecentLogs();
            updateTimeline();
            updateModuleStatus();
        });
        
        socket.on('ai_analysis_complete', function(data) {
            console.log('AI 분석 완료:', data);
            updateClusters();
            showNotification(`🤖 AI 분석 완료: ${data.template.substring(0, 50)}...`);
        });
        
        socket.on('ssh_log_update', function(data) {
            console.log('새 SSH 로그:', data);
            updateSSHLogs();
        });
        
        socket.on('rag_progress', function(data) {
            console.log('RAG 진행상황:', data);
            updateRAGProgress(data.stage, data.progress, data.total);
            if (data.detail) {
                document.getElementById('rag-progress-text').textContent += ` - ${data.detail}`;
            }
        });
        
        socket.on('rag_complete', function(data) {
            console.log('RAG 완료:', data);
            showNotification(data.message);
            hideRAGProgress();
            updateModuleStatus();
            
            displayRAGResult(data);
            updateRAGHistory();  // 🔥 이력 새로고침
        });
        
        socket.on('rag_error', function(data) {
            console.log('RAG 에러:', data);
            showNotification(data.message, true);
            hideRAGProgress();
            updateModuleStatus();
            updateRAGHistory();  // 🔥 실패 시에도 이력 새로고침
        });
        
        // 🔥 이 함수들을 stopRAG() 함수 아래에 추가
        function displayRAGResult(result) {
            const panel = document.getElementById('rag-result-panel');
            panel.style.display = 'block';
            
            document.getElementById('result-message').textContent = result.message;
            document.getElementById('result-timestamp').textContent = new Date().toLocaleString();
            document.getElementById('result-model').textContent = result.model_path ? result.model_path.split('/').pop() : 'Unknown';
            document.getElementById('result-count').textContent = result.bug_count || 0;
            
            // 이슈 목록
            const issuesContainer = document.getElementById('trained-issues');
            if (result.issue_keys && result.issue_keys.length > 0) {
                issuesContainer.innerHTML = result.issue_keys.map(key => 
                    `<div style="padding: 5px; border-bottom: 1px solid #dee2e6;">${key}</div>`
                ).join('');
            }
            
            // 라벨 분포
            const labelsContainer = document.getElementById('labels-distribution');
            if (result.top_labels && result.top_labels.length > 0) {
                const maxCount = result.top_labels[0][1];
                labelsContainer.innerHTML = result.top_labels.map(([label, count]) => {
                    const percentage = (count / maxCount) * 100;
                    return `
                        <div class="label-item">
                            <div class="label-name">${label}</div>
                            <div class="label-bar-container">
                                <div class="label-bar" style="width: ${percentage}%;"></div>
                            </div>
                            <div class="label-count">${count}개</div>
                        </div>
                    `;
                }).join('');
            }
        }
        
        async function updateRAGHistory() {
            try {
                const response = await fetch('/api/rag-history');
                const data = await response.json();
                const container = document.getElementById('rag-history');
                
                if (!data.history || data.history.length === 0) {
                    container.innerHTML = '<p style="color: #666;">아직 학습 이력이 없습니다.</p>';
                    return;
                }
                
                // 🔥 최신순 정렬 (reverse 사용)
                const sortedHistory = [...data.history].reverse();
                
                container.innerHTML = sortedHistory.map(item => {
                    const timestamp = item.timestamp ? new Date(item.timestamp).toLocaleString('ko-KR') : '알 수 없음';
                    const isSuccess = item.success !== false;
                    
                    return `
                        <div class="history-item ${isSuccess ? '' : 'failed'}">
                            <div style="font-weight: bold; margin-bottom: 5px;">
                                ${isSuccess ? '✅' : '❌'} ${timestamp}
                            </div>
                            <div style="font-size: 0.9rem; color: #666;">
                                ${isSuccess ? `
                                    모델: ${item.model_name || 'Unknown'}<br>
                                    학습 이슈: ${item.bug_count || 0}개<br>
                                    라벨 종류: ${Object.keys(item.labels_summary || {}).length}개
                                    ${Array.isArray(item.issue_keys) && item.issue_keys.length > 0
                                        ? `
                                          <div style="margin-top:8px;">
                                            <strong>이슈 키 (${item.issue_keys.length}개):</strong>
                                            <div style="max-height:140px; overflow:auto; background:#f8f9fa; border:1px solid #dee2e6; border-radius:6px; padding:6px; font-family:'Courier New', monospace; font-size:0.85rem;">
                                              ${item.issue_keys.slice(0, 10).map(k =>
                                                `<div style="padding:2px 4px; border-bottom:1px solid #eee;">${k}</div>`
                                              ).join('')}
                                              ${item.issue_keys.length > 10
                                                ? `<div style="padding:6px; color:#667eea; font-weight:600;">+ ${item.issue_keys.length - 10} more</div>`
                                                : ''}
                                            </div>
                                          </div>`
                                        : `<div style="margin-top:8px; color:#aaa;">이슈 키 없음</div>`
                                      }
                                ` : `
                                    오류: ${item.message || '알 수 없는 오류'}
                                `}
                            </div>
                        </div>
                    `;
                }).join('');
            } catch (error) {
                console.error('학습 이력 조회 실패:', error);
                document.getElementById('rag-history').innerHTML = 
                    '<p style="color: #dc3545;">학습 이력 조회 중 오류가 발생했습니다.</p>';
            }
        }
        
        // 데이터 업데이트 함수들
        function updateStats() {
            fetch('/api/stats')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('total-logs').textContent = data.total_logs.toLocaleString();
                    document.getElementById('error-logs').textContent = data.error_logs.toLocaleString();
                    document.getElementById('error-rate').textContent = data.error_rate.toFixed(1) + '%';
                    document.getElementById('cluster-count').textContent = data.cluster_count;
                });
        }
        
        function updateClusters() {
            fetch('/api/clusters')
                .then(response => response.json())
                .then(data => {
                    const container = document.getElementById('clusters');
                    if (data.length === 0) {
                        container.innerHTML = '<p>아직 에러 패턴이 발견되지 않았습니다.</p>';
                        return;
                    }
                    
                    container.innerHTML = data.map(cluster => {
                        const analysis = cluster.ai_analysis;
                        const isRAG = analysis && analysis.source === 'RAG';
                        
                        return `
                            <div class="cluster-item severity-${getSeverityClass(cluster.severity)}">
                                <div class="cluster-count">${cluster.count}회 발생</div>
                                <div class="cluster-template">${cluster.template}</div>
                                <div style="font-size: 0.8em; color: #666; margin-top: 5px;">
                                    마지막: ${new Date(cluster.last_seen).toLocaleString()}
                                </div>
                                ${analysis ? `
                                    <div style="margin-top: 10px; padding: 10px; background: ${isRAG ? '#f0fff4' : '#f0f8ff'}; border-radius: 5px; border-left: 3px solid ${isRAG ? '#28a745' : '#007bff'};">
                                        <div style="font-weight: bold; color: ${isRAG ? '#28a745' : '#007bff'}; margin-bottom: 5px;">
                                            ${isRAG ? '🔍 RAG 지식베이스 매칭' : '🤖 AI 분석 결과'} 
                                            (신뢰도: ${analysis.confidence}%)
                                        </div>
                                        <div style="font-size: 0.85em;">
                                            ${isRAG ? `
                                                <div><strong>유사 이슈:</strong> ${analysis.issue_key} (유사도: ${(analysis.similarity * 100).toFixed(1)}%)</div>
                                                <div><strong>에러 유형:</strong> ${analysis.error_type}</div>
                                                <div><strong>상태:</strong> ${analysis.status}</div>
                                                <div><strong>우선순위:</strong> ${analysis.severity}</div>
                                                ${analysis.labels && analysis.labels.length > 0 ? `
                                                    <div><strong>라벨:</strong> ${analysis.labels.join(', ')}</div>
                                                ` : ''}
                                                <div style="margin-top: 5px;">
                                                    <strong>조치사항:</strong>
                                                    <ul style="margin: 2px 0; padding-left: 15px;">
                                                        ${analysis.immediate_actions.map(action => `<li>${action}</li>`).join('')}
                                                    </ul>
                                                </div>
                                                ${analysis.related_issues && analysis.related_issues.length > 0 ? `
                                                    <div style="margin-top: 5px;">
                                                        <strong>관련 이슈:</strong>
                                                        <ul style="margin: 2px 0; padding-left: 15px;">
                                                            ${analysis.related_issues.map(ri => 
                                                                `<li>${ri.issue_key} (${(ri.similarity * 100).toFixed(1)}%) - ${ri.summary || 'N/A'}</li>`
                                                            ).join('')}
                                                        </ul>
                                                    </div>
                                                ` : ''}
                                            ` : `
                                                <div><strong>에러 유형:</strong> ${analysis.error_type}</div>
                                                <div><strong>심각도:</strong> ${analysis.severity}</div>
                                                <div><strong>근본 원인:</strong> ${analysis.root_cause}</div>
                                                <div style="margin-top: 5px;">
                                                    <strong>즉시 조치사항:</strong>
                                                    <ul style="margin: 2px 0; padding-left: 15px;">
                                                        ${analysis.immediate_actions.map(action => `<li>${action}</li>`).join('')}
                                                    </ul>
                                                </div>
                                            `}
                                        </div>
                                    </div>
                                ` : ''}
                            </div>
                        `;
                    }).join('');
                });
        }
        
        function updateRecentLogs() {
            fetch('/api/recent-logs')
                .then(response => response.json())
                .then(data => {
                    const container = document.getElementById('recent-logs');
                    if (data.length === 0) {
                        container.innerHTML = '<p>아직 로그가 없습니다.</p>';
                        return;
                    }
                    
                    container.innerHTML = data.slice(-10).reverse().map(log => `
                        <div class="log-entry ${log.type}">
                            <div class="log-timestamp">${new Date(log.timestamp).toLocaleString()}</div>
                            <div class="log-content">${log.content}</div>
                        </div>
                    `).join('');
                });
        }
        
        function updateSSHLogs() {
            fetch('/api/ssh-logs')
                .then(response => response.json())
                .then(data => {
                    const container = document.getElementById('ssh-logs');
                    if (data.length === 0) {
                        container.innerHTML = '<p style="color: #666;">SSH 연결 후 실시간 로그가 여기에 표시됩니다...</p>';
                        return;
                    }
                    
                    container.innerHTML = data.slice(-50).reverse().map(log => `
                        <div class="log-entry ${log.type}">
                            <div class="log-timestamp">${new Date(log.timestamp).toLocaleString()}</div>
                            <div class="log-content">${log.content}</div>
                        </div>
                    `).join('');
                    
                    // 자동 스크롤
                    container.scrollTop = 0;
                });
        }
        
        function updateTimeline() {
            fetch('/api/error-timeline')
                .then(response => response.json())
                .then(data => {
                    const labels = data.map(item => new Date(item.timestamp).toLocaleTimeString());
                    const counts = data.map(item => item.count);
                    
                    timelineChart.data.labels = labels;
                    timelineChart.data.datasets[0].data = counts;
                    timelineChart.update();
                });
        }
        
        function updateModuleStatus() {
            fetch('/api/module-status')
                .then(response => response.json())
                .then(data => {
                    // 상태 점 업데이트
                    updateStatusDot('log-status-dot', 'running');
                    updateStatusDot('rag-status-dot', data.rag_learning.status);
                    updateStatusDot('ssh-status-dot', data.ssh_connection.status);
                    
                    // 상태 텍스트 업데이트
                    updateStatusText('rag-status-text', data.rag_learning.status);
                    updateStatusText('ssh-status-text', data.ssh_connection.status);
                    
                    // RAG 모듈 상태 업데이트
                    document.getElementById('jira-status').textContent = data.rag_learning.jira_available ? '✅ 사용 가능' : '❌ 설정 필요';
                    document.getElementById('trainer-status').textContent = data.rag_learning.trainer_available ? '✅ 사용 가능' : '❌ 설정 필요';
                    
                    // SSH 로그 파일 정보 업데이트
                    if (data.ssh_connection.log_path) {
                        document.getElementById('ssh-log-file').textContent = data.ssh_connection.log_path;
                    }
                    
                    // 버튼 상태 업데이트
                    updateButtons(data);
                    
                    // 🔥 RAG 상태가 'completed' 또는 'failed'로 변경되었을 때 이력 새로고침
                    if (data.rag_learning.status === 'completed' || data.rag_learning.status === 'failed') {
                        updateRAGHistory();
                    }
                });
        }
        
        function updateStatusDot(dotId, status) {
            const dot = document.getElementById(dotId);
            dot.className = `status-dot status-${status}`;
        }
        
        function updateStatusText(textId, status) {
            const text = document.getElementById(textId);
            const statusMap = {
                'running': '실행 중',
                'stopped': '중지됨',
                'connected': '연결됨',
                'disconnected': '연결 해제됨',
                'training': '학습 중',
                'completed': '완료됨',
                'failed': '실패'
            };
            text.textContent = statusMap[status] || status;
        }
        
        function updateButtons(moduleStatus) {
            // RAG 버튼
            const startRagBtn = document.getElementById('start-rag-btn');
            const stopRagBtn = document.getElementById('stop-rag-btn');
            const ragStatus = moduleStatus.rag_learning.status;
            
            startRagBtn.disabled = ragStatus === 'training';
            stopRagBtn.disabled = ragStatus !== 'training';
            
            // SSH 버튼
            const startSshBtn = document.getElementById('start-ssh-btn');
            const stopSshBtn = document.getElementById('stop-ssh-btn');
            const sshStatus = moduleStatus.ssh_connection.status;
            
            startSshBtn.disabled = sshStatus === 'connected' || sshStatus === 'connecting';
            stopSshBtn.disabled = sshStatus === 'disconnected';
        }
        
        function updateSystemInfo() {
            fetch('/api/system-info')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('cpu-usage').textContent = data.cpu_percent + '%';
                    document.getElementById('memory-usage').textContent = data.memory_percent + '%';
                    document.getElementById('disk-usage').textContent = data.disk_usage + '%';
                    document.getElementById('process-count').textContent = data.active_processes;
                });
        }
        
        function getSeverityClass(severity) {
            switch(severity) {
                case '매우 심각': return 'critical';
                case '심각': return 'warning';
                case '주의': return 'info';
                default: return 'info';
            }
        }
        
        function showNotification(message, isError = false) {
            const notification = document.getElementById('notification');
            notification.textContent = message;
            notification.className = `notification ${isError ? 'error' : ''} show`;
            
            setTimeout(() => {
                notification.classList.remove('show');
            }, 5000);
        }
        
        // RAG 진행률 표시 함수들
        function updateRAGProgress(stage, current, total) {
            const container = document.getElementById('rag-progress-container');
            const bar = document.getElementById('rag-progress-bar');
            const text = document.getElementById('rag-progress-text');
            
            container.style.display = 'block';
            const percentage = (current / total) * 100;
            bar.style.width = percentage + '%';
            text.textContent = `${stage} (${current}/${total}) - ${percentage.toFixed(0)}%`;
        }
        
        function hideRAGProgress() {
            const container = document.getElementById('rag-progress-container');
            container.style.display = 'none';
        }
        
        // SSH 기능들
        async function startSSH() {
            try {
                const host = document.getElementById('ssh-host').value;
                const username = document.getElementById('ssh-username').value;
                const password = document.getElementById('ssh-password').value;
                const log_path = document.getElementById('ssh-log-path').value;
                
                if (!host || !username || !log_path) {
                    showNotification('호스트, 사용자명, 로그 경로를 모두 입력하세요', true);
                    return;
                }
                
                const response = await fetch('/api/start-ssh', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ host, username, password, log_path })
                });
                const data = await response.json();
                
                if (response.ok) {
                    showNotification(data.message);
                    document.getElementById('ssh-log-file').textContent = data.log_path;
                    
                    // SSH 로그 컨테이너 초기화
                    document.getElementById('ssh-logs').innerHTML = '<p style="color: #28a745;">🔍 실시간 로그 모니터링 시작...</p>';
                } else {
                    showNotification(data.error, true);
                }
            } catch (error) {
                showNotification('SSH 연결 실패: ' + error.message, true);
            }
        }
        
        async function stopSSH() {
            try {
                const response = await fetch('/api/stop-ssh', { method: 'POST' });
                const data = await response.json();
                
                if (response.ok) {
                    showNotification(data.message);
                    document.getElementById('ssh-log-file').textContent = '-';
                    document.getElementById('ssh-logs').innerHTML = '<p style="color: #666;">SSH 연결 후 실시간 로그가 여기에 표시됩니다...</p>';
                } else {
                    showNotification(data.error, true);
                }
            } catch (error) {
                showNotification('SSH 연결 해제 실패: ' + error.message, true);
            }
        }
        
        function clearSSHLogs() {
            document.getElementById('ssh-logs').innerHTML = '<p style="color: #666;">로그가 지워졌습니다.</p>';
        }
        
        function downloadSSHLogs() {
            const logs = document.getElementById('ssh-logs').textContent;
            const blob = new Blob([logs], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `ssh-logs-${new Date().toISOString().split('T')[0]}.txt`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            showNotification('SSH 로그 다운로드 완료');
        }
        
        // RAG 기능들
        async function startRAG() {
            try {
                const model_name = document.getElementById('rag-model').value || 'sentence-transformers/all-MiniLM-L6-v2';
                const max_results = parseInt(document.getElementById('rag-max-results').value) || 5;
                
                const response = await fetch('/api/start-rag', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model_name, max_results })
                });
                const data = await response.json();
                
                if (response.ok) {
                    showNotification(data.message);
                } else {
                    showNotification(data.error, true);
                }
            } catch (error) {
                showNotification('RAG 학습 시작 실패: ' + error.message, true);
            }
        }
        
        async function stopRAG() {
            try {
                const response = await fetch('/api/stop-rag', { method: 'POST' });
                const data = await response.json();
                
                if (response.ok) {
                    showNotification(data.message);
                    hideRAGProgress();
                } else {
                    showNotification(data.error, true);
                }
            } catch (error) {
                showNotification('RAG 학습 중지 실패: ' + error.message, true);
            }
        }
        
        // 주기적 업데이트
        setInterval(() => {
            updateStats();
            updateClusters();
            updateRecentLogs();
            updateSSHLogs();
            updateTimeline();
            updateModuleStatus();
            updateSystemInfo();
        }, 5000);
        
        // 페이지 로드시 초기화
        window.addEventListener('load', function() {
            updateModuleStatus();
            updateSystemInfo();
            updateRAGHistory();  // 🔥 페이지 로드시 이력 로드
        });
    </script>
</body>
</html>'''

    with open(os.path.join(templates_dir, 'dashboard.html'), 'w', encoding='utf-8') as f:
        f.write(html_content)

    print("✅ HTML 템플릿 생성 완료")

def main():
    """메인 실행 함수"""
    print("🚀 통합 모니터링 대시보드 시작 (리팩토링 - AI 분석 통합)")
    print("=" * 70)

    # 모듈 상태 확인
    print("\n📦 모듈 로드 상태:")
    print(f"  - LogClusteringHandler: {'✅ 로드됨' if CLUSTERING_AVAILABLE else '❌ 없음'}")
    print(f"  - OllamaErrorAnalyzer: {'✅ 로드됨' if OLLAMA_AVAILABLE else '❌ 없음'}")
    print(f"  - Jira 연동: {'✅ 가능' if JIRA_AVAILABLE else '❌ 불가'}")
    print(f"  - RAG Trainer: {'✅ 가능' if RAG_TRAINER_AVAILABLE else '❌ 불가'}")
    print(f"  - Slack 연동: {'✅ 가능' if SLACK_AVAILABLE else '❌ 불가'}")

    # HTML 템플릿 생성
    create_templates()

    # 파일 모니터링 시작
    start_file_monitoring()

    # 상태 체크 스레드 시작
    status_thread = threading.Thread(target=check_module_status, daemon=True)
    status_thread.start()

    print("\n" + "=" * 70)
    print("🌐 웹 대시보드 서버 시작 중...")
    print("=" * 70)
    print("\n📱 브라우저에서 http://localhost:5000 접속하세요")
    print("\n✨ 주요 기능:")
    print("  1. 🎛️  왼쪽 메뉴: RAG 학습, SSH 연결, 시스템 정보")
    print("  2. 🔌 SSH 연결: 원격 서버 로그 실시간 모니터링")
    print("  3. 🤖 AI 분석: 에러 발생 시 자동으로 Ollama AI 분석")
    print("  4. 📊 클러스터링: Drain3로 에러 패턴 자동 그룹화")
    print("  5. 🔔 실시간 알림: Socket.IO로 실시간 업데이트")
    print("\n💡 AI 분석 트리거:")
    print("  - 에러가 3회 이상 발생")
    print("  - 5의 배수로 발생할 때마다 (5회, 10회, 15회...)")
    print("\n🖥️  웹 화면에 표시되는 내용:")
    print("  - 실시간 에러 로그")
    print("  - 에러 패턴 클러스터")
    print("  - 🤖 AI 분석 결과 (에러 유형, 심각도, 근본 원인, 해결방법)")
    print("  - 통계 대시보드")
    print("  - 에러 타임라인 차트")
    print("\n🛑 Ctrl+C로 종료")
    print("=" * 70)

    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\n⏹ 대시보드 서버 종료")
        print("✅ 종료 완료")


if __name__ == "__main__":
    main()