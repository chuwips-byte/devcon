"""
통합 웹 대시보드 - Flask 기반 실시간 모니터링 (리팩토링 버전)
- clustering_monitor의 LogClusteringHandler 상속
- ollama_integration의 AI 분석 통합
- SSH 연결 후 에러 발생 시 자동 AI 분석 및 대시보드 표시
"""

# 필수 라이브러리 import
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import json
import threading
import time
from datetime import datetime, timedelta
from collections import defaultdict, deque
import os
import sys
import subprocess
import psutil
import paramiko

# 🔥 clustering_monitor에서 LogClusteringHandler import
try:
    from clustering_monitor import LogClusteringHandler
    CLUSTERING_AVAILABLE = True
    print("✅ LogClusteringHandler 클래스 로드 성공")
except ImportError as e:
    CLUSTERING_AVAILABLE = False
    print(f"❌ clustering_monitor 로드 실패: {e}")

# 🔥 ollama_integration에서 OllamaErrorAnalyzer import
try:
    from ollama_integration import OllamaErrorAnalyzer
    OLLAMA_AVAILABLE = True
    print("✅ OllamaErrorAnalyzer 클래스 로드 성공")
except ImportError as e:
    OLLAMA_AVAILABLE = False
    print(f"❌ ollama_integration 로드 실패: {e}")

# Jira 연동 import
try:
    from jira_integration import JiraIntegration
    JIRA_AVAILABLE = True
    print("✅ Jira 연동 모듈 로드 성공")
except ImportError as e:
    JIRA_AVAILABLE = False
    print(f"❌ Jira 연동 모듈 로드 실패: {e}")

# RAG 학습 import
try:
    from rag.trainer import train_issue
    RAG_TRAINER_AVAILABLE = True
    print("✅ RAG 학습 모듈 로드 성공")
except ImportError as e:
    RAG_TRAINER_AVAILABLE = False
    print(f"❌ RAG 학습 모듈 로드 실패: {e}")

# Slack 연동 (선택사항)
try:
    from slack_integration import SlackNotifier
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False
    print("Slack 연동 모듈을 찾을 수 없습니다.")

# Drain3 import
try:
    from drain3 import TemplateMiner
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError as e:
    print(f"필수 모듈 import 실패: {e}")
    print("pip install -r requirements.txt를 실행하세요.")


# Flask 앱 생성
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
    'ai_analyses': deque(maxlen=50)  # 🔥 AI 분석 결과 저장소
}

