"""
파일명: 2_clustering_monitor.py (로컬 저장 기능 포함 업데이트 버전)
목적: Watchdog + Drain3를 이용한 실시간 로그 모니터링 + 로컬 저장
사용법: python 2_clustering_monitor.py
"""

import os
import time
from datetime import datetime, timedelta
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv
load_dotenv()
from drain3 import TemplateMiner

# Slack 연동 모듈 시도
try:
    from slack_integration import SlackNotifier
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False
    print("Slack 연동 모듈을 찾을 수 없습니다. 콘솔 출력만 진행합니다.")
    
# 스택트레이스 프로세서 시도
try:
    from stack_trace_processor import EnhancedStackTraceProcessor
    STACK_PROCESSOR_AVAILABLE = True
except ImportError:
    STACK_PROCESSOR_AVAILABLE = False
    print("스택트레이스 프로세서를 찾을 수 없습니다. 기본 처리만 진행합니다.")

# 로컬 저장 모듈 시도
try:
    from log_block_saver import LogBlockSaver
    LOG_SAVER_AVAILABLE = True
except ImportError:
    LOG_SAVER_AVAILABLE = False
    print("로그 블록 저장 모듈을 찾을 수 없습니다. 로컬 저장 기능 비활성화")

try:
    from ollama_integration import OllamaErrorAnalyzer
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    print("Ollama 연동 모듈을 찾을 수 없습니다. AI 분석 기능이 비활성화됩니다.")

