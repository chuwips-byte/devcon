"""
RAG 통합 Ollama 연동 모듈 (수정된 버전)
학습된 Jira 이슈 데이터를 활용하여 에러 분석 수행
"""

import requests
import json
import time
import os
import glob
from datetime import datetime
from typing import Optional, Dict, Any, List
import logging

# RAG 모듈 import
try:
    from rag_trainer import RAGTrainer
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    print("⚠️ RAG Trainer를 사용할 수 없습니다.")

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RagIntegratedOllamaAnalyzer:
    """RAG 통합 Ollama 에러 분석기"""

    def __init__(self,
                 ollama_url: str = "http://localhost:11434",
                 # 모델변경(★★)
                 model_name: str = "llama3:8b-instruct-q4_K_M",
                 timeout: int = 180,
                 rag_models_dir: str = "models"):
        """
        RAG 통합 Ollama 분석기 초기화

        Args:
            ollama_url: Ollama 서버 URL
            model_name: 사용할 모델명
            timeout: 요청 타임아웃 (초)
            rag_models_dir: RAG 모델 저장 디렉토리
        """
        self.ollama_url = ollama_url
        self.model_name = model_name
        self.timeout = timeout
        self.rag_models_dir = rag_models_dir

        # Ollama 연결 확인
        self.enabled = self._check_ollama_connection()

        # RAG 모델 로드
        self.rag_trainer = None
        self.rag_available = False
        if RAG_AVAILABLE:
            self._load_latest_rag_model()

        if self.enabled:
            logger.info(f"✅ Ollama 연결 성공: {model_name}")
            if self.rag_available:
                logger.info("✅ RAG 모델 로드 성공 - 학습된 이슈 데이터 활용 가능")
            else:
                logger.info("⚠️ RAG 모델 없음 - 일반 분석만 가능")
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

    def _load_latest_rag_model(self):
        """가장 최근의 RAG 모델 로드"""
        try:
            if not os.path.exists(self.rag_models_dir):
                logger.info("RAG 모델 디렉토리가 없습니다.")
                return

            # bug_rag_model_* 패턴의 디렉토리 찾기
            model_patterns = [
                os.path.join(self.rag_models_dir, "bug_rag_model_*"),
                os.path.join(self.rag_models_dir, "*rag*"),
            ]

            model_dirs = []
            for pattern in model_patterns:
                model_dirs.extend(glob.glob(pattern))

            if not model_dirs:
                logger.info("RAG 모델을 찾을 수 없습니다.")
                return

            # 가장 최근 모델 선택 (파일명 기준)
            latest_model = max(model_dirs, key=lambda x: os.path.getctime(x))

            logger.info(f"RAG 모델 로드 시도: {latest_model}")

            # RAG Trainer 초기화 및 모델 로드
            self.rag_trainer = RAGTrainer()
            self.rag_trainer.load_model(latest_model)

            stats = self.rag_trainer.get_stats()
            self.rag_available = stats['status'] == 'ready'

            if self.rag_available:
                logger.info(f"✅ RAG 모델 로드 성공: {stats['num_documents']}개 문서")
            else:
                logger.warning("❌ RAG 모델 로드 실패")

        except Exception as e:
            logger.warning(f"RAG 모델 로드 실패: {e}")
            self.rag_available = False

    def analyze_error(self,
                      error_log: str,
                      error_template: str,
                      occurrence_count: int,
                      context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        에러 로그를 분석하여 원인과 해결방법 제공 (RAG 통합)

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
            # 1. RAG 검색으로 유사한 이슈 찾기
            similar_issues = []
            if self.rag_available:
                similar_issues = self._search_similar_issues(error_log, error_template)

            # 2. 프롬프트 생성 (RAG 결과 포함)
            prompt = self._create_rag_enhanced_prompt(
                error_log, error_template, occurrence_count, context, similar_issues
            )

            # 3. Ollama API 호출
            analysis_result = self._call_ollama_api(prompt)

            # 4. 결과 파싱 및 구조화
            structured_result = self._parse_analysis_result(analysis_result)

            # 5. RAG 검색 결과 추가
            if similar_issues:
                structured_result['similar_issues'] = similar_issues
                structured_result['rag_enhanced'] = True
            else:
                structured_result['rag_enhanced'] = False

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

    def _search_similar_issues(self, error_log: str, error_template: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """RAG를 사용하여 유사한 이슈 검색 (디버깅 강화)"""
        if not self.rag_available:
            return []

        try:
            # 검색 쿼리 생성 (에러 로그와 템플릿 조합)
            query = f"{error_template} {error_log}"

            # 🔍 디버깅: 검색 쿼리 출력
            logger.info(f"🔍 RAG 검색 쿼리: {query[:100]}...")

            # 유사도 검색
            results = self.rag_trainer.search(query, top_k=top_k)

            similar_issues = []
            for result in results:
                doc = result['document']

                # 🔍 디버깅: 각 검색 결과 출력
                logger.info(f"📄 검색 결과 {result['rank']}: ID={doc.get('id', 'Unknown')}, 유사도={result['similarity']:.3f}")
                logger.info(f"📝 내용 미리보기: {doc.get('text', '')[:150]}...")

                similar_issues.append({
                    'issue_id': doc.get('id', 'Unknown'),
                    'similarity': result['similarity'],
                    'text': doc.get('text', ''),
                    'metadata': doc.get('metadata', {}),
                    'rank': result['rank']
                })

            logger.info(f"🔍 RAG 검색 완료: {len(similar_issues)}개 유사 이슈 발견")

            # 🔍 디버깅: 최고 유사도 확인
            if similar_issues:
                max_similarity = max(issue['similarity'] for issue in similar_issues)
                logger.info(f"📊 최고 유사도: {max_similarity:.3f}")

            return similar_issues

        except Exception as e:
            logger.error(f"RAG 검색 실패: {e}")
            return []

    def _create_rag_enhanced_prompt(self,
                                    error_log: str,
                                    error_template: str,
                                    occurrence_count: int,
                                    context: Optional[Dict[str, Any]] = None,
                                    similar_issues: List[Dict[str, Any]] = None) -> str:
        """RAG 검색 결과를 포함한 향상된 프롬프트 생성 (디버깅 강화)"""

        prompt = f"""당신은 경험 많은 소프트웨어 엔지니어입니다. 다음 에러 로그를 분석하여 원인과 해결방법을 제공해주세요.
    
    **에러 정보:**
    - 실제 에러 로그: {error_log}
    - 에러 패턴: {error_template}
    - 발생 횟수: {occurrence_count}회
    - 분석 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    
    **추가 컨텍스트:**
    {self._format_context(context) if context else "추가 컨텍스트 없음"}
    """

        # RAG 검색 결과 추가
        if similar_issues:
            logger.info(f"📝 프롬프트에 {len(similar_issues)}개 유사 사례 추가 중...")

            prompt += f"""
    
    **🔍 유사한 과거 이슈 사례 (중요 - 이 사례들을 적극 참고하세요!):**
    다음은 시스템에서 찾은 유사한 이슈들입니다. 이 사례들의 해결방법을 우선적으로 참고하여 분석해주세요.
    
    """
            for i, issue in enumerate(similar_issues, 1):
                # 🔍 디버깅: 각 사례를 프롬프트에 추가할 때 로그 출력
                logger.info(f"📄 사례 {i} 프롬프트 추가: {issue['issue_id']} (유사도: {issue['similarity']:.3f})")

                prompt += f"""
    사례 {i} (유사도: {issue['similarity']:.2f}, 이슈 ID: {issue['issue_id']}):
    내용: {issue['text'][:500]}
    메타데이터: {issue.get('metadata', {})}
    
    """
        else:
            logger.warning("⚠️ 유사 사례가 없어서 일반 분석만 수행")

        prompt += f"""
    
    **분석 요청사항:**
    {"위의 유사 사례들을 적극 참고하여" if similar_issues else ""} 다음 형식으로 JSON 형태로 답변해주세요:
    
    {{
        "error_type": "에러 유형",
        "severity": "심각도 (Critical/High/Medium/Low)",
        "root_cause": "근본 원인 분석{' (유사 사례 참고)' if similar_issues else ''}",
        "immediate_actions": [
            "즉시 조치사항 1{' (과거 사례 기반)' if similar_issues else ''}",
            "즉시 조치사항 2"
        ],
        "long_term_solutions": [
            "장기적 해결방안 1{' (과거 사례에서 학습)' if similar_issues else ''}",
            "장기적 해결방안 2"
        ],
        "prevention_tips": [
            "예방 방법 1",
            "예방 방법 2"
        ],
        "related_documentation": "관련 문서나 리소스",
        "confidence": "분석 신뢰도 (0-100{', 유사 사례가 있으면 높게' if similar_issues else ''})",
        "past_cases_referenced": "{len(similar_issues) if similar_issues else 0}",
        "similar_case_details": "{', '.join([issue['issue_id'] for issue in similar_issues]) if similar_issues else 'None'}"
    }}
    
    **중요 지침:**
    - JSON 형식을 정확히 지켜주세요
    - 한국어로 답변해주세요
    {"- 위에 제공된 유사 사례들의 해결방법을 우선적으로 참고하세요" if similar_issues else ""}
    - 실용적이고 구체적인 해결방법을 제시해주세요
    - 발생 횟수({occurrence_count}회)를 고려하여 긴급도를 판단하세요
    """

        # 🔍 디버깅: 최종 프롬프트 길이 출력
        logger.info(f"📝 최종 프롬프트 생성 완료: {len(prompt)}자, 유사사례 {len(similar_issues) if similar_issues else 0}개 포함")

        # 🔍 디버깅: 프롬프트 일부 출력 (너무 길면 일부만)
        if len(prompt) > 1000:
            logger.info(f"📝 프롬프트 미리보기: {prompt[:300]}... [중간 생략] ...{prompt[-200:]}")
        else:
            logger.info(f"📝 전체 프롬프트: {prompt}")

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
                    "past_cases_referenced": parsed_result.get("past_cases_referenced", 0),
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
            "past_cases_referenced": 0,
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
                "past_cases_referenced": 0,
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
                "past_cases_referenced": 0,
                "analysis_timestamp": datetime.now().isoformat(),
                "model_used": "fallback_analysis"
            }

    def reload_rag_model(self):
        """RAG 모델 다시 로드 (새로운 학습 후 호출)"""
        logger.info("RAG 모델 다시 로드 중...")
        self._load_latest_rag_model()

    def get_rag_stats(self) -> Dict[str, Any]:
        """RAG 상태 정보 반환"""
        if self.rag_available and self.rag_trainer:
            stats = self.rag_trainer.get_stats()
            stats['rag_available'] = True
            return stats
        else:
            return {
                'rag_available': False,
                'status': 'not_loaded',
                'num_documents': 0
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

def test_rag_integrated_ollama():
    """RAG 통합 Ollama 테스트"""
    print("🤖 RAG 통합 Ollama 테스트 시작")
    print("=" * 50)

    # 분석기 생성
    analyzer = RagIntegratedOllamaAnalyzer()

    if analyzer.enabled:
        print("✅ Ollama 연결 성공")

        # RAG 상태 확인
        rag_stats = analyzer.get_rag_stats()
        if rag_stats['rag_available']:
            print(f"✅ RAG 사용 가능: {rag_stats['num_documents']}개 문서 로드됨")
        else:
            print("⚠️ RAG 사용 불가 - 일반 분석만 수행")

        # 테스트 에러 분석
        sample_error = "ERROR: 비가 많이오는데 창문을 열어놨어 (랜덤번호: 9)"
        sample_template = "ERROR: 비가 많이오는데 창문을 열어놨어 (랜덤번호: <*>)"

        result = analyzer.analyze_error(
            error_log=sample_error,
            error_template=sample_template,
            occurrence_count=3
        )

        print("\n📊 분석 결과:")
        print(f"에러 유형: {result['error_type']}")
        print(f"심각도: {result['severity']}")
        print(f"근본 원인: {result['root_cause']}")
        print(f"즉시 조치사항: {result['immediate_actions']}")
        print(f"신뢰도: {result['confidence']}%")
        print(f"과거 사례 참조: {result.get('past_cases_referenced', 0)}개")
        print(f"RAG 강화: {result.get('rag_enhanced', False)}")

        if result.get('similar_issues'):
            print(f"\n🔍 유사 사례:")
            for issue in result['similar_issues']:
                print(f"  - {issue['issue_id']} (유사도: {issue['similarity']:.2f})")

    else:
        print("❌ Ollama 연결 실패")

if __name__ == "__main__":
    test_rag_integrated_ollama()