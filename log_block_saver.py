"""
로그 블록 로컬 저장 모듈
클러스터링 결과를 로컬 파일로 저장하여 분석 및 확인 가능
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Any
from pathlib import Path

class LogBlockSaver:
    def __init__(self, base_dir="D:/devcon/log_reports"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # 오늘 날짜별 폴더 생성
        today = datetime.now().strftime("%Y-%m-%d")
        self.today_dir = self.base_dir / today
        self.today_dir.mkdir(exist_ok=True)
        
        # 세부 폴더들 생성
        self.error_alerts_dir = self.today_dir / "error_alerts"
        self.summaries_dir = self.today_dir / "summaries" 
        self.raw_logs_dir = self.today_dir / "raw_logs"
        
        for dir_path in [self.error_alerts_dir, self.summaries_dir, self.raw_logs_dir]:
            dir_path.mkdir(exist_ok=True)
        
        print(f"로그 블록 저장 위치: {self.base_dir}")
    
    def save_error_alert(self, cluster_id: int, template: str, count: int, examples: List = None):
        """에러 알림을 로컬 파일로 저장"""
        timestamp = datetime.now()
        filename = f"error_{cluster_id}_{timestamp.strftime('%H%M%S')}.json"
        filepath = self.error_alerts_dir / filename
        
        # 심각도 판단
        severity = self._get_severity(count)
        
        # 저장할 데이터 구성
        alert_data = {
            "timestamp": timestamp.isoformat(),
            "cluster_id": cluster_id,
            "template": template,
            "count": count,
            "severity": severity,
            "examples": examples or [],
            "recommendations": self._get_recommendations(template)
        }
        
        # JSON으로 저장
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(alert_data, f, ensure_ascii=False, indent=2, default=str)
        
        # HTML 리포트도 생성
        self._save_error_html_report(alert_data, filepath.with_suffix('.html'))
        
        print(f"에러 알림 저장됨: {filepath}")
        return filepath
    
    def save_summary_report(self, handler_stats: Dict[str, Any]):
        """요약 리포트를 로컬 파일로 저장"""
        timestamp = datetime.now()
        filename = f"summary_{timestamp.strftime('%H%M%S')}.json"
        filepath = self.summaries_dir / filename
        
        # 요약 데이터 구성
        summary_data = {
            "timestamp": timestamp.isoformat(),
            "stats": handler_stats,
            "analysis": self._analyze_summary(handler_stats)
        }
        
        # JSON으로 저장
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2, default=str)
        
        # HTML 요약 리포트 생성
        self._save_summary_html_report(summary_data, filepath.with_suffix('.html'))
        
        print(f"요약 리포트 저장됨: {filepath}")
        return filepath
    
    def save_raw_log_cluster(self, cluster_id: int, original_logs: List[str]):
        """원본 로그들을 클러스터별로 저장"""
        timestamp = datetime.now()
        filename = f"cluster_{cluster_id}_{timestamp.strftime('%H%M%S')}.txt"
        filepath = self.raw_logs_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"클러스터 ID: {cluster_id}\n")
            f.write(f"수집 시간: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"로그 개수: {len(original_logs)}\n")
            f.write("="*80 + "\n\n")
            
            for i, log in enumerate(original_logs, 1):
                f.write(f"[{i:03d}] {log}\n")
                f.write("-"*60 + "\n")
        
        print(f"원본 로그 저장됨: {filepath}")
        return filepath
    
    def _save_error_html_report(self, alert_data: Dict, filepath: Path):
        """에러 알림 HTML 리포트 생성"""
        severity_colors = {
            "critical": "#dc3545",
            "high": "#fd7e14", 
            "medium": "#ffc107",
            "low": "#28a745"
        }
        
        color = severity_colors.get(alert_data["severity"], "#6c757d")
        
        html_content = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>에러 알림 - 클러스터 {alert_data['cluster_id']}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
        .header {{ background: {color}; color: white; padding: 20px; border-radius: 8px; }}
        .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0; }}
        .info-box {{ background: #f8f9fa; padding: 15px; border-radius: 5px; border-left: 4px solid {color}; }}
        .examples {{ background: #fff; border: 1px solid #dee2e6; padding: 15px; border-radius: 5px; margin: 10px 0; }}
        .log-example {{ background: #f1f3f4; padding: 10px; margin: 10px 0; border-radius: 3px; font-family: monospace; font-size: 14px; }}
        .recommendations {{ background: #d1ecf1; padding: 15px; border-radius: 5px; border-left: 4px solid #bee5eb; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚨 빈발 에러 패턴 감지</h1>
        <p>클러스터 ID: {alert_data['cluster_id']} | 심각도: {alert_data['severity'].upper()} | 시간: {alert_data['timestamp']}</p>
    </div>
    
    <div class="info-grid">
        <div class="info-box">
            <h3>📈 발생 정보</h3>
            <p><strong>발생 횟수:</strong> {alert_data['count']}번</p>
            <p><strong>심각도:</strong> {alert_data['severity']}</p>
        </div>
        <div class="info-box">
            <h3>🏷️ 클러스터 정보</h3>
            <p><strong>클러스터 ID:</strong> {alert_data['cluster_id']}</p>
            <p><strong>감지 시간:</strong> {datetime.fromisoformat(alert_data['timestamp']).strftime('%H:%M:%S')}</p>
        </div>
    </div>
    
    <div class="info-box">
        <h3>📋 에러 패턴</h3>
        <div class="log-example">{alert_data['template']}</div>
    </div>
    
    <div class="examples">
        <h3>📝 원본 로그 예시</h3>
        {self._format_examples_html(alert_data['examples'])}
    </div>
    
    <div class="recommendations">
        <h3>🎯 권장사항</h3>
        {self._format_recommendations_html(alert_data['recommendations'])}
    </div>
</body>
</html>
        """
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
    
    def _save_summary_html_report(self, summary_data: Dict, filepath: Path):
        """요약 리포트 HTML 생성"""
        stats = summary_data['stats']
        analysis = summary_data['analysis']
        
        html_content = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>로그 모니터링 요약 - {summary_data['timestamp']}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-box {{ background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; border-left: 4px solid #007bff; }}
        .stat-number {{ font-size: 2em; font-weight: bold; color: #007bff; }}
        .top-clusters {{ background: #fff; border: 1px solid #dee2e6; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .cluster-item {{ padding: 10px; margin: 5px 0; background: #f8f9fa; border-radius: 5px; }}
        .severity-critical {{ border-left: 4px solid #dc3545; }}
        .severity-high {{ border-left: 4px solid #fd7e14; }}
        .severity-medium {{ border-left: 4px solid #ffc107; }}
        .severity-low {{ border-left: 4px solid #28a745; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 로그 모니터링 요약</h1>
        <p>생성 시간: {summary_data['timestamp']}</p>
    </div>
    
    <div class="stats-grid">
        <div class="stat-box">
            <div class="stat-number">{stats.get('total_logs', 0):,}</div>
            <div>총 로그</div>
        </div>
        <div class="stat-box">
            <div class="stat-number">{stats.get('error_logs', 0):,}</div>
            <div>에러 로그</div>
        </div>
        <div class="stat-box">
            <div class="stat-number">{len(stats.get('top_clusters', []))}</div>
            <div>클러스터 수</div>
        </div>
        <div class="stat-box">
            <div class="stat-number">{analysis.get('error_rate', 0):.1f}%</div>
            <div>에러율</div>
        </div>
    </div>
    
    <div class="top-clusters">
        <h3>🏆 TOP 에러 패턴</h3>
        {self._format_clusters_html(stats.get('top_clusters', []))}
    </div>
    
    <div class="top-clusters">
        <h3>📈 분석 결과</h3>
        <p><strong>시스템 상태:</strong> {analysis.get('system_status', 'Unknown')}</p>
        <p><strong>권장사항:</strong> {analysis.get('recommendations', 'None')}</p>
    </div>
</body>
</html>
        """
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
    
    def _format_examples_html(self, examples: List) -> str:
        """예시를 HTML로 포맷팅"""
        if not examples:
            return "<p>예시 없음</p>"
        
        html_parts = []
        for i, example in enumerate(examples[:5], 1):  # 최대 5개
            if isinstance(example, dict):
                text = example.get('text', str(example))
                timestamp = example.get('timestamp', 'Unknown time')
            else:
                text = str(example)
                timestamp = 'Unknown time'
            
            html_parts.append(f"""
            <div class="log-example">
                <strong>예시 {i}:</strong><br>
                {text}<br>
                <small>수집 시간: {timestamp}</small>
            </div>
            """)
        
        return "".join(html_parts)
    
    def _format_recommendations_html(self, recommendations: List) -> str:
        """권장사항을 HTML로 포맷팅"""
        if not recommendations:
            return "<p>권장사항 없음</p>"
        
        items = "".join([f"<li>{rec}</li>" for rec in recommendations])
        return f"<ul>{items}</ul>"
    
    def _format_clusters_html(self, clusters: List) -> str:
        """클러스터를 HTML로 포맷팅"""
        if not clusters:
            return "<p>클러스터 없음</p>"
        
        html_parts = []
        for i, (cluster_id, template, count) in enumerate(clusters, 1):
            severity = self._get_severity(count)
            severity_class = f"severity-{severity}"
            
            html_parts.append(f"""
            <div class="cluster-item {severity_class}">
                <strong>{i}. 클러스터 {cluster_id}</strong> [{count}번]<br>
                <code>{template}</code>
            </div>
            """)
        
        return "".join(html_parts)
    
    def _get_severity(self, count: int) -> str:
        """발생 횟수에 따른 심각도 판단"""
        if count >= 50:
            return "critical"
        elif count >= 20:
            return "high"
        elif count >= 10:
            return "medium"
        else:
            return "low"
    
    def _get_recommendations(self, template: str) -> List[str]:
        """에러 패턴별 권장사항"""
        template_lower = template.lower()
        recommendations = []
        
        if 'nullpointer' in template_lower:
            recommendations.extend([
                "널체크 로직 추가 필요",
                "Optional 패턴 사용 검토", 
                "단위 테스트에서 널 케이스 추가"
            ])
        elif 'database' in template_lower or 'sql' in template_lower:
            recommendations.extend([
                "DB 커넥션 풀 설정 확인",
                "쿼리 성능 최적화",
                "DB 제약조건 검토"
            ])
        elif 'outofmemory' in template_lower:
            recommendations.extend([
                "JVM 힙 크기 조정",
                "메모리 프로파일링 실행",
                "GC 로그 분석"
            ])
        elif 'filenotfound' in template_lower:
            recommendations.extend([
                "파일 경로 확인",
                "파일 권한 점검",
                "설정 파일 존재 여부 확인"
            ])
        else:
            recommendations.append("상세한 로그 분석 필요")
        
        return recommendations
    
    def _analyze_summary(self, stats: Dict) -> Dict:
        """요약 통계 분석"""
        total_logs = stats.get('total_logs', 0)
        error_logs = stats.get('error_logs', 0)
        
        error_rate = (error_logs / total_logs * 100) if total_logs > 0 else 0
        
        if error_rate > 80:
            system_status = "🚨 위험 - 즉시 조치 필요"
            recommendations = "시스템 전반적인 점검이 필요합니다"
        elif error_rate > 50:
            system_status = "⚠️ 주의 - 모니터링 강화"
            recommendations = "주요 에러 패턴에 대한 빠른 대응이 필요합니다"
        elif error_rate > 25:
            system_status = "🟡 보통 - 지속 관찰"
            recommendations = "정기적인 모니터링을 유지하세요"
        else:
            system_status = "🟢 양호 - 정상 운영"
            recommendations = "현재 상태를 유지하세요"
        
        return {
            "error_rate": error_rate,
            "system_status": system_status,
            "recommendations": recommendations
        }
    
    def get_today_reports(self) -> Dict[str, List]:
        """오늘 생성된 리포트 목록 반환"""
        reports = {
            "error_alerts": list(self.error_alerts_dir.glob("*.json")),
            "summaries": list(self.summaries_dir.glob("*.json")),
            "raw_logs": list(self.raw_logs_dir.glob("*.txt"))
        }
        
        return reports
    
    def print_report_summary(self):
        """생성된 리포트 요약 출력"""
        reports = self.get_today_reports()
        
        print(f"\n📁 오늘 생성된 리포트 ({datetime.now().strftime('%Y-%m-%d')})")
        print(f"   📊 에러 알림: {len(reports['error_alerts'])}개")
        print(f"   📋 요약 리포트: {len(reports['summaries'])}개") 
        print(f"   📝 원본 로그: {len(reports['raw_logs'])}개")
        print(f"   📂 저장 위치: {self.today_dir}")