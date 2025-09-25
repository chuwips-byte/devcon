"""
파일명: 2_clustering_monitor.py
목적: Watchdog + Drain3를 이용한 실시간 로그 모니터링 (Jira/Confluence 연동 추가)
사용법: python 2_clustering_monitor.py
"""

import os
import time
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv
from rag.vector_store import search_similar_error
from rag.embedder import embed

load_dotenv()
from drain3 import TemplateMiner

try:
    from slack_integration import SlackNotifier
    SLACK_AVAILABLE = True
except ImportError:
    SLACK_AVAILABLE = False
    print("Slack 연동 모듈을 찾을 수 없습니다. 콘솔 출력만 진행합니다.")

class LogClusteringHandler(FileSystemEventHandler):
    """실시간 로그 클러스터링 핸들러"""
    
    def __init__(self):
        # 파일별 마지막 읽은 위치 저장
        self.last_position = {}
        
        # 에러 키워드 정의
        self.error_keywords = ['ERROR', 'FATAL', 'Exception', 'Failed', 'Error:']
        
        # Drain3 엔진 초기화
        self.template_miner = self.initialize_drain3()
        
        # 통계 변수
        self.total_logs = 0
        self.error_logs = 0

        # 🔹 필수 속성들 (빠지면 AttributeError 발생함)
        self._cluster_samples = {}          # 클러스터별 샘플 라인 저장
        self.alert_min_count = int(os.getenv("ALERT_MIN_COUNT", "1"))  # 최소 알림 건수
        self.alert_cooldown = int(os.getenv("ALERT_COOLDOWN_SEC", "600"))  # 알림 쿨다운(초)
        self._last_alert_ts = {}            # cluster_id -> 마지막 알림 시각(epoch)

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

    def initialize_drain3(self):
        """Drain3 초기화"""
        try:
            template_miner = TemplateMiner()
            print("✅ 기본 설정으로 Drain3 초기화 성공")
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
        
        filename = os.path.basename(event.src_path)
        print(f"\n📁 파일 변경: {filename}")
        
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
                
                print(f"   📄 새 라인: {len(new_lines)}개")
                
                # 각 라인 검사
                for line in new_lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    self.total_logs += 1
                    
                    # 에러 라인인지 확인
                    if self.is_error_line(line):
                        self.error_logs += 1
                        self.handle_error_clustering(line)
                        
        except Exception as e:
            print(f"❌ 파일 읽기 오류: {e}")
    
    def is_error_line(self, line):
        """에러 라인 판단"""
        return any(keyword in line for keyword in self.error_keywords)
    
    def handle_error_clustering(self, error_line):
        """에러 로그 클러스터링 처리"""
        if not self.template_miner:
            print("❌ Drain3 엔진이 초기화되지 않음")
            return
            
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        print(f"\n🚨 [{timestamp}] 에러 감지!")
        print(f"📝 로그: {error_line}")
        
        try:
            # Drain3로 클러스터링
            result = self.template_miner.add_log_message(error_line)
            
            # 결과 처리 (dict 또는 객체 모두 지원)
            cluster_id = self.get_cluster_id(result)
            template = self.get_template(result)

            # 최근 샘플 라인 보관
            self._cluster_samples[str(cluster_id)] = error_line
            
            print(f"🏷️  클러스터 ID: {cluster_id}")
            print(f"📋 템플릿: {template}")
            
            # 클러스터 정보 분석
            cluster_size = self.get_cluster_size(cluster_id)
            if cluster_size > 0:
                print(f"📊 발생 횟수: {cluster_size}번")
                
                # 빈발 패턴 감지(임계+쿨다운)
                if cluster_size >= self.alert_min_count:
                    now_sec = time.time()
                    last = self._last_alert_ts.get(str(cluster_id), 0)
                    if now_sec - last >= self.alert_cooldown:
                        self._last_alert_ts[str(cluster_id)] = now_sec
                        self.alert_frequent_error(template, cluster_size, cluster_id)
                    else:
                        remain = int(self.alert_cooldown - (now_sec - last))
                        print(f"⏳ 알림 쿨다운 중({remain}s 남음) - cluster:{cluster_id}")
            else:
                print(f"🔍 디버깅: 클러스터 {cluster_id} 크기가 0인 이유 조사")
                clusters_dict = self.get_clusters_dict()
                print(f"   전체 클러스터 수: {len(clusters_dict)}")
                print(f"   클러스터 ID {cluster_id} 존재 여부: {cluster_id in clusters_dict}")
                
        except Exception as e:
            print(f"❌ 클러스터링 처리 오류: {e}")
        
        print("-" * 50)
    
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
        try:
            if hasattr(self.template_miner, 'drain') and hasattr(self.template_miner.drain, 'id_to_cluster'):
                id_to_cluster = self.template_miner.drain.id_to_cluster
                if isinstance(id_to_cluster, dict):
                    print(f"   id_to_cluster 발견: {len(id_to_cluster)}개 클러스터")
                    return id_to_cluster
            
            if hasattr(self.template_miner, 'drain') and hasattr(self.template_miner.drain, 'clusters'):
                clusters_values = self.template_miner.drain.clusters
                reconstructed = {}
                
                for cluster in clusters_values:
                    if hasattr(cluster, 'cluster_id'):
                        cluster_id = cluster.cluster_id
                        reconstructed[cluster_id] = cluster
                
                if len(reconstructed) > 0:
                    print(f"   클러스터 재구성 성공: {len(reconstructed)}개")
                    return reconstructed
            
            return {}
        except Exception as e:
            print(f"   클러스터 딕셔너리 조회 오류: {e}")
            return {}
    
    def alert_frequent_error(self, template, count, cluster_id):
        """빈발 에러 알림 (Slack + Jira + RAG)"""
        print(f"🔥 긴급! 반복 에러 패턴: {template}")
        print(f"📈 발생 횟수: {count}번")
        
        # 가이드
        template_str = str(template).lower()
        if 'nullpointer' in template_str:
            print(f"🎯 권장사항: 널체크 코드 추가 필요")
        elif 'database' in template_str or 'connection' in template_str:
            print(f"🎯 권장사항: DB 커넥션 풀 상태 확인")
        elif 'outofmemory' in template_str:
            print(f"🎯 권장사항: 메모리 사용량 및 힙 크기 확인")
        elif 'filenotfound' in template_str:
            print(f"🎯 권장사항: 파일 경로 및 권한 확인")
        
        # Slack 알림
        if self.slack_notifier:
            try:
                self.slack_notifier.send_error_alert(template, count, cluster_id)
            except Exception as e:
                print(f"Slack 알림 실패: {e}")

        # 🔹 RAG 검색
        print(f"💡 TODO: RAG 시스템으로 해결책 검색")
        similar = search_similar_error(template, embed)
        for match in similar:
            print(f"🔎 유사 이슈: {match['text']} (출처: {match['issueKey']})")

    def print_summary(self):
        """현황 요약 출력"""
        if not self.template_miner:
            print("❌ Drain3 엔진 미초기화로 요약 불가")
            return
        
        print(f"\n📈 === 현황 요약 ===")
        print(f"⏰ 시간: {datetime.now().strftime('%H:%M:%S')}")
        print(f"📋 총 로그: {self.total_logs}개")
        print(f"🚨 에러 로그: {self.error_logs}개")
        
        clusters_dict = self.get_clusters_dict()
        print(f"🏷️  클러스터: {len(clusters_dict)}개")
        
        if clusters_dict:
            print(f"\n🏆 TOP 5 에러 패턴:")
            cluster_items = []
            for cluster_id, cluster in clusters_dict.items():
                size = getattr(cluster, 'size', 0)
                template = self.get_cluster_template(cluster)
                cluster_items.append((cluster_id, template, size))
            
            sorted_clusters = sorted(cluster_items, key=lambda x: x[2], reverse=True)
            for i, (cid, template, size) in enumerate(sorted_clusters[:5], 1):
                print(f"   {i}. [{size}번] {template}")
                if size >= 50:
                    print(f"      🔴 매우 심각 - 즉시 조치 필요")
                elif size >= 20:
                    print(f"      🟠 심각 - 빠른 조치 필요")
                elif size >= 10:
                    print(f"      🟡 주의 - 모니터링 필요")
                else:
                    print(f"      🟢 경미 - 관찰 중")
        else:
            print(f"   아직 에러 패턴이 발견되지 않았습니다.")
        
        if self.total_logs > 0:
            error_rate = (self.error_logs / self.total_logs) * 100
            print(f"📊 에러율: {error_rate:.1f}%")

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
    """모니터링 시작"""
    watch_dir = r"D:\devcon\logs"

    print("🚀 실시간 로그 모니터링 시작 (Jira/Confluence 연동 버전)")
    print(f"📁 감시 디렉토리: {watch_dir}")
    
    os.makedirs(watch_dir, exist_ok=True)
    
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
            if hasattr(handler, 'summary_counter'):
                handler.summary_counter += 1
            else:
                handler.summary_counter = 1
            
            if handler.summary_counter >= 10:  # 10초마다
                handler.print_summary()
                handler.summary_counter = 0
            
    except KeyboardInterrupt:
        print(f"\n⏹️  모니터링 중단")
        handler.print_summary()
        observer.stop()
        observer.join()
        print("✅ 종료 완료")


if __name__ == "__main__":
    start_monitoring()
