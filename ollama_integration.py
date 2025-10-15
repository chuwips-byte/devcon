"""
Ollama 연동 모듈
실시간 에러 발생시 llama3:8b-instruct-q4_K_M 모델을 사용하여 에러 분석 및 해결방법 제공
"""

import requests
import json
import time
from datetime import datetime
from typing import Optional, Dict, Any
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OllamaErrorAnalyzer:
    """Ollama를 사용한 에러 분석기"""

    def __init__(self, 
                 ollama_url: str = "http://localhost:11434",
                 # 모델변경(★★)
                 model_name: str = "",
                 timeout: int = 180):
        """
        Ollama 에러 분석기 초기화
        
        Args:
            ollama_url: Ollama 서버 URL
            model_name: 사용할 모델명
            timeout: 요청 타임아웃 (초)
        """
        self.ollama_url = ollama_url
        self.model_name = model_name
        self.timeout = timeout
        self.enabled = self._check_ollama_connection()
        
        if self.enabled:
            logger.info(f"✅ Ollama 연결 성공: {model_name}")
        else:
            logger.warning("❌ Ollama 연결 실패 - 에러 분석 기능 비활성화")
    
    def _check_ollama_connection(self) -> bool:
        """Ollama 서버 연결 확인"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [model['name'] for model in models]
                
                if self.model_name in model_names:
                    logger.info(f"✅ 모델 '{self.model_name}' 사용 가능")
                    return True
                else:
                    logger.warning(f"❌ 모델 '{self.model_name}'을 찾을 수 없습니다.")
                    logger.info(f"사용 가능한 모델: {model_names}")
                    return False
            else:
                logger.warning(f"Ollama 서버 응답 오류: {response.status_code}")
                return False
        except Exception as e:
            logger.warning(f"Ollama 연결 실패: {e}")
            return False
    
    def analyze_error(self, 
                     error_log: str, 
                     error_template: str, 
                     occurrence_count: int,
                     context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        에러 로그를 분석하여 원인과 해결방법 제공
        
        Args:
            error_log: 실제 에러 로그
            error_template: 클러스터링된 에러 템플릿
            occurrence_count: 발생 횟수
            context: 추가 컨텍스트 정보
            
        Returns:
            분석 결과 딕셔너리
        """
        if not self.enabled:
            return self._get_fallback_analysis(error_template)
        
        # 분석 시작 시간 로그
        start_time = datetime.now()
        logger.info(f"🤖 AI 에러 분석 시작: {error_template} (시작시간: {start_time.strftime('%H:%M:%S')})")
        
        try:
            # 프롬프트 생성
            prompt = self._create_analysis_prompt(error_log, error_template, occurrence_count, context)
            
            # Ollama API 호출
            analysis_result = self._call_ollama_api(prompt)
            
            # 결과 파싱 및 구조화
            structured_result = self._parse_analysis_result(analysis_result)
            
            # 분석 완료 시간 및 소요 시간 계산
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.info(f"✅ AI 에러 분석 완료: {error_template} (완료시간: {end_time.strftime('%H:%M:%S')}, 소요시간: {duration:.2f}초)")
            
            return structured_result
            
        except Exception as e:
            # 분석 실패 시간 및 소요 시간 계산
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            logger.error(f"❌ AI 에러 분석 실패: {error_template} (실패시간: {end_time.strftime('%H:%M:%S')}, 소요시간: {duration:.2f}초, 오류: {e})")
            return self._get_fallback_analysis(error_template)
    
    def _create_analysis_prompt(self, 
                              error_log: str, 
                              error_template: str, 
                              occurrence_count: int,
                              context: Optional[Dict[str, Any]] = None) -> str:
        """에러 분석을 위한 프롬프트 생성"""
        
        prompt = f"""당신은 경험 많은 소프트웨어 엔지니어입니다. 다음 에러 로그를 분석하여 원인과 해결방법을 제공해주세요.

**에러 정보:**
- 실제 에러 로그: {error_log}
- 에러 패턴: {error_template}
- 발생 횟수: {occurrence_count}회
- 분석 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**추가 컨텍스트:**
{self._format_context(context) if context else "추가 컨텍스트 없음"}

**분석 요청사항:**
다음 형식으로 JSON 형태로 답변해주세요:

{{
    "error_type": "에러 유형 (예: NullPointerException, DatabaseConnectionError 등)",
    "severity": "심각도 (Critical/High/Medium/Low)",
    "root_cause": "근본 원인 분석",
    "immediate_actions": [
        "즉시 조치사항 1",
        "즉시 조치사항 2"
    ],
    "long_term_solutions": [
        "장기적 해결방안 1",
        "장기적 해결방안 2"
    ],
    "prevention_tips": [
        "예방 방법 1",
        "예방 방법 2"
    ],
    "related_documentation": "관련 문서나 리소스",
    "confidence": "분석 신뢰도 (0-100)"
}}

**주의사항:**
- JSON 형식을 정확히 지켜주세요
- 실용적이고 구체적인 해결방법을 제시해주세요
- 한국어로 답변해주세요
- 발생 횟수가 높을수록 더 긴급한 조치가 필요함을 고려해주세요
"""
        
        return prompt
    
    def _format_context(self, context: Dict[str, Any]) -> str:
        """컨텍스트 정보 포맷팅"""
        formatted = []
        for key, value in context.items():
            formatted.append(f"- {key}: {value}")
        return "\n".join(formatted)
    
    def _call_ollama_api(self, prompt: str) -> str:
        """Ollama API 호출"""
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,  # 일관된 분석을 위해 낮은 temperature
                "top_p": 0.9,
                "max_tokens": 2000
            }
        }
        
        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('response', '')
            else:
                logger.error(f"Ollama API 오류: {response.status_code}")
                raise Exception(f"API 오류: {response.status_code}")
                
        except requests.exceptions.Timeout:
            logger.error("Ollama API 타임아웃")
            raise Exception("API 타임아웃")
        except Exception as e:
            logger.error(f"Ollama API 호출 실패: {e}")
            raise
    
    def _parse_analysis_result(self, raw_result: str) -> Dict[str, Any]:
        """Ollama 응답을 파싱하여 구조화된 결과 반환"""
        try:
            # JSON 부분만 추출
            json_start = raw_result.find('{')
            json_end = raw_result.rfind('}') + 1
            
            if json_start != -1 and json_end != -1:
                json_str = raw_result[json_start:json_end]
                parsed_result = json.loads(json_str)
                
                # 필수 필드 검증 및 기본값 설정
                return {
                    "error_type": parsed_result.get("error_type", "Unknown"),
                    "severity": parsed_result.get("severity", "Medium"),
                    "root_cause": parsed_result.get("root_cause", "분석 불가"),
                    "immediate_actions": parsed_result.get("immediate_actions", ["상세 분석 필요"]),
                    "long_term_solutions": parsed_result.get("long_term_solutions", ["시스템 점검 필요"]),
                    "prevention_tips": parsed_result.get("prevention_tips", ["모니터링 강화"]),
                    "related_documentation": parsed_result.get("related_documentation", "관련 문서 없음"),
                    "confidence": parsed_result.get("confidence", 50),
                    "analysis_timestamp": datetime.now().isoformat(),
                    "model_used": self.model_name
                }
            else:
                # JSON 파싱 실패시 텍스트 기반 파싱
                return self._parse_text_result(raw_result)
                
        except json.JSONDecodeError as e:
            logger.warning(f"JSON 파싱 실패, 텍스트 파싱 시도: {e}")
            return self._parse_text_result(raw_result)
        except Exception as e:
            logger.error(f"결과 파싱 오류: {e}")
            return self._get_fallback_analysis("Unknown")
    
    def _parse_text_result(self, text: str) -> Dict[str, Any]:
        """텍스트 기반 결과 파싱 (JSON 파싱 실패시)"""
        return {
            "error_type": "Text Analysis",
            "severity": "Medium",
            "root_cause": text[:200] + "..." if len(text) > 200 else text,
            "immediate_actions": ["상세 로그 분석 필요", "시스템 상태 점검"],
            "long_term_solutions": ["코드 리뷰 강화", "모니터링 시스템 개선"],
            "prevention_tips": ["정기적인 시스템 점검", "에러 핸들링 개선"],
            "related_documentation": "시스템 문서 참조",
            "confidence": 30,
            "analysis_timestamp": datetime.now().isoformat(),
            "model_used": self.model_name,
            "raw_response": text
        }
    
    def _get_fallback_analysis(self, error_template: str) -> Dict[str, Any]:
        """Ollama 연결 실패시 기본 분석 결과"""
        template_lower = error_template.lower()
        
        # 기본 패턴 기반 분석
        if 'nullpointer' in template_lower:
            return {
                "error_type": "NullPointerException",
                "severity": "High",
                "root_cause": "객체 참조가 null인 상태에서 메서드 호출",
                "immediate_actions": [
                    "해당 코드 라인 확인",
                    "null 체크 로직 추가"
                ],
                "long_term_solutions": [
                    "Optional 패턴 도입",
                    "코드 리뷰에서 null 체크 강화"
                ],
                "prevention_tips": [
                    "단위 테스트에서 null 케이스 추가",
                    "정적 분석 도구 사용"
                ],
                "related_documentation": "Java NullPointerException 가이드",
                "confidence": 80,
                "analysis_timestamp": datetime.now().isoformat(),
                "model_used": "fallback_analysis"
            }
        elif 'database' in template_lower or 'connection' in template_lower:
            return {
                "error_type": "DatabaseConnectionError",
                "severity": "Critical",
                "root_cause": "데이터베이스 연결 실패 또는 타임아웃",
                "immediate_actions": [
                    "DB 서버 상태 확인",
                    "커넥션 풀 설정 점검"
                ],
                "long_term_solutions": [
                    "커넥션 풀 최적화",
                    "DB 모니터링 시스템 구축"
                ],
                "prevention_tips": [
                    "정기적인 DB 상태 점검",
                    "커넥션 풀 모니터링"
                ],
                "related_documentation": "데이터베이스 연결 관리 가이드",
                "confidence": 85,
                "analysis_timestamp": datetime.now().isoformat(),
                "model_used": "fallback_analysis"
            }
        else:
            return {
                "error_type": "Unknown Error",
                "severity": "Medium",
                "root_cause": "에러 패턴 분석 필요",
                "immediate_actions": [
                    "상세 로그 분석",
                    "시스템 상태 점검"
                ],
                "long_term_solutions": [
                    "에러 모니터링 시스템 강화",
                    "코드 리뷰 프로세스 개선"
                ],
                "prevention_tips": [
                    "정기적인 시스템 점검",
                    "에러 핸들링 개선"
                ],
                "related_documentation": "시스템 문서 참조",
                "confidence": 50,
                "analysis_timestamp": datetime.now().isoformat(),
                "model_used": "fallback_analysis"
            }
    
    def test_connection(self) -> bool:
        """연결 테스트"""
        if not self.enabled:
            return False
        
        try:
            test_prompt = "안녕하세요. 간단한 테스트입니다."
            result = self._call_ollama_api(test_prompt)
            logger.info("✅ Ollama 연결 테스트 성공")
            return True
        except Exception as e:
            logger.error(f"❌ Ollama 연결 테스트 실패: {e}")
            return False

