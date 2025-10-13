"""
파일명: web_dashboard.py
목적: Flask 기반 웹 대시보드 - 실시간 로그 모니터링 시각화
사용법: python web_dashboard.py
"""

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import json
import threading
import time
from datetime import datetime, timedelta
from collections import defaultdict, deque
import os
import sys
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 기존 모듈 import
try:
    from drain3 import TemplateMiner
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    from dotenv import load_dotenv
    load_dotenv()
except ImportError as e:
    print(f"필수 모듈 import 실패: {e}")
    print("pip install -r requirements.txt를 실행하세요.")
    sys.exit(1)

try:
    from slack_integration import SlackNotifier
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False
    print("Slack 연동 모듈을 찾을 수 없습니다.")

try:
    from ollama_integration import OllamaErrorAnalyzer
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    print("Ollama 연동 모듈을 찾을 수 없습니다. AI 분석 기능이 비활성화됩니다.")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'log_monitoring_secret_key'

# Flask 로그 비활성화
import logging

# Werkzeug 로그만 비활성화 (안전한 방법)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# 추가적인 로그 비활성화
logging.getLogger('socketio').setLevel(logging.ERROR)
logging.getLogger('engineio').setLevel(logging.ERROR)

socketio = SocketIO(app, cors_allowed_origins="*")

# 전역 데이터 저장소
dashboard_data = {
    'total_logs': 0,
    'error_logs': 0,
    'clusters': {},
    'recent_logs': deque(maxlen=100),  # 최근 100개 로그만 저장
    'error_timeline': deque(maxlen=50),  # 최근 50개 에러 타임라인
    'cluster_stats': defaultdict(int),
    'system_status': 'running',
    'last_update': datetime.now().isoformat()
}