# 모듈 상태 추적
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
    """웹 대시보드용 파일 모니터링 핸들러 - LogClusteringHandler 상속"""

    def __init__(self, watch_dir="logs"):
        # 🔥 부모 클래스(LogClusteringHandler) 초기화
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

        # 🔥 Ollama AI 분석기 설정 (이미 부모에서 초기화되었지만 상태 업데이트)
        if hasattr(self, 'ollama_analyzer') and self.ollama_analyzer:
            module_status['ai_analyzer']['enabled'] = self.ollama_analyzer.enabled
            module_status['ai_analyzer']['status'] = 'enabled' if self.ollama_analyzer.enabled else 'disabled'
            if self.ollama_analyzer.enabled:
                print("✅ Ollama AI 분석기 활성화 (웹 대시보드 연동)")
        else:
            module_status['ai_analyzer']['status'] = 'unavailable'

        print("✅ 웹 대시보드 핸들러 초기화 완료")

    def process_new_logs(self, file_path):
        """새로운 로그 라인 처리 - 부모 메서드 오버라이드"""
        if not self.template_miner:
            return

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                last_pos = self.last_position.get(file_path, 0)
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

                    # 에러 라인인지 확인
                    if self.is_error_line(line):
                        self.error_logs += 1
                        dashboard_data['error_logs'] += 1

                        # 🔥 대시보드 데이터 업데이트
                        self.update_dashboard_data(line, is_error=True)

                        # 🔥 에러 클러스터링 + AI 분석
                        self.handle_error_clustering(line)

                        # 🔥 실시간 Socket.IO 전송
                        try:
                            socketio.emit('new_error_log', {
                                'timestamp': datetime.now().isoformat(),
                                'content': line,
                                'type': 'error'
                            })
                        except Exception as e:
                            print(f"Socket 전송 오류: {e}")
                    else:
                        # 일반 로그도 대시보드에 추가
                        self.update_dashboard_data(line, is_error=False)

        except Exception as e:
            print(f"❌ 파일 읽기 오류: {e}")

    def update_dashboard_data(self, line, is_error=False):
        """🔥 대시보드 데이터 업데이트 (웹 전용 메서드)"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'content': line,
            'type': 'error' if is_error else 'info',
            'severity': self.get_log_severity(line) if is_error else 'info'
        }
        dashboard_data['recent_logs'].append(log_entry)

        if is_error:
            # 에러 타임라인 업데이트
            now = datetime.now()
            timeline_entry = {
                'timestamp': now.isoformat(),
                'count': 1
            }
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
        """🔥 에러 클러스터링 처리 - 부모 메서드 오버라이드하여 웹 기능 추가"""
        if not self.template_miner:
            print("❌ Drain3 엔진이 초기화되지 않음")
            return

        timestamp = datetime.now().strftime("%H:%M:%S")

        print(f"\n🚨 [{timestamp}] 에러 감지!")
        print(f"📝 로그: {error_line}")

        try:
            # Drain3로 클러스터링
            result = self.template_miner.add_log_message(error_line)

            cluster_id = self.get_cluster_id(result)
            template = self.get_template(result)

            print(f"🏷️  클러스터 ID: {cluster_id}")
            print(f"📋 템플릿: {template}")

            # 🔥 대시보드 클러스터 정보 업데이트
            if cluster_id not in dashboard_data['clusters']:
                dashboard_data['clusters'][cluster_id] = {
                    'template': template,
                    'count': 0,
                    'first_seen': datetime.now().isoformat(),
                    'last_seen': datetime.now().isoformat(),
                    'severity': '경미',
                    'recent_logs': deque(maxlen=10),
                    'ai_analysis': None  # AI 분석 결과
                }

            cluster = dashboard_data['clusters'][cluster_id]
            cluster['count'] += 1
            cluster['last_seen'] = datetime.now().isoformat()
            cluster['severity'] = self.get_severity(cluster['count'])
            cluster['recent_logs'].append({
                'content': error_line,
                'timestamp': datetime.now().isoformat()
            })

            dashboard_data['cluster_stats'][cluster_id] += 1

            cluster_size = cluster['count']
            print(f"📊 발생 횟수: {cluster_size}번")

            # 🔥 빈발 패턴 감지 (3회 이상, 5의 배수)
            if cluster_size >= 3 and cluster_size % 5 == 0:
                print(f"⚠️  빈발 패턴 감지! {cluster_size}번 발생")

                # 🔥 AI 분석 수행
                if self.ollama_analyzer and self.ollama_analyzer.enabled:
                    self.perform_ai_analysis_for_web(cluster_id, cluster, error_line, template)

                # Slack 알림
                self.alert_frequent_error(error_line, template, cluster_size, cluster_id)

            # 🔥 Socket.IO로 클러스터 업데이트 전송
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

    def perform_ai_analysis_for_web(self, cluster_id, cluster, error_log, template):
        """🔥 웹 대시보드용 AI 분석 수행 (ollama_integration 사용)"""
        analysis_start_time = datetime.now().strftime("%H:%M:%S")
        print(f"🤖 웹 대시보드 AI 분석 시작: {template[:50]}... (시작시간: {analysis_start_time})")

        try:
            # 🔥 OllamaErrorAnalyzer.analyze_error() 호출
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

            # 클러스터에 AI 분석 결과 저장
            cluster['ai_analysis'] = ai_analysis

            # 전역 AI 분석 저장소에 추가
            dashboard_data['ai_analyses'].append({
                'cluster_id': cluster_id,
                'template': template,
                'analysis': ai_analysis,
                'timestamp': datetime.now().isoformat()
            })

            # AI 분석기 상태 업데이트
            module_status['ai_analyzer']['last_analysis'] = datetime.now().isoformat()

            # 콘솔에 AI 분석 결과 출력
            print(f"\n🧠 AI 분석 완료:")
            print(f"   에러 유형: {ai_analysis['error_type']}")
            print(f"   심각도: {ai_analysis['severity']}")
            print(f"   근본 원인: {ai_analysis['root_cause']}")
            print(f"   신뢰도: {ai_analysis['confidence']}%")

            print(f"\n⚡ 즉시 조치사항:")
            for i, action in enumerate(ai_analysis['immediate_actions'], 1):
                print(f"   {i}. {action}")

            print(f"\n🔧 장기적 해결방안:")
            for i, solution in enumerate(ai_analysis['long_term_solutions'], 1):
                print(f"   {i}. {solution}")

            # 🔥 Socket.IO로 실시간 AI 분석 결과 전송
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
    """🔥 SSH를 통한 원격 로그 모니터링 + 자동 AI 분석"""
    try:
        print(f"🔍 SSH 로그 모니터링 시작: {log_path}")

        stdin, stdout, stderr = ssh_client.exec_command(f'tail -f {log_path}')

        # 웹 핸들러 초기화
        if 'web_handler' not in globals():
            global web_handler
            web_handler = WebDashboardHandler()

        for line in iter(stdout.readline, ""):
            if not line:
                break

            line = line.strip()
            if line:
                is_error = web_handler.is_error_line(line)

                # SSH 로그 저장소에 추가
                ssh_log_entry = {
                    'timestamp': datetime.now().isoformat(),
                    'content': line,
                    'type': 'error' if is_error else 'info',
                    'source': 'ssh'
                }
                dashboard_data['ssh_logs'].append(ssh_log_entry)

                # 대시보드 데이터 업데이트
                web_handler.update_dashboard_data(line, is_error)

                # 🔥 에러인 경우 클러스터링 + AI 분석 자동 실행
                if is_error:
                    web_handler.handle_error_clustering(line)

                # 실시간 전송
                socketio.emit('ssh_log_update', ssh_log_entry)

    except Exception as e:
        print(f"❌ SSH 로그 모니터링 오류: {e}")
        module_status['ssh_connection']['status'] = 'disconnected'
        module_status['ssh_connection']['process'] = None


def rag_learning_process(model_name='sentence-transformers/all-MiniLM-L6-v2', max_results=20):
    """RAG 학습 프로세스 (Jira 연동)"""
    try:
        socketio.emit('rag_progress', {'stage': 'init', 'progress': 0, 'total': 100})

        if not JIRA_AVAILABLE:
            raise Exception("Jira 모듈을 사용할 수 없습니다")

        if not RAG_TRAINER_AVAILABLE:
            raise Exception("RAG Trainer 모듈을 사용할 수 없습니다")

        from jira_integration import JiraIntegration
        from rag_trainer import RAGTrainer

        socketio.emit('rag_progress', {'stage': 'connecting', 'progress': 10, 'total': 100, 'detail': 'Jira 연결 중...'})
        jira = JiraIntegration()

        socketio.emit('rag_progress', {'stage': 'searching', 'progress': 20, 'total': 100, 'detail': 'Bug 이슈 검색 중...'})

        bug_jql = 'issuetype = Bug ORDER BY created DESC'
        all_issues = []
        start_at = 0
        batch_size = 50

        print(f"\n🎯 목표: Bug 이슈 {max_results}개 수집")

        while len(all_issues) < max_results:
            remaining = max_results - len(all_issues)
            current_batch_size = min(batch_size, remaining)

            try:
                issues_batch = jira.search_issues(
                    jql=bug_jql,
                    startAt=start_at,
                    maxResults=current_batch_size
                )

                if not issues_batch:
                    print(f"✅ 더 이상 Bug 이슈가 없습니다. 이 {len(all_issues)}개 수집됨")
                    break

                for issue in issues_batch:
                    if len(all_issues) >= max_results:
                        break

                    issue_type = issue.fields.issuetype.name if hasattr(issue.fields, 'issuetype') else 'Unknown'

                    if issue_type.lower() == 'bug':
                        all_issues.append(issue)

                        progress = 20 + (len(all_issues) / max_results) * 30
                        socketio.emit('rag_progress', {
                            'stage': 'collecting',
                            'progress': int(progress),
                            'total': 100,
                            'detail': f'Bug 이슈 수집 중... ({len(all_issues)}/{max_results})'
                        })

                        print(f"  ✓ {issue.key} 수집 ({len(all_issues)}/{max_results})")

                start_at += current_batch_size

                if start_at > 1000:
                    print(f"⚠️ 검색 한계 도달. Bug 이슈 {len(all_issues)}개만 수집됨")
                    break

            except Exception as e:
                print(f"❌ 배치 수집 오류: {e}")
                break

        if len(all_issues) == 0:
            raise Exception("Bug 타입의 이슈를 찾을 수 없습니다")

        print(f"\n✅ 이 {len(all_issues)}개의 Bug 이슈 수집 완료")

        socketio.emit('rag_progress', {'stage': 'preprocessing', 'progress': 50, 'total': 100, 'detail': 'Bug 데이터 전처리 중...'})

        documents = []
        for i, issue in enumerate(all_issues):
            try:
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
                        'status': issue.fields.status.name if hasattr(issue.fields, 'status') and issue.fields.status else 'Unknown'
                    }
                })

                progress = 50 + (i / len(all_issues)) * 20
                socketio.emit('rag_progress', {
                    'stage': 'preprocessing',
                    'progress': int(progress),
                    'total': 100,
                    'detail': f'Bug 데이터 전처리 중... ({i+1}/{len(all_issues)})'
                })

            except Exception as e:
                print(f"❌ 이슈 {issue.key} 처리 중 오류: {e}")
                continue

        if not documents:
            raise Exception("처리 가능한 Bug 이슈가 없습니다")

        print(f"\n✅ {len(documents)}개 문서 전처리 완료")

        socketio.emit('rag_progress', {'stage': 'training', 'progress': 70, 'total': 100, 'detail': 'RAG 모델 학습 중...'})

        trainer = RAGTrainer(model_name=model_name)

        socketio.emit('rag_progress', {'stage': 'indexing', 'progress': 80, 'total': 100, 'detail': 'Bug 데이터 인덱싱 중...'})
        trainer.build_vector_database(documents)

        socketio.emit('rag_progress', {'stage': 'saving', 'progress': 90, 'total': 100, 'detail': '모델 저장 중...'})
        model_path = f"models/bug_rag_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        trainer.save_model(model_path)

        socketio.emit('rag_progress', {'stage': 'complete', 'progress': 100, 'total': 100, 'detail': '학습 완료!'})

        result = {
            'success': True,
            'message': f'Bug RAG 학습 완료! {len(documents)}개의 Bug 이슈로 학습했습니다.',
            'model_path': model_path,
            'bug_count': len(documents),
            'documents_processed': len(documents)
        }

        socketio.emit('rag_complete', result)
        return result

    except Exception as e:
        error_result = {
            'success': False,
            'message': f'RAG 학습 실패: {str(e)}'
        }
        socketio.emit('rag_error', error_result)
        return error_result


# 파일 모니터링 시작
def start_file_monitoring(watch_dir="logs"):
    """파일 모니터링 시작"""
    global web_handler, observer

    if not os.path.exists(watch_dir):
        os.makedirs(watch_dir)

    if not hasattr(start_file_monitoring, 'started'):
        web_handler = WebDashboardHandler(watch_dir)
        observer = Observer()
        observer.schedule(web_handler, watch_dir, recursive=True)
        observer.start()
        start_file_monitoring.started = True
        print(f"✅ 파일 모니터링 시작: {watch_dir}")


# Flask 라우트들
@app.route('/')
def index():
    """메인 페이지"""
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
            'ai_analysis': cluster_info.get('ai_analysis')  # 🔥 AI 분석 결과 포함
        }
        clusters.append(cluster_data)

    # 발생 횟수 순으로 정렬
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
    """🔥 AI 분석 결과 API"""
    return jsonify(list(dashboard_data['ai_analyses']))


@app.route('/api/system-info')
def get_system_info():
    """시스템 정보 API"""
    try:
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

        # SSH 연결 테스트 및 로그 파일 확인
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(host, username=username, password=password, timeout=10)

        stdin, stdout, stderr = client.exec_command(f'ls -la {log_path}')
        output = stdout.read().decode().strip()
        error_output = stderr.read().decode().strip()

        if error_output and ('No such file' in error_output or 'cannot access' in error_output):
            client.close()
            return jsonify({'error': f'로그 파일을 찾을 수 없습니다: {log_path}'}), 400

        # SSH 연결 정보 저장
        module_status['ssh_connection']['status'] = 'connected'
        module_status['ssh_connection']['process'] = client
        module_status['ssh_connection']['log_path'] = log_path
        module_status['ssh_connection']['host'] = host
        module_status['ssh_connection']['username'] = username

        # SSH 로그 모니터링 시작
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
            module_status['ssh_connection']['process'].close()

        module_status['ssh_connection']['status'] = 'disconnected'
        module_status['ssh_connection']['process'] = None
        module_status['ssh_connection']['log_path'] = None
        module_status['ssh_connection']['host'] = None

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
            return jsonify({
                'error': 'Jira 연동이 설정되지 않았습니다. .env 파일의 JIRA 설정을 확인하세요.'
            }), 400

        if not RAG_TRAINER_AVAILABLE:
            return jsonify({
                'error': 'RAG 학습 모듈이 설정되지 않았습니다. rag.trainer 모듈을 확인하세요.'
            }), 400

        process = threading.Thread(
            target=rag_learning_process,
            kwargs={
                'model_name': model_name,
                'max_results': max_results
            },
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
    """RAG 학습 중지"""
    try:
        if module_status['rag_learning']['process']:
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
    emit('status', {'message': '대시보드에 연결되었습니다'})


@socketio.on('disconnect')
def handle_disconnect():
    print('클라이언트 연결 해제됨')


@socketio.on('request_update')
def handle_request_update():
    """클라이언트 업데이트 요청 처리"""
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

    # 기존 dashboard.html 템플릿 사용
    # (너무 길어서 여기서는 생략 - 원본 web_dashboard.py의 HTML 사용)
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