def test_ollama_integration():
    """Ollama 연동 테스트 함수"""
    print("🤖 Ollama 연동 테스트 시작")
    print("=" * 50)
    
    # Ollama 분석기 생성
    analyzer = OllamaErrorAnalyzer()
    
    if analyzer.enabled:
        print("✅ Ollama 연결 성공")
        
        # 연결 테스트
        print("\n1. 연결 테스트 실행 중...")
        if analyzer.test_connection():
            print("✅ 연결 테스트 성공")
            
            # 샘플 에러 분석
            print("\n2. 샘플 에러 분석 실행 중...")
            sample_error = "ERROR NullPointerException at UserService.findById(123)"
            sample_template = "ERROR NullPointerException at UserService.findById(<*>)"
            
            result = analyzer.analyze_error(
                error_log=sample_error,
                error_template=sample_template,
                occurrence_count=5
            )
            
            print("\n📊 분석 결과:")
            print(f"에러 유형: {result['error_type']}")
            print(f"심각도: {result['severity']}")
            print(f"근본 원인: {result['root_cause']}")
            print(f"즉시 조치사항: {result['immediate_actions']}")
            print(f"신뢰도: {result['confidence']}%")
            
        else:
            print("❌ 연결 테스트 실패")
    else:
        print("❌ Ollama 연결 실패")
        print("💡 Ollama 서버가 실행 중인지 확인하세요")
        print("💡 llama3:8b-instruct-q4_K_M 모델이 설치되어 있는지 확인하세요")

if __name__ == "__main__":
    test_ollama_integration()