class WebDashboardHandler(FileSystemEventHandler):
    """웹 대시보드용 로그 핸들러"""
    
    def __init__(self):
        # 파일별 마지막 읽은 위치 저장
        self.last_position = {}
        
        # 에러 키워드 정의
        self.error_keywords = ['ERROR', 'FATAL', 'Exception', 'Failed', 'Error:']
        
        # Drain3 엔진 초기화
        self.template_miner = self.initialize_drain3()
        
        # Slack 연동 초기화
        if SLACK_AVAILABLE:
            self.slack_notifier = SlackNotifier()
        else:
            self.slack_notifier = None
        
        # Ollama AI 분석기 초기화
        if OLLAMA_AVAILABLE:
            self.ollama_analyzer = OllamaErrorAnalyzer()
        else:
            self.ollama_analyzer = None
        
        print("✅ 웹 대시보드 핸들러 초기화 완료")
    
    def initialize_drain3(self):
        """Drain3 초기화"""
        try:
            template_miner = TemplateMiner()
            print("✅ Drain3 엔진 초기화 성공")
            return template_miner
        except Exception as e:
            print(f"❌ Drain3 초기화 실패: {e}")
            return None
    
    def on_modified(self, event):
        """파일 변경 감지시 호출"""
        if not self.template_miner:
            return
            
        # .log 파일만 처리
        if event.is_directory or not event.src_path.endswith('.log'):
            return
        
        self.process_new_logs(event.src_path)
    
    def process_new_logs(self, file_path):
        """새로운 로그 라인 처리"""
        if not self.template_miner:
            return
            
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                # 마지막 위치부터 읽기
                last_pos = self.last_position.get(file_path, 0)
                f.seek(last_pos)
                
                new_lines = f.readlines()
                self.last_position[file_path] = f.tell()
                
                # 각 라인 검사
                for line in new_lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # 대시보드 데이터 업데이트
                    dashboard_data['total_logs'] += 1
                    
                    # 최근 로그에 추가
                    log_entry = {
                        'timestamp': datetime.now().isoformat(),
                        'content': line,
                        'type': 'error' if self.is_error_line(line) else 'info'
                    }
                    dashboard_data['recent_logs'].append(log_entry)
                    
                    # 에러 라인인지 확인
                    if self.is_error_line(line):
                        dashboard_data['error_logs'] += 1
                        self.handle_error_clustering(line, log_entry)
                        
                        # 에러 타임라인에 추가
                        dashboard_data['error_timeline'].append({
                            'timestamp': datetime.now().isoformat(),
                            'count': 1
                        })
                        
                        # WebSocket으로 실시간 업데이트
                        socketio.emit('new_error', {
                            'log': log_entry,
                            'total_errors': dashboard_data['error_logs'],
                            'total_logs': dashboard_data['total_logs']
                        })
                        
        except Exception as e:
            print(f"❌ 파일 읽기 오류: {e}")
    
    def is_error_line(self, line):
        """에러 라인 판단"""
        return any(keyword in line for keyword in self.error_keywords)
    
    def handle_error_clustering(self, error_line, log_entry):
        """에러 로그 클러스터링 처리"""
        if not self.template_miner:
            return
            
        try:
            # Drain3로 클러스터링
            result = self.template_miner.add_log_message(error_line)
            
            # 결과 처리
            cluster_id = self.get_cluster_id(result)
            template = self.get_template(result)
            
            # 클러스터 정보 업데이트
            if cluster_id not in dashboard_data['clusters']:
                dashboard_data['clusters'][cluster_id] = {
                    'template': template,
                    'count': 0,
                    'first_seen': datetime.now().isoformat(),
                    'last_seen': datetime.now().isoformat(),
                    'recent_logs': [],
                    'ai_analysis': None  # AI 분석 결과 저장
                }
            
            cluster = dashboard_data['clusters'][cluster_id]
            cluster['count'] += 1
            cluster['last_seen'] = datetime.now().isoformat()
            cluster['recent_logs'].append(log_entry)
            
            # 최근 10개 로그만 유지
            if len(cluster['recent_logs']) > 10:
                cluster['recent_logs'] = cluster['recent_logs'][-10:]
            
            # 클러스터 통계 업데이트
            dashboard_data['cluster_stats'][cluster_id] = cluster['count']
            
            # 빈발 패턴 감지 (3회 이상)
            if cluster['count'] >= 3:
                # AI 분석 수행 (첫 번째 빈발 패턴 감지시 또는 주기적으로)
                if cluster['count'] == 3 or cluster['count'] % 5 == 0:  # 3회, 8회, 13회... 마다 분석
                    if self.ollama_analyzer and self.ollama_analyzer.enabled:
                        analysis_start_time = datetime.now().strftime("%H:%M:%S")
                        logger.info(f"🤖 웹 대시보드 AI 분석 시작: {template} (시작시간: {analysis_start_time})")
                        try:
                            ai_analysis = self.ollama_analyzer.analyze_error(
                                error_log=error_line,
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
                            logger.info(f"AI 분석 완료: {template}")
                        except Exception as e:
                            logger.error(f"AI 분석 실패: {e}")
                            cluster['ai_analysis'] = None
                
                # WebSocket으로 빈발 패턴 알림 (AI 분석 결과 포함)
                socketio.emit('frequent_pattern', {
                    'cluster_id': cluster_id,
                    'template': template,
                    'count': cluster['count'],
                    'severity': self.get_severity(cluster['count']),
                    'ai_analysis': cluster.get('ai_analysis')
                })
                
                # Slack 알림 (AI 분석 결과 포함)
                if self.slack_notifier and self.slack_notifier.enabled:
                    self.slack_notifier.send_error_alert_with_ai(
                        template, cluster['count'], cluster_id, cluster.get('ai_analysis')
                    )
            
            # 전체 대시보드 데이터 업데이트
            dashboard_data['last_update'] = datetime.now().isoformat()
            
        except Exception as e:
            print(f"❌ 클러스터링 처리 오류: {e}")
    
    def get_cluster_id(self, result):
        """결과에서 클러스터 ID 추출"""
        if isinstance(result, dict):
            return result.get('cluster_id', 'unknown')
        else:
            return getattr(result, 'cluster_id', 'unknown')
    
    def get_template(self, result):
        """결과에서 템플릿 추출"""
        if isinstance(result, dict):
            return result.get('template_mined', result.get('template', 'unknown'))
        else:
            return getattr(result, 'template', 'unknown')
    
    def get_severity(self, count):
        """심각도 결정"""
        if count >= 50:
            return "매우 심각"
        elif count >= 20:
            return "심각"
        elif count >= 10:
            return "주의"
        else:
            return "경미"

# 전역 핸들러 인스턴스
web_handler = None
observer = None

def start_file_monitoring():
    """파일 모니터링 시작"""
    global web_handler, observer
    
    watch_dir = r"D:\devcon\logs"
    
    # 디렉토리 생성
    os.makedirs(watch_dir, exist_ok=True)
    
    # 핸들러와 Observer 설정
    web_handler = WebDashboardHandler()
    
    if not web_handler.template_miner:
        print("❌ Drain3 초기화 실패로 모니터링을 시작할 수 없습니다")
        return
    
    observer = Observer()
    observer.schedule(web_handler, watch_dir, recursive=True)
    observer.start()
    
    print(f"✅ 파일 모니터링 시작: {watch_dir}")

# Flask 라우트
@app.route('/')
def index():
    """메인 대시보드 페이지"""
    return render_template('dashboard.html')

@app.route('/api/stats')
def get_stats():
    """통계 데이터 API"""
    return jsonify({
        'total_logs': dashboard_data['total_logs'],
        'error_logs': dashboard_data['error_logs'],
        'error_rate': (dashboard_data['error_logs'] / max(dashboard_data['total_logs'], 1)) * 100,
        'cluster_count': len(dashboard_data['clusters']),
        'last_update': dashboard_data['last_update']
    })

@app.route('/api/clusters')
def get_clusters():
    """클러스터 데이터 API (AI 분석 결과 포함)"""
    clusters_list = []
    for cluster_id, cluster_info in dashboard_data['clusters'].items():
        cluster_data = {
            'id': cluster_id,
            'template': cluster_info['template'],
            'count': cluster_info['count'],
            'first_seen': cluster_info['first_seen'],
            'last_seen': cluster_info['last_seen'],
            'severity': web_handler.get_severity(cluster_info['count']) if web_handler else 'unknown',
            'ai_analysis': cluster_info.get('ai_analysis')  # AI 분석 결과 포함
        }
        clusters_list.append(cluster_data)
    
    # 발생 횟수 순으로 정렬
    clusters_list.sort(key=lambda x: x['count'], reverse=True)
    
    return jsonify(clusters_list)

@app.route('/api/recent-logs')
def get_recent_logs():
    """최근 로그 데이터 API"""
    return jsonify(list(dashboard_data['recent_logs']))

@app.route('/api/error-timeline')
def get_error_timeline():
    """에러 타임라인 데이터 API"""
    return jsonify(list(dashboard_data['error_timeline']))

# WebSocket 이벤트
@socketio.on('connect')
def handle_connect():
    """클라이언트 연결시"""
    print('클라이언트 연결됨')
    emit('connected', {'message': '대시보드에 연결되었습니다'})

@socketio.on('disconnect')
def handle_disconnect():
    """클라이언트 연결 해제시"""
    print('클라이언트 연결 해제됨')

@socketio.on('request_update')
def handle_request_update():
    """클라이언트가 업데이트 요청시"""
    emit('stats_update', {
        'total_logs': dashboard_data['total_logs'],
        'error_logs': dashboard_data['error_logs'],
        'cluster_count': len(dashboard_data['clusters'])
    })

def create_templates():
    """HTML 템플릿 생성"""
    templates_dir = 'templates'
    os.makedirs(templates_dir, exist_ok=True)
    
    dashboard_html = '''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Log Monitoring Dashboard</title>
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
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .header p {
            font-size: 1.2em;
            opacity: 0.9;
        }
        
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
        
        .main-content {
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
        
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }
        
        .status-running {
            background: #28a745;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
        
        .full-width {
            grid-column: 1 / -1;
        }
        
        .chart-container {
            position: relative;
            height: 300px;
            margin-top: 20px;
        }
        
        @media (max-width: 768px) {
            .main-content {
                grid-template-columns: 1fr;
            }
            
            .stats-grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Log Monitoring Dashboard</h1>
            <p>실시간 로그 모니터링 및 클러스터링 분석</p>
            <p><span class="status-indicator status-running"></span>시스템 상태: <span id="system-status">실행 중</span></p>
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
        
        <div class="main-content">
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
        
        // Socket 이벤트 처리
        socket.on('connect', function() {
            console.log('대시보드에 연결됨');
            updateStats();
            updateClusters();
            updateRecentLogs();
            updateTimeline();
        });
        
        socket.on('new_error', function(data) {
            console.log('새 에러 감지:', data);
            updateStats();
            updateRecentLogs();
        });
        
        socket.on('frequent_pattern', function(data) {
            console.log('빈발 패턴 감지:', data);
            updateClusters();
            let message = `빈발 패턴 감지: ${data.template} (${data.count}회)`;
            if (data.ai_analysis) {
                message += `\n🤖 AI 분석: ${data.ai_analysis.error_type} (신뢰도: ${data.ai_analysis.confidence}%)`;
            }
            showNotification(message);
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
                            ${cluster.ai_analysis ? `
                                <div class="ai-analysis" style="margin-top: 10px; padding: 10px; background: #f0f8ff; border-radius: 5px; border-left: 3px solid #007bff;">
                                    <div style="font-weight: bold; color: #007bff; margin-bottom: 5px;">
                                        🤖 AI 분석 결과 (신뢰도: ${cluster.ai_analysis.confidence}%)
                                    </div>
                                    <div style="font-size: 0.85em;">
                                        <div><strong>에러 유형:</strong> ${cluster.ai_analysis.error_type}</div>
                                        <div><strong>심각도:</strong> ${cluster.ai_analysis.severity}</div>
                                        <div><strong>근본 원인:</strong> ${cluster.ai_analysis.root_cause}</div>
                                        <div style="margin-top: 5px;">
                                            <strong>즉시 조치사항:</strong>
                                            <ul style="margin: 2px 0; padding-left: 15px;">
                                                ${cluster.ai_analysis.immediate_actions.map(action => `<li>${action}</li>`).join('')}
                                            </ul>
                                        </div>
                                    </div>
                                </div>
                            ` : ''}
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
        
        function getSeverityClass(severity) {
            switch(severity) {
                case '매우 심각': return 'critical';
                case '심각': return 'warning';
                case '주의': return 'info';
                default: return 'info';
            }
        }
        
        function showNotification(message) {
            // 간단한 알림 표시
            const notification = document.createElement('div');
            notification.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: #dc3545;
                color: white;
                padding: 15px 20px;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                z-index: 1000;
                animation: slideIn 0.3s ease;
            `;
            notification.textContent = message;
            document.body.appendChild(notification);
            
            setTimeout(() => {
                notification.remove();
            }, 5000);
        }
        
        // 주기적 업데이트
        setInterval(() => {
            updateStats();
            updateClusters();
            updateRecentLogs();
            updateTimeline();
        }, 5000);
        
        // CSS 애니메이션 추가
        const style = document.createElement('style');
        style.textContent = `
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
        `;
        document.head.appendChild(style);
    </script>
</body>
</html>'''
    
    with open(os.path.join(templates_dir, 'dashboard.html'), 'w', encoding='utf-8') as f:
        f.write(dashboard_html)
    
    print("✅ HTML 템플릿 생성 완료")

def main():
    """메인 실행 함수"""
    print("🚀 Log Monitoring Web Dashboard 시작")
    print("=" * 50)
    
    # 템플릿 생성
    create_templates()
    
    # 파일 모니터링 시작 (별도 스레드에서)
    monitoring_thread = threading.Thread(target=start_file_monitoring, daemon=True)
    monitoring_thread.start()
    
    # Flask 서버 시작
    print("🌐 웹 대시보드 서버 시작 중...")
    print("📱 브라우저에서 http://localhost:5000 접속하세요")
    print("🛑 Ctrl+C로 종료")
    
    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        print("\n⏹️ 대시보드 서버 종료")
        if observer:
            observer.stop()
            observer.join()
        print("✅ 종료 완료")

if __name__ == "__main__":
    main()
