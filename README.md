1단계. RAG 미니 POC
목표: “내 문서에서 질문하면 근거랑 답을 돌려준다” 경험
실습
Confluence 페이지 1~2개 export → 텍스트 파일
LangChain DocumentLoader → TextSplitter → Embedding → VectorStore → RetrievalQA 구성
질문: “DB 커넥션 풀 오류 해결 방법?” → 출처+인용문 포함 답변
성과: “우리 내부 문서를 AI가 근거 기반으로 답해줄 수 있구나” 체감

2단계. 로그 클러스터링 맛보기
목표: 로그 중복 줄이고 패턴 잡기

실습
Drain3 라이브러리 사용 → NullPointerException… 같은 로그 10줄 넣어보기
클러스터링 결과 확인 (동일 패턴은 하나의 템플릿으로 묶임)
성과: “중복 에러 메시지를 자동으로 모아줄 수 있구나” 확인

3단계. Slack 연동 샘플
목표: Slack으로 결과 푸시하기
실습
Slack Webhook URL 만들어서 Python에서 requests.post로 메시지 보내보기
Block Kit 사용해서 버튼 달린 메시지 전송
성과: “AI 결과를 슬랙에 흘려보낼 수 있다” 체감

4단계. 모듈 연결 미니 플로우
위 3개를 합쳐서 작은 엔드투엔드 데모 만들기
로그 20줄 → Drain3로 클러스터링
에러 메시지를 RAG 질의로 넣어 → Jira/Confluence에서 근거 찾아오기
Slack에 결과 요약 + 근거 + “지라 생성” 버튼 보내기


🚦 그 다음(Week 2~3)
PostgreSQL + pgvector 붙여서 진짜 RAG 스토어 운영

Spring Boot API 게이트웨이 추가 (Slack/Jira 액션 프록시)

React 대시보드 연결