class LogClusteringHandler(FileSystemEventHandler):
    """실시간 로그 클러스터링 핸들러 (로컬 저장 기능 포함)"""
    
    def __init__(self):
        # 파일별 마지막 읽은 위치 저장
        self.last_position = {}
        
        # 에러 키워드 정의 (확장)
        self.error_keywords = [
            'ERROR', 'FATAL', 'Exception', 'Failed', 'Error:', 
            'Caused by:', 'at java.', 'at org.', '### Error',
            'NullPointerException', 'SQLException', 'OutOfMemoryError'
        ]
        
        # Drain3 엔진 초기화
        self.template_miner = self.initialize_drain3()
        
        # 통계 변수
        self.total_logs = 0
        self.error_logs = 0
        self.clustered_logs = 0
        
        # 스택트레이스 처리를 위한 버퍼
        self.line_buffer = []
        self.buffer_timeout = timedelta(seconds=2)
        self.last_buffer_time = None
        
        # 클러스터 알림 방지 (중복 알림 방지)
        self.last_alert_time = {}
        self.alert_cooldown = timedelta(minutes=5)
        
        # 클러스터별 원본 예시 보관용
        self.error_examples = {}
        
        if self.template_miner:
            print("✅ Drain3 엔진 초기화 완료")
        else:
            print("❌ Drain3 엔진 초기화 실패")

        # Slack 연동 초기화
        if SLACK_AVAILABLE:
            self.slack_notifier = SlackNotifier()
            if self.slack_notifier.enabled:
                print("✅ Slack 연동 활성화됨")
            else:
                print("⚠️ Slack 비활성화 - 콘솔 출력만 진행")
        else:
            self.slack_notifier = None

        # 스택트레이스 프로세서 초기화
        if STACK_PROCESSOR_AVAILABLE:
            self.stack_processor = EnhancedStackTraceProcessor()
            print("✅ 스택트레이스 프로세서 활성화됨")
        else:
            self.stack_processor = None
        
        # 로그 블록 로컬 저장 기능 초기화
        if LOG_SAVER_AVAILABLE:
            self.log_saver = LogBlockSaver()
            print("✅ 로그 블록 로컬 저장 기능 활성화됨")
        else:
            self.log_saver = None
            print("⚠️ 로컬 저장 기능 비활성화")
        
        # Ollama AI 분석기 초기화
        if OLLAMA_AVAILABLE:
            self.ollama_analyzer = OllamaErrorAnalyzer()
            if self.ollama_analyzer.enabled:
                print("✅ Ollama AI 분석기 활성화됨")
            else:
                print("⚠️ Ollama 비활성화 - 기본 분석만 진행")
        else:
            self.ollama_analyzer = None
    
    def initialize_drain3(self):
        """Drain3 초기화 (버전 호환성 개선)"""
        try:
            # 다양한 Drain3 버전에 대한 호환성 처리
            template_miner = None
            
            # 방법 1: 기본 생성자 시도
            try:
                template_miner = TemplateMiner()
                print("✅ 기본 생성자로 Drain3 초기화 성공")
            except Exception as e1:
                print(f"⚠️ 기본 생성자 실패: {e1}")
                
                # 방법 2: profiling_enabled 파라미터만 시도
                try:
                    template_miner = TemplateMiner(profiling_enabled=False)
                    print("✅ profiling_enabled=False로 Drain3 초기화 성공")
                except Exception as e2:
                    print(f"⚠️ profiling_enabled 파라미터 실패: {e2}")
                    
                    # 방법 3: 완전 기본값으로 재시도
                    try:
                        import drain3
                        template_miner = drain3.TemplateMiner()
                        print("✅ 모듈 직접 접근으로 Drain3 초기화 성공")
                    except Exception as e3:
                        print(f"❌ 모든 초기화 방법 실패: {e3}")
                        raise e3
            
            # 성공적으로 생성되었다면 설정 최적화 시도
            if template_miner and hasattr(template_miner, 'drain'):
                try:
                    # 클러스터링 품질 향상을 위한 설정
                    template_miner.drain.sim_th = 0.4  # 유사도 임계값
                    template_miner.drain.depth = 4     # 트리 깊이
                    if hasattr(template_miner.drain, 'max_children'):
                        template_miner.drain.max_children = 100  # 자식 노드 최대 수
                    print("✅ Drain3 고급 설정 적용 완료")
                except Exception as config_error:
                    print(f"⚠️ 고급 설정 적용 실패 (기본값 사용): {config_error}")
            
            return template_miner
            
        except Exception as e:
            print(f"❌ Drain3 초기화 완전 실패: {e}")
            print("💡 해결 방법:")
            print("   1. pip install drain3 --upgrade")
            print("   2. pip install drain3==0.9.6")
            print("   3. 또는 conda install drain3")
            return None
    
    def on_modified(self, event):
        """파일 변경 감지시 호출"""
        if not self.template_miner:
            return
            
        # .log 파일만 처리
        if event.is_directory or not event.src_path.endswith('.log'):
            return
        
        filename = os.path.basename(event.src_path)
        print(f"\n📁 파일 변경: {filename}")
        
        self.process_new_logs(event.src_path)
    
    def process_new_logs(self, file_path):
        """새로운 로그 라인 처리 (개선된 멀티라인 지원)"""
        if not self.template_miner:
            return
            
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                # 마지막 위치부터 읽기
                last_pos = self.last_position.get(file_path, 0)
                f.seek(last_pos)
                
                new_lines = f.readlines()
                self.last_position[file_path] = f.tell()
                
                print(f"   📄 새 라인: {len(new_lines)}개")
                
                # 각 라인을 처리
                for line in new_lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    self.total_logs += 1
                    self.process_single_line(line)
                
                # 버퍼 타임아웃 체크
                self.check_buffer_timeout()
                        
        except Exception as e:
            print(f"❌ 파일 읽기 오류: {e}")
    
    def process_single_line(self, line):
        """단일 라인 처리 (스택트레이스 고려)"""
        current_time = datetime.now()
        
        # 스택트레이스 프로세서가 있으면 사용
        if self.stack_processor:
            result = self.stack_processor.process_line(line, current_time)
            if result:
                if result.get('is_single_line', False):
                    # 일반 로그 라인
                    if self.is_error_line(line):
                        self.handle_error_clustering(line)
                else:
                    # 완성된 스택트레이스
                    self.handle_stack_trace_clustering(result)
            return
        
        # 기본 처리 (스택트레이스 프로세서 없을 때)
        if self.is_error_line(line):
            self.add_to_buffer(line, current_time)
        else:
            # 일반 로그는 버퍼 플러시
            self.flush_buffer()
    
    def add_to_buffer(self, line, timestamp):
        """라인을 버퍼에 추가"""
        self.line_buffer.append(line)
        self.last_buffer_time = timestamp
        
        # 버퍼가 너무 크면 플러시
        if len(self.line_buffer) >= 10:  # 최대 10라인
            self.flush_buffer()
    
    def check_buffer_timeout(self):
        """버퍼 타임아웃 체크"""
        if (self.line_buffer and self.last_buffer_time and 
            datetime.now() - self.last_buffer_time > self.buffer_timeout):
            self.flush_buffer()
    
    def flush_buffer(self):
        """버퍼의 내용을 클러스터링에 전달"""
        if not self.line_buffer:
            return
        
        if len(self.line_buffer) == 1:
            # 단일 라인
            self.handle_error_clustering(self.line_buffer[0])
        else:
            # 멀티라인 스택트레이스
            combined_log = '\n'.join(self.line_buffer)
            self.handle_multiline_clustering(combined_log)
        
        self.line_buffer = []
        self.last_buffer_time = None
    
    def is_error_line(self, line):
        """에러 라인 판단 (확장된 패턴)"""
        return any(keyword in line for keyword in self.error_keywords)
    
    def handle_error_clustering(self, error_line):
        """단일 에러 로그 클러스터링 처리"""
        self.error_logs += 1
        self._process_clustering(error_line, is_multiline=False)
    
    def handle_multiline_clustering(self, multiline_log):
        """멀티라인 스택트레이스 클러스터링 처리"""
        self.error_logs += 1
        
        # 스택트레이스 요약 생성 (간단한 버전)
        lines = multiline_log.split('\n')
        summary = self.create_simple_stack_summary(lines)
        
        self._process_clustering(summary, is_multiline=True, original=multiline_log)
    
    def handle_stack_trace_clustering(self, stack_result):
        """완성된 스택트레이스 클러스터링 처리"""
        self.error_logs += 1
        summary = stack_result.get('summary', '')
        original = stack_result.get('original', '')
        
        self._process_clustering(summary, is_multiline=True, original=original)
    
    def create_simple_stack_summary(self, lines):
        """간단한 스택트레이스 요약 생성"""
        if not lines:
            return "Unknown Error"
        
        # 첫 번째 라인에서 예외 타입 추출
        first_line = lines[0]
        
        # Exception: message 패턴
        import re
        exception_match = re.search(r'(\w*Exception|\w*Error):\s*(.+)', first_line)
        if exception_match:
            exc_type = exception_match.group(1)
            message = exception_match.group(2)[:50]  # 메시지 길이 제한
            return f"{exc_type}: {message}"
        
        # 기본적으로 첫 번째 라인 반환
        return first_line[:100]
    
    def _process_clustering(self, log_content, is_multiline=False, original=None):
        """실제 클러스터링 처리"""
        if not self.template_miner:
            print("❌ Drain3 엔진이 초기화되지 않음")
            return
            
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        print(f"\n🚨 [{timestamp}] 에러 감지! {'(멀티라인)' if is_multiline else '(단일라인)'}")
        print(f"📝 로그: {log_content}")
        
        try:
            # Drain3로 클러스터링
            result = self.template_miner.add_log_message(log_content)
            self.clustered_logs += 1
            
            # 결과 처리
            cluster_id = self.get_cluster_id(result)
            template = self.get_template(result)
            
            # 원본 로그 예시 저장
            self.store_original_example(cluster_id, original or log_content)
            
            print(f"🏷️  클러스터 ID: {cluster_id}")
            print(f"📋 템플릿: {template}")
            
            # 클러스터 크기 확인
            cluster_size = self.get_cluster_size(cluster_id)
            if cluster_size > 0:
                print(f"📊 발생 횟수: {cluster_size}번")
                
                # 빈발 패턴 감지 (중복 알림 방지 포함)
                if cluster_size >= 3 and self.should_send_alert(cluster_id):
                    print(f"⚠️  빈발 패턴 감지! {cluster_size}번 발생")
                    # 향상된 알림 전송 (예시 포함)
                    examples = self.get_examples_for_cluster(cluster_id)
                    self.alert_frequent_error(template, cluster_size, cluster_id, examples)
                    self.last_alert_time[cluster_id] = datetime.now()
                    
                    self.alert_frequent_error(error_line, template, cluster_size, cluster_id)
            else:
                print(f"🔍 디버깅: 클러스터 {cluster_id} 크기가 0인 이유 조사")
                clusters_dict = self.get_clusters_dict()
                print(f"   전체 클러스터 수: {len(clusters_dict)}")
                print(f"   클러스터 ID {cluster_id} 존재 여부: {cluster_id in clusters_dict}")
                
        except Exception as e:
            print(f"❌ 클러스터링 처리 오류: {e}")
        
        print("-" * 50)
    
    def should_send_alert(self, cluster_id):
        """알림 전송 여부 판단 (쿨다운 적용)"""
        if cluster_id not in self.last_alert_time:
            return True
        
        time_since_last = datetime.now() - self.last_alert_time[cluster_id]
        return time_since_last > self.alert_cooldown
    
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
    
    def get_cluster_size(self, cluster_id):
        """클러스터 크기 조회"""
        try:
            clusters = self.get_clusters_dict()
            if clusters and cluster_id in clusters:
                cluster = clusters[cluster_id]
                return getattr(cluster, 'size', 0)
            return 0
        except Exception:
            return 0
    
    def get_clusters_dict(self):
        """클러스터 딕셔너리 조회"""
        try:
            if hasattr(self.template_miner, 'drain') and hasattr(self.template_miner.drain, 'id_to_cluster'):
                return self.template_miner.drain.id_to_cluster
            return {}
        except Exception as e:
            print(f"   클러스터 딕셔너리 조회 오류: {e}")
            return {}
    
    def store_original_example(self, cluster_id, original_text):
        """클러스터별 원본 예시 저장"""
        if cluster_id not in self.error_examples:
            self.error_examples[cluster_id] = []
        
        # 최근 3개 예시만 보관 (메모리 절약)
        if len(self.error_examples[cluster_id]) >= 3:
            self.error_examples[cluster_id].pop(0)
        
        self.error_examples[cluster_id].append({
            'text': original_text,
            'timestamp': datetime.now()
        })
    
    def get_examples_for_cluster(self, cluster_id):
        """특정 클러스터의 예시들 반환"""
        return self.error_examples.get(cluster_id, [])
    
    def alert_frequent_error(self, template, count, cluster_id, examples=None):
        """빈발 에러 알림 (로컬 저장 + Slack)"""
        print(f"🔥 긴급! 반복 에러 패턴: {template}")
        print(f"📈 발생 횟수: {count}번")
        
        # 패턴 분석 및 권장사항
        recommendations = self.analyze_error_pattern(str(template))
        for rec in recommendations:
            print(f"🎯 권장사항: {rec}")
        
        # 예시 데이터 확인
        if not examples:
            examples = self.get_examples_for_cluster(cluster_id)
        
        print(f"🔍 디버깅 - 클러스터 {cluster_id} 예시 개수: {len(examples) if examples else 0}")
        
        # 1순위: 로컬 저장
        if self.log_saver:
            try:
                filepath = self.log_saver.save_error_alert(cluster_id, template, count, examples)
                print(f"✅ 로컬 저장 완료: {filepath}")
                
                # 원본 로그도 별도 저장
                if examples:
                    raw_logs = [ex.get('text', str(ex)) if isinstance(ex, dict) else str(ex) for ex in examples]
                    self.log_saver.save_raw_log_cluster(cluster_id, raw_logs)
                    
            except Exception as e:
                print(f"❌ 로컬 저장 오류: {e}")
        
        # 2순위: Slack 전송
        if self.slack_notifier:
            try:
                # 향상된 Slack 연동인지 확인
                if hasattr(self.slack_notifier, 'send_error_alert') and examples:
                    # 예시 포함해서 전송
                    success = self.slack_notifier.send_error_alert(template, count, cluster_id, examples)
                    if success:
                        print("✅ Slack 알림 전송 성공")
                    else:
                        print("❌ Slack 알림 전송 실패")
                else:
                    # 기본 방식으로 전송
                    self.slack_notifier.send_error_alert(template, count, cluster_id)
                    print("ℹ️ 기본 Slack 알림 전송")
                    
            except Exception as e:
                print(f"❌ Slack 전송 오류: {e}")
        else:
            print("⚠️ Slack 연동 비활성화")
    
    def analyze_error_pattern(self, template_str):
        """에러 패턴 분석 및 권장사항 생성"""
        template_lower = template_str.lower()
        recommendations = []
        
        if 'nullpointer' in template_lower:
            recommendations.append("널체크 코드 추가 필요")
        if 'database' in template_lower or 'sql' in template_lower:
            recommendations.append("DB 커넥션 풀 상태 확인")
        if 'outofmemory' in template_lower:
            recommendations.append("메모리 사용량 및 힙 크기 확인")
        if 'filenotfound' in template_lower:
            recommendations.append("파일 경로 및 권한 확인")
        if 'timeout' in template_lower:
            recommendations.append("네트워크 연결 및 타임아웃 설정 확인")
        
        if not recommendations:
            recommendations.append("로그 패턴 분석 필요")
        
        return recommendations
    
    def print_summary(self):
        """현황 요약 출력 (로컬 저장 포함)"""
        if not self.template_miner:
            print("❌ Drain3 엔진 미초기화로 요약 불가")
            return
        
        print(f"\n📈 === 현황 요약 ===")
        print(f"⏰ 시간: {datetime.now().strftime('%H:%M:%S')}")
        print(f"📋 총 로그: {self.total_logs}개")
        print(f"🚨 에러 로그: {self.error_logs}개")
        print(f"🏷️  클러스터링된 로그: {self.clustered_logs}개")
        
        # 클러스터 정보
        clusters_dict = self.get_clusters_dict()
        print(f"📊 클러스터 수: {len(clusters_dict)}개")
        
        top_clusters = []
        if clusters_dict:
            print(f"\n🏆 TOP 5 에러 패턴:")
            
            # 클러스터를 크기 순으로 정렬
            cluster_items = []
            for cluster_id, cluster in clusters_dict.items():
                size = getattr(cluster, 'size', 0)
                template = self.get_cluster_template(cluster)
                cluster_items.append((cluster_id, template, size))
            
            # 크기 순으로 정렬
            sorted_clusters = sorted(cluster_items, key=lambda x: x[2], reverse=True)
            
            # 상위 5개 출력 및 저장
            for i, (cid, template, size) in enumerate(sorted_clusters[:5], 1):
                severity = self.get_severity_indicator(size)
                print(f"   {i}. [{size}번] {severity} {template}")
                top_clusters.append((cid, template, size))
        
        # 통계
        if self.total_logs > 0:
            error_rate = (self.error_logs / self.total_logs) * 100
            clustering_rate = (self.clustered_logs / self.error_logs) * 100 if self.error_logs > 0 else 0
            
            print(f"\n📊 통계:")
            print(f"   에러율: {error_rate:.1f}%")
            print(f"   클러스터링율: {clustering_rate:.1f}%")
            
            if error_rate > 80:
                print(f"🚨 시스템 상태 위험! 에러율이 {error_rate:.1f}%입니다")
            elif error_rate > 50:
                print(f"⚠️  시스템 상태 주의! 에러율이 {error_rate:.1f}%입니다")
        
        # 10분마다 요약 저장
        current_time = datetime.now()
        if (not hasattr(self, 'last_summary_saved') or 
            (current_time - self.last_summary_saved).total_seconds() >= 600):  # 10분
            
            if len(top_clusters) > 0:
                handler_stats = {
                    'total_logs': self.total_logs,
                    'error_logs': self.error_logs,
                    'clustered_logs': self.clustered_logs,
                    'top_clusters': top_clusters
                }
                
                # 로컬 저장
                if self.log_saver:
                    try:
                        filepath = self.log_saver.save_summary_report(handler_stats)
                        print(f"✅ 로컬 요약 저장 완료: {filepath}")
                    except Exception as e:
                        print(f"❌ 로컬 요약 저장 오류: {e}")
                
                # Slack 전송 (향상된 버전이 있다면)
                if (self.slack_notifier and hasattr(self.slack_notifier, 'send_clustering_summary')):
                    try:
                        self.slack_notifier.send_clustering_summary(handler_stats)
                        print("📤 Slack 요약 정보 전송됨")
                    except Exception as e:
                        print(f"❌ Slack 요약 전송 오류: {e}")
                
                self.last_summary_saved = current_time
        
        # 로컬 리포트 요약 출력
        if self.log_saver:
            self.log_saver.print_report_summary()
    
    def get_severity_indicator(self, count):
        """심각도 표시기 반환"""
        if count >= 50:
            return "🔴"  # 매우 심각
        elif count >= 20:
            return "🟠"  # 심각
        elif count >= 10:
            return "🟡"  # 주의
        else:
            return "🟢"  # 경미
    
    def get_cluster_template(self, cluster):
        """클러스터에서 템플릿 추출"""
        try:
            if hasattr(cluster, 'log_template_tokens'):
                return ' '.join(cluster.log_template_tokens)
            elif hasattr(cluster, 'get_template'):
                return cluster.get_template()
            else:
                return str(cluster)
        except Exception:
            return "unknown"

