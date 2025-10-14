"""
통합 웹 대시보드 - Flask 기반 실시간 모니터링
- RAG 학습 관리 (Jira 연동)
- SSH 연결 관리 (로그 파일 지정 포함)
- 로그 모니터링
- 시스템 정보
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

# Jira 연동 import 추가
try:
    from jira_integration import JiraIntegration

    JIRA_AVAILABLE = True
    print("✅ Jira 연동 모듈 로드 성공")
except ImportError as e:
    JIRA_AVAILABLE = False
    print(f"❌ Jira 연동 모듈 로드 실패: {e}")

# RAG 학습 import 추가
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

# Drain3 import (선택사항)
try:
    from drain3 import TemplateMiner
    from drain3.template_miner_config import TemplateMinerConfig
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    import paramiko
except ImportError as e:
    print(f"필수 모듈 import 실패: {e}")
    print("pip install -r requirements.txt를 실행하세요.")

# Ollama 연동 import 추가
try:
    from ollama_integration import OllamaErrorAnalyzer
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    print("Ollama 연동 모듈을 찾을 수 없습니다. AI 분석 기능이 비활성화됩니다.")


# Flask 앱 생성
app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*")

# 전역 데이터 저장소
dashboard_data = {
    'total_logs': 0,
    'error_logs': 0,
    'recent_logs': deque(maxlen=100),  # 최근 100개만 저장
    'clusters': {},  # cluster_id -> cluster info
    'error_timeline': deque(maxlen=50),  # 최근 50개 시간대
    'cluster_stats': defaultdict(int),
    'last_frequent_alert': {},  # 빈발 패턴 알림 제한
    'ssh_logs': deque(maxlen=500)  # SSH 로그 저장소
}

# 모듈 상태 추적
module_status = {
    'log_monitoring': {'status': 'running', 'process': None},  # 웹 대시보드는 항상 실행
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
    }
}


# 웹 대시보드 핸들러 클래스
class WebDashboardHandler(FileSystemEventHandler):
    """웹 대시보드용 파일 모니터링 핸들러 - 개선 버전"""

    def __init__(self, watch_dir="logs"):
        self.watch_dir = watch_dir
        self.last_position = {}

        # 🔥 개선: 더 포괄적인 에러 키워드
        self.error_keywords = [
            'ERROR', 'Exception', 'error', 'FATAL', 'CRITICAL', 'failed',
            'failure', 'NullPointerException', 'SQLException', 'OutOfMemoryError',
            'ConnectionException', 'TimeoutException', 'refused', 'denied',
            'Error:', 'Exception:', 'WARN', 'WARNING'  # 추가
        ]

        # Slack 연동 초기화
        self.slack_notifier = None
        if SLACK_AVAILABLE:
            self.slack_notifier = SlackNotifier()

        # Drain3 초기화
        self.template_miner = None
        self.initialize_drain3()

        # Ollama AI 분석기 초기화
        if OLLAMA_AVAILABLE:
            self.ollama_analyzer = OllamaErrorAnalyzer()
        else:
            self.ollama_analyzer = None

        print("✅ 웹 대시보드 핸들러 초기화 완료")

    def initialize_drain3(self):
        """Drain3 템플릿 마이너 초기화"""
        try:
            config = TemplateMinerConfig()
            config.load('drain3.ini')
            config.profiling_enabled = False
            self.template_miner = TemplateMiner(config=config)
            print("✅ Drain3 엔진 초기화 성공")
        except Exception as e:
            print(f"⚠️ Drain3 초기화 실패 (기본 설정 사용): {e}")
            try:
                # 설정 파일 없이 초기화
                self.template_miner = TemplateMiner()
                print("✅ Drain3 기본 설정으로 초기화 성공")
            except Exception as e2:
                print(f"❌ Drain3 초기화 완전 실패: {e2}")
                self.template_miner = None

    def on_modified(self, event):
        """파일 수정 이벤트 처리"""
        if not event.is_directory and event.src_path.endswith('.log'):
            self.process_new_logs(event.src_path)

    def process_new_logs(self, file_path):
        """새로운 로그 라인 처리 - 개선 버전"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                # 마지막 읽은 위치부터 읽기
                if file_path in self.last_position:
                    f.seek(self.last_position[file_path])
                else:
                    f.seek(0)

                new_lines = f.readlines()
                self.last_position[file_path] = f.tell()

                for line in new_lines:
                    line = line.strip()
                    if not line:
                        continue

                    # 🔥 개선: 로그 파싱 강화
                    is_error = self.is_error_line(line)

                    # 대시보드 데이터 업데이트
                    self.update_dashboard_data(line, is_error)

                    # 에러 로그인 경우 클러스터링 처리
                    if is_error:
                        self.handle_error_clustering(line)

                        # 🔥 추가: Socket.IO로 실시간 전송
                        try:
                            socketio.emit('new_error_log', {
                                'timestamp': datetime.now().isoformat(),
                                'content': line,
                                'type': 'error'
                            })
                        except Exception as e:
                            print(f"Socket 전송 오류: {e}")

        except Exception as e:
            print(f"❌ 파일 읽기 오류: {e}")

    def is_error_line(self, line):
        """에러 라인 여부 판단 - 개선 버전"""
        line_upper = line.upper()

        # 키워드 매칭
        for keyword in self.error_keywords:
            if keyword.upper() in line_upper:
                return True

        # 추가 패턴 검사
        error_patterns = [
            'EXCEPTION',
            'STACK TRACE',
            'CAUSED BY',
            'AT LINE',
            'FAILED TO',
            'UNABLE TO',
            'COULD NOT'
        ]

        for pattern in error_patterns:
            if pattern in line_upper:
                return True

        return False

    def update_dashboard_data(self, line, is_error=False):
        """대시보드 데이터 업데이트 - 개선 버전"""
        dashboard_data['total_logs'] += 1

        # 🔥 개선: 로그 타입 명확히 표시
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'content': line,
            'type': 'error' if is_error else 'info',
            'severity': self.get_log_severity(line) if is_error else 'info'
        }
        dashboard_data['recent_logs'].append(log_entry)

        # 에러 로그 카운트
        if is_error:
            dashboard_data['error_logs'] += 1

            # 에러 타임라인 업데이트
            now = datetime.now()
            timeline_entry = {
                'timestamp': now.isoformat(),
                'count': 1
            }
            dashboard_data['error_timeline'].append(timeline_entry)

            # 🔥 추가: 콘솔에도 출력
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

    def handle_error_clustering(self, line):
        """에러 로그 클러스터링 처리"""
        if not self.template_miner:
            return

        try:
            # Drain3로 클러스터링
            result = self.template_miner.add_log_message(line)

            cluster_id = self.get_cluster_id(result)
            template = self.get_template(result)

            # 클러스터 정보 업데이트
            if cluster_id not in dashboard_data['clusters']:
                dashboard_data['clusters'][cluster_id] = {
                    'template': template,
                    'count': 0,
                    'first_seen': datetime.now().isoformat(),
                    'last_seen': datetime.now().isoformat(),
                    'severity': '경미',
                    'recent_logs': deque(maxlen=10)
                }

            cluster = dashboard_data['clusters'][cluster_id]
            cluster['count'] += 1
            cluster['last_seen'] = datetime.now().isoformat()
            cluster['severity'] = self.get_severity(cluster['count'])
            cluster['recent_logs'].append({
                'content': line,
                'timestamp': datetime.now().isoformat()
            })

            dashboard_data['cluster_stats'][cluster_id] += 1

            # 🔥 개선: 콘솔에 클러스터 정보 출력
            print(f"📊 클러스터 {cluster_id}: {template[:80]}... (발생: {cluster['count']}회)")

            # 빈발 패턴 감지 및 알림
            if cluster['count'] >= 3 and cluster['count'] % 5 == 0:
                if self.ollama_analyzer and self.ollama_analyzer.enabled:
                    analysis_start_time = datetime.now().strftime("%H:%M:%S")
                    print(f"🤖 웹 대시보드 AI 분석 시작: {template} (시작시간: {analysis_start_time})")
                    try:
                        ai_analysis = self.ollama_analyzer.analyze_error(
                            error_log=line,
                            error_template=template,
                            occurrence_count=cluster['count'],
                            context={
                                "cluster_id": cluster_id,
                                "detection_time": datetime.now().isoformat(),
                                "total_logs": dashboard_data['total_logs'],
                                "error_logs": dashboard_data['error_logs']
                            }
                        )
                        cluster['ai_analysis'] = ai_analysis
                        print(f"AI 분석 완료: {template}")
                    except Exception as e:
                        print(f"AI 분석 실패: {e}")
                        cluster['ai_analysis'] = None

                self.send_frequent_pattern_alert(cluster_id, cluster)

            # 🔥 추가: Socket.IO로 클러스터 업데이트 전송
            try:
                socketio.emit('cluster_update', {
                    'cluster_id': cluster_id,
                    'template': template,
                    'count': cluster['count'],
                    'severity': cluster['severity'],
                    'last_seen': cluster['last_seen']
                })
            except Exception as e:
                print(f"Socket 전송 오류: {e}")

        except Exception as e:
            print(f"❌ 클러스터링 처리 오류: {e}")

    def get_cluster_id(self, result):
        """클러스터 ID 추출"""
        if isinstance(result, dict):
            return result.get('cluster_id', 'unknown')
        else:
            return getattr(result, 'cluster_id', 'unknown')

    def get_template(self, result):
        """템플릿 추출"""
        if isinstance(result, dict):
            return result.get('template_mined', result.get('template', 'unknown'))
        else:
            return getattr(result, 'template', 'unknown')

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

    def send_frequent_pattern_alert(self, cluster_id, cluster):
        """빈발 패턴 알림 전송"""
        if self.slack_notifier:
            # 예제 로그 수집
            examples = list(cluster['recent_logs'])

            message = f"""🚨 빈발 에러 패턴 감지!

패턴 ID: {cluster_id}
템플릿: {cluster['template']}
발생 횟수: {cluster['count']}회
심각도: {cluster['severity']}
최근 발생: {cluster['last_seen']}

권장 조치:
- 로그 패턴 분석 필요
- 시스템 상태 점검 권장"""

            self.slack_notifier.send_alert(
                title="빈발 에러 패턴 감지",
                message=message,
                severity=cluster['severity']
            )


