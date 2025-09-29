"""
파일명: stack_trace_processor.py
목적: 범용 스택트레이스 처리 및 클러스터링
사용법: from stack_trace_processor import EnhancedStackTraceProcessor
"""

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

class EnhancedStackTraceProcessor:
    def __init__(self):
        self.pending_stack = []
        self.stack_timeout = timedelta(seconds=3)
        self.last_stack_time = None
        self.error_examples = {}  # 클러스터별 원본 예시 보관
        
    def process_line(self, line: str, timestamp: Optional[datetime] = None) -> Optional[Dict]:
        """라인을 처리하고 완료된 스택트레이스 반환"""
        if timestamp is None:
            timestamp = datetime.now()
        
        line_type = self.classify_line(line)
        
        if line_type == "EXCEPTION_START":
            # 이전 스택 완료 처리
            result = self.finalize_current_stack()
            # 새 스택 시작
            self.start_new_stack(line, timestamp)
            return result
            
        elif line_type == "STACK_CONTINUATION":
            self.add_to_current_stack(line, timestamp)
            return None
            
        elif line_type == "NORMAL_LOG":
            # 일반 로그면 스택 종료
            result = self.finalize_current_stack()
            if result:
                return result
            # 일반 로그는 기존 방식으로 처리하도록 문자열 반환
            return {"summary": line, "original": line, "is_single_line": True}
            
        # 타임아웃 체크
        if self.is_stack_timeout(timestamp):
            return self.finalize_current_stack()
            
        return None
    
    def classify_line(self, line: str) -> str:
        """라인 타입 분류"""
        line = line.strip()
        
        # 예외 시작 패턴들
        exception_starts = [
            r'\w+Exception:',
            r'\w+Error:',
            r'### Error',
            r'org\.springframework\.',
            r'^\w+\.\w+\.\w+Exception',
            r'Caused by:',
            r'java\.lang\.\w+Exception',
        ]
        
        for pattern in exception_starts:
            if re.search(pattern, line):
                return "EXCEPTION_START"
        
        # 스택 연속 패턴들
        stack_continuations = [
            r'^\s*at\s+',
            r'^\s*\.\.\.\s*\d+\s+more',
            r'^\s*Suppressed:',
            r'^\s*###',
            r'^\s*\[',
            r'^\s*\t',
            r'^\s{4,}',
        ]
        
        for pattern in stack_continuations:
            if re.search(pattern, line):
                return "STACK_CONTINUATION"
        
        return "NORMAL_LOG"
    
    def start_new_stack(self, line: str, timestamp: datetime):
        """새 스택트레이스 시작"""
        self.pending_stack = [line]
        self.last_stack_time = timestamp
    
    def add_to_current_stack(self, line: str, timestamp: datetime):
        """현재 스택에 라인 추가"""
        if self.pending_stack:
            self.pending_stack.append(line)
            self.last_stack_time = timestamp
    
    def finalize_current_stack(self) -> Optional[Dict]:
        """현재 스택을 완료하고 요약 반환"""
        if not self.pending_stack:
            return None
        
        # 요약 생성 (클러스터링용)
        summary = self.create_stack_summary(self.pending_stack)
        
        # 원본 보관 (사용자 확인용)
        original_text = '\n'.join(self.pending_stack)
        
        result = {
            'summary': summary,
            'original': original_text,
            'timestamp': datetime.now(),
            'line_count': len(self.pending_stack),
            'is_single_line': False
        }
        
        self.pending_stack = []
        self.last_stack_time = None
        
        return result
    
    def is_stack_timeout(self, current_time: datetime) -> bool:
        """스택 타임아웃 체크"""
        if not self.last_stack_time:
            return False
        return current_time - self.last_stack_time > self.stack_timeout
    
    def create_stack_summary(self, stack_lines: List[str]) -> str:
        """스택트레이스를 요약된 형태로 변환"""
        if not stack_lines:
            return ""
        
        # 1. 루트 예외 추출
        root_exception = self.extract_root_exception(stack_lines[0])
        
        # 2. 핵심 스택 위치 추출
        key_location = self.extract_key_location(stack_lines)
        
        # 3. 요약 생성
        summary = f"{root_exception} at {key_location}"
        
        return summary
    
    def extract_root_exception(self, first_line: str) -> str:
        """첫 번째 라인에서 예외 타입과 메시지 추출"""
        
        # Exception: message 패턴
        exception_match = re.search(r'(\w*Exception|\w*Error):\s*(.+)', first_line)
        if exception_match:
            exc_type = exception_match.group(1)
            message = exception_match.group(2)
            # 메시지가 너무 길면 자르기
            if len(message) > 50:
                message = message[:50] + "..."
            return f"{exc_type}: {message}"
        
        # ### Error 패턴 (MyBatis 등)
        if '### Error' in first_line:
            if 'database' in first_line.lower():
                return "DatabaseError: " + self.extract_db_operation(first_line)
            return "FrameworkError: " + first_line.split('###')[-1].strip()[:50]
        
        # 일반적인 경우 - 첫 50자
        return first_line.strip()[:50] + ("..." if len(first_line) > 50 else "")
    
    def extract_key_location(self, stack_lines: List[str]) -> str:
        """스택에서 가장 중요한 위치 추출"""
        
        # 우선순위: 프로젝트 코드 > 컨트롤러/서비스 > 첫 번째 스택
        priorities = [
            r'at\s+com\.(?!sun|oracle|microsoft)',  # 프로젝트 패키지
            r'at\s+\w+\..*[Cc]ontroller\.',         # 컨트롤러
            r'at\s+\w+\..*[Ss]ervice\.',            # 서비스
            r'at\s+\w+\..*[Mm]apper\.',             # 매퍼
            r'at\s+',                               # 기타 모든 스택
        ]
        
        for priority_pattern in priorities:
            for line in stack_lines[1:]:  # 첫 번째 라인(예외) 제외
                if re.search(priority_pattern, line):
                    return self.clean_stack_location(line)
        
        return "unknown"
    
    def clean_stack_location(self, stack_line: str) -> str:
        """스택 라인에서 깔끔한 위치 정보 추출"""
        match = re.search(r'at\s+([\w.]+)\((.*?):(\d+)\)', stack_line)
        if match:
            full_method = match.group(1)
            class_method = '.'.join(full_method.split('.')[-2:])  # 마지막 2개 요소
            return class_method
        
        # 파싱 실패시 원본에서 간단히 추출
        if 'at ' in stack_line:
            location = stack_line.replace('at ', '').strip()
            return location.split('(')[0].split('.')[-1]  # 메서드명만
        
        return stack_line.strip()[:30]
    
    def extract_db_operation(self, line: str) -> str:
        """DB 관련 에러에서 오퍼레이션 추출"""
        operations = ['updating', 'querying', 'inserting', 'deleting']
        for op in operations:
            if op in line.lower():
                return op + " database"
        return "database operation"
    
    def store_original_example(self, cluster_id: int, original_text: str):
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
    
    def get_examples_for_cluster(self, cluster_id: int) -> List[Dict]:
        """특정 클러스터의 예시들 반환"""
        return self.error_examples.get(cluster_id, [])