def start_monitoring():
    """모니터링 시작 (로컬 저장 기능 포함)"""
    watch_dir = r"D:\devcon\logs"
    
    print("🚀 실시간 로그 모니터링 시작 (로컬 저장 기능 포함)")
    print(f"📁 감시 디렉토리: {watch_dir}")
    print("✨ 기능:")
    print("   - 멀티라인 스택트레이스 지원")
    print("   - 중복 알림 방지 (5분 쿨다운)")
    print("   - 향상된 에러 패턴 분석")
    print("   - 로컬 HTML/JSON 리포트 자동 생성")
    print("   - Slack 연동 (설정된 경우)")
    
    # 디렉토리 생성
    os.makedirs(watch_dir, exist_ok=True)
    
    # 핸들러와 Observer 설정
    handler = LogClusteringHandler()
    
    if not handler.template_miner:
        print("❌ Drain3 초기화 실패로 모니터링을 시작할 수 없습니다")
        return
    
    observer = Observer()
    observer.schedule(handler, watch_dir, recursive=True)
    observer.start()
    
    print("👁️  파일 감시 시작됨")
    print("💡 다른 터미널에서 3_log_generator.py 실행하세요")
    print("🛑 Ctrl+C로 종료")
    
    try:
        while True:
            time.sleep(1)
            # 10초마다 요약 출력하려면 카운터 사용
            if hasattr(handler, 'summary_counter'):
                handler.summary_counter += 1
            else:
                handler.summary_counter = 1
            
            if handler.summary_counter >= 10:  # 10초마다
                handler.print_summary()
                handler.summary_counter = 0
            
    except KeyboardInterrupt:
        print(f"\n⏹️  모니터링 중단")
        handler.print_summary()  # 최종 요약
        observer.stop()
        observer.join()
        print("✅ 종료 완료")

if __name__ == "__main__":
    start_monitoring()