def monitor_ssh_logs(ssh_client, log_path):
    """SSH를 통한 원격 로그 모니터링"""
    try:
        print(f"🔍 SSH 로그 모니터링 시작: {log_path}")

        # tail -f 명령으로 실시간 로그 모니터링
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
                # SSH 로그에 추가
                ssh_log_entry = {
                    'timestamp': datetime.now().isoformat(),
                    'content': line,
                    'type': 'error' if web_handler.is_error_line(line) else 'info',
                    'source': 'ssh'
                }
                dashboard_data['ssh_logs'].append(ssh_log_entry)

                # SSH로 받은 로그를 로컬 핸들러로 처리
                web_handler.update_dashboard_data(line)

                # 에러 로그인 경우 클러스터링 처리
                if web_handler.is_error_line(line):
                    web_handler.handle_error_clustering(line)

                # 실시간으로 클라이언트에 전송
                socketio.emit('ssh_log_update', ssh_log_entry)

                # print(f"SSH 로그: {line}")

    except Exception as e:
        print(f"❌ SSH 로그 모니터링 오류: {e}")
        module_status['ssh_connection']['status'] = 'disconnected'
        module_status['ssh_connection']['process'] = None


def rag_learning_process(model_name='sentence-transformers/all-MiniLM-L6-v2', max_results=20):
    """
    RAG 학습 프로세스 (Jira 연동) - Bug만 정확히 수집

    Args:
        model_name: 사용할 임베딩 모델 이름
        max_results: 수집할 최대 Bug 이슈 개수 (기본값: 20)
    """
    try:
        socketio.emit('rag_progress', {'stage': 'init', 'progress': 0, 'total': 100})

        if not JIRA_AVAILABLE:
            raise Exception("Jira 모듈을 사용할 수 없습니다")

        if not RAG_TRAINER_AVAILABLE:
            raise Exception("RAG Trainer 모듈을 사용할 수 없습니다")

        from jira_integration import JiraIntegration
        from rag_trainer import RAGTrainer

        # Jira 연결
        socketio.emit('rag_progress', {'stage': 'connecting', 'progress': 10, 'total': 100, 'detail': 'Jira 연결 중...'})
        jira = JiraIntegration()

        # Bug 이슈만 검색하도록 JQL 수정
        socketio.emit('rag_progress', {'stage': 'searching', 'progress': 20, 'total': 100, 'detail': 'Bug 이슈 검색 중...'})

        # 🔥 수정: Bug 타입만 정확히 가져오는 JQL
        bug_jql = 'issuetype = Bug ORDER BY created DESC'

        all_issues = []
        start_at = 0
        batch_size = 50

        # 🔥 수정: Bug 이슈를 정확히 max_results개까지만 수집
        print(f"\n🎯 목표: Bug 이슈 {max_results}개 수집")

        while len(all_issues) < max_results:
            # 남은 개수만큼만 요청
            remaining = max_results - len(all_issues)
            current_batch_size = min(batch_size, remaining)

            try:
                # 🔥 search_issues 메서드 사용 (jira_integration.py에 추가 필요)
                issues_batch = jira.search_issues(
                    jql=bug_jql,
                    startAt=start_at,
                    maxResults=current_batch_size
                )

                if not issues_batch:
                    print(f"✅ 더 이상 Bug 이슈가 없습니다. 총 {len(all_issues)}개 수집됨")
                    break

                # Bug 타입인지 재확인 (안전장치)
                for issue in issues_batch:
                    if len(all_issues) >= max_results:
                        break

                    # issuetype이 Bug인지 확인
                    issue_type = issue.fields.issuetype.name if hasattr(issue.fields, 'issuetype') else 'Unknown'

                    if issue_type.lower() == 'bug':
                        all_issues.append(issue)

                        # 진행률 업데이트
                        progress = 20 + (len(all_issues) / max_results) * 30  # 20-50% 구간
                        socketio.emit('rag_progress', {
                            'stage': 'collecting',
                            'progress': int(progress),
                            'total': 100,
                            'detail': f'Bug 이슈 수집 중... ({len(all_issues)}/{max_results})'
                        })

                        print(f"  ✓ {issue.key} 수집 ({len(all_issues)}/{max_results})")

                # 다음 배치로
                start_at += current_batch_size

                # 무한루프 방지
                if start_at > 1000:
                    print(f"⚠️ 검색 한계 도달. Bug 이슈 {len(all_issues)}개만 수집됨")
                    break

            except Exception as e:
                print(f"❌ 배치 수집 오류: {e}")
                break

        if len(all_issues) == 0:
            raise Exception("Bug 타입의 이슈를 찾을 수 없습니다")

        print(f"\n✅ 총 {len(all_issues)}개의 Bug 이슈 수집 완료")

        # 이슈 데이터 전처리
        socketio.emit('rag_progress', {'stage': 'preprocessing', 'progress': 50, 'total': 100, 'detail': 'Bug 데이터 전처리 중...'})

        documents = []
        for i, issue in enumerate(all_issues):
            try:
                # Bug 이슈 정보 추출
                doc_text = f"Bug ID: {issue.key}\n"
                doc_text += f"Summary: {issue.fields.summary}\n"

                if hasattr(issue.fields, 'description') and issue.fields.description:
                    doc_text += f"Description: {issue.fields.description}\n"

                if hasattr(issue.fields, 'priority') and issue.fields.priority:
                    doc_text += f"Priority: {issue.fields.priority.name}\n"

                if hasattr(issue.fields, 'status') and issue.fields.status:
                    doc_text += f"Status: {issue.fields.status.name}\n"

                # Bug 관련 추가 정보
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

                # 진행률 업데이트
                progress = 50 + (i / len(all_issues)) * 20  # 50-70% 구간
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

        # RAG 모델 학습
        socketio.emit('rag_progress', {'stage': 'training', 'progress': 70, 'total': 100, 'detail': 'RAG 모델 학습 중...'})

        trainer = RAGTrainer(model_name=model_name)

        # 벡터 데이터베이스 구축
        socketio.emit('rag_progress', {'stage': 'indexing', 'progress': 80, 'total': 100, 'detail': 'Bug 데이터 인덱싱 중...'})
        trainer.build_vector_database(documents)

        # 모델 저장
        socketio.emit('rag_progress', {'stage': 'saving', 'progress': 90, 'total': 100, 'detail': '모델 저장 중...'})
        model_path = f"models/bug_rag_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        trainer.save_model(model_path)

        # 완료
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
        clusters.append({
            'id': cluster_id,
            'template': cluster_info['template'],
            'count': cluster_info['count'],
            'severity': cluster_info['severity'],
            'last_seen': cluster_info['last_seen'],
            'first_seen': cluster_info['first_seen']
        })

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


@app.route('/api/system-info')
def get_system_info():
    """시스템 정보 API"""
    try:
        # CPU 사용률
        cpu_percent = psutil.cpu_percent(interval=1)

        # 메모리 정보
        memory = psutil.virtual_memory()

        # 디스크 사용률
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
        log_path = data.get('log_path', '/var/log/application.log')  # 로그 파일 경로 추가

        if module_status['ssh_connection']['process']:
            return jsonify({'error': 'SSH 연결이 이미 활성화되어 있습니다'}), 400

        if not host or not username or not log_path:
            return jsonify({'error': '호스트, 사용자명, 로그 경로를 모두 입력하세요'}), 400

        # SSH 연결 테스트 및 로그 파일 확인
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(host, username=username, password=password, timeout=10)

        # 로그 파일 존재 여부 확인
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

        # SSH 로그 초기화
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
        max_results = data.get('max_results', 20)  # 기본값 20으로 변경

        if module_status['rag_learning']['process']:
            return jsonify({'error': 'RAG 학습이 이미 진행 중입니다'}), 400

        # 필수 모듈 확인
        if not JIRA_AVAILABLE:
            return jsonify({
                'error': 'Jira 연동이 설정되지 않았습니다. .env 파일의 JIRA 설정을 확인하세요.'
            }), 400

        if not RAG_TRAINER_AVAILABLE:
            return jsonify({
                'error': 'RAG 학습 모듈이 설정되지 않았습니다. rag.trainer 모듈을 확인하세요.'
            }), 400

        # 🔥 수정: kwargs로 model_name과 max_results 모두 전달
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
                    # SSH 연결 살아있는지 확인
                    stdin, stdout, stderr = module_status['ssh_connection']['process'].exec_command('echo "alive"',
                                                                                                    timeout=5)
                    stdout.read()
                except:
                    module_status['ssh_connection']['status'] = 'disconnected'
                    module_status['ssh_connection']['process'] = None
                    module_status['ssh_connection']['log_path'] = None

            time.sleep(5)  # 5초마다 체크
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
            transform: translateX(400px);
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
                        <input type="number" id="rag-max-results" placeholder="10" value="10" min="1" max="100">
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
        });
        
        socket.on('rag_error', function(data) {
            console.log('RAG 에러:', data);
            showNotification(data.message, true);
            hideRAGProgress();
            updateModuleStatus();
        });
        
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
                    
                    container.innerHTML = data.map(cluster => `
                        <div class="cluster-item severity-${getSeverityClass(cluster.severity)}">
                            <div class="cluster-count">${cluster.count}회 발생</div>
                            <div class="cluster-template">${cluster.template}</div>
                            <div style="font-size: 0.8em; color: #666; margin-top: 5px;">
                                마지막: ${new Date(cluster.last_seen).toLocaleString()}
                            </div>
                        </div>
                    `).join('');
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
        });
    </script>
</body>
</html>'''

    with open(os.path.join(templates_dir, 'dashboard.html'), 'w', encoding='utf-8') as f:
        f.write(html_content)

    print("✅ HTML 템플릿 생성 완료")


def main():
    """메인 실행 함수"""
    print("🚀 통합 모니터링 대시보드 시작")
    print("=" * 50)

    # HTML 템플릿 생성
    create_templates()

    # 파일 모니터링 시작
    start_file_monitoring()

    # 상태 체크 스레드 시작
    status_thread = threading.Thread(target=check_module_status, daemon=True)
    status_thread.start()

    print("🌐 웹 대시보드 서버 시작 중...")
    print("📱 브라우저에서 http://localhost:5000 접속하세요")
    print("🎛️ 왼쪽 메뉴에서 RAG 학습, SSH 연결, 시스템 정보에 접근하세요")
    print("🧠 RAG 학습 탭에서 Jira 프로젝트를 설정하고 학습을 시작하세요")
    print("🔒 SSH 연결 탭에서 로그 파일 경로를 지정하세요")
    print("🛑 Ctrl+C로 종료")

    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\n❗ 대시보드 서버 종료")
        print("✅ 종료 완료")


if __name__ == "__main__":
    main()
