import os
from dotenv import load_dotenv
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.chains import RetrievalQA
from langchain_community.llms import OpenAI
from langchain.schema import Document

# 환경 변수 로드
load_dotenv()

class TechDocRAG:
    def __init__(self, docs_directory=r"D:\devcon\docs", persist_directory=r"D:\devcon\rag_db"):
        self.docs_directory = docs_directory
        self.persist_directory = persist_directory
        self.vectorstore = None
        self.qa_chain = None
        
        # API 키 확인
        if not os.getenv("OPENAI_API_KEY"):
            print("⚠️  OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
            print("💡 대안으로 HuggingFace Embeddings를 사용하겠습니다.")
            self.use_openai = False
        else:
            self.use_openai = True
    
    def load_documents(self):
        """문서 로드"""
        print(f"📂 문서 로딩 시작: {self.docs_directory}")
        
        # DirectoryLoader로 마크다운 파일들 로드
        loader = DirectoryLoader(
            self.docs_directory,
            glob="*.md",
            loader_cls=TextLoader,
            loader_kwargs={'encoding': 'utf-8'}
        )
        
        documents = loader.load()
        print(f"✅ {len(documents)}개 문서 로드됨")
        
        # 문서 정보 출력
        for doc in documents:
            print(f"  - {os.path.basename(doc.metadata['source'])}: {len(doc.page_content)} 문자")
        
        return documents
    
    def split_documents(self, documents):
        """문서 분할"""
        print("\n📄 문서 분할 시작")
        
        # 텍스트 분할기 설정
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,        # 청크 크기
            chunk_overlap=200,      # 청크 겹침
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )
        
        # 문서들 분할
        splits = text_splitter.split_documents(documents)
        print(f"✅ {len(splits)}개 청크로 분할됨")
        
        # 청크 정보 출력
        for i, chunk in enumerate(splits[:3]):  # 처음 3개만 출력
            print(f"  청크 {i+1}: {len(chunk.page_content)} 문자")
            print(f"    미리보기: {chunk.page_content[:100]}...")
        
        return splits
    
    def create_embeddings_and_vectorstore(self, splits):
        """임베딩 생성 및 벡터스토어 구축"""
        print("\n🧠 임베딩 및 벡터스토어 생성")
        
        if self.use_openai:
            # OpenAI Embeddings 사용
            embeddings = OpenAIEmbeddings()
            print("✅ OpenAI Embeddings 사용")
        else:
            # HuggingFace Embeddings 사용 (무료 대안)
            from langchain_community.embeddings import HuggingFaceEmbeddings
            embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2"
            )
            print("✅ HuggingFace Embeddings 사용")
        
        # Chroma 벡터스토어 생성
        self.vectorstore = Chroma.from_documents(
            documents=splits,
            embedding=embeddings,
            persist_directory=self.persist_directory
        )
        
        # 벡터스토어 저장
        self.vectorstore.persist()
        print(f"✅ 벡터스토어 저장됨: {self.persist_directory}")
    
    def setup_qa_chain(self):
        """RetrievalQA 체인 설정"""
        print("\n🔗 QA 체인 설정")
        
        if self.use_openai:
            # OpenAI LLM 사용
            llm = OpenAI(temperature=0)
            print("✅ OpenAI LLM 사용")
        else:
            # HuggingFace LLM 사용 (무료 대안)
            from langchain_community.llms import HuggingFacePipeline
            from transformers import pipeline
            
            # 가벼운 모델 사용
            hf_pipeline = pipeline(
                "text-generation",
                model="microsoft/DialoGPT-small",
                max_length=512,
                temperature=0.1
            )
            llm = HuggingFacePipeline(pipeline=hf_pipeline)
            print("✅ HuggingFace LLM 사용")
        
        # RetrievalQA 체인 생성
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=self.vectorstore.as_retriever(
                search_kwargs={"k": 3}  # 상위 3개 관련 문서 검색
            ),
            return_source_documents=True
        )
        
        print("✅ RetrievalQA 체인 준비됨")
    
    def build_rag_system(self):
        """전체 RAG 시스템 구축"""
        print("🚀 RAG 시스템 구축 시작")
        print("=" * 50)
        
        # 1. 문서 로드
        documents = self.load_documents()
        
        # 2. 문서 분할  
        splits = self.split_documents(documents)
        
        # 3. 임베딩 & 벡터스토어
        self.create_embeddings_and_vectorstore(splits)
        
        # 4. QA 체인 설정
        self.setup_qa_chain()
        
        print("\n✅ RAG 시스템 구축 완료!")
        print("🎯 이제 query() 메서드로 질문할 수 있습니다.")
    
    def query(self, question):
        """질문하기"""
        if not self.qa_chain:
            print("❌ RAG 시스템이 초기화되지 않았습니다. build_rag_system()을 먼저 실행하세요.")
            return None
        
        print(f"\n❓ 질문: {question}")
        print("-" * 30)
        
        # 질문 실행
        result = self.qa_chain({"query": question})
        
        # 답변 출력
        print(f"💡 답변: {result['result']}")
        
        # 출처 문서 출력
        print(f"\n📚 출처 ({len(result['source_documents'])}개):")
        for i, doc in enumerate(result['source_documents']):
            source = os.path.basename(doc.metadata['source'])
            preview = doc.page_content[:150].replace('\n', ' ')
            print(f"  {i+1}. {source}")
            print(f"     \"{preview}...\"")
        
        return result

# 테스트 실행 함수
def test_rag_system():
    """RAG 시스템 테스트"""
    print("🧪 RAG 시스템 테스트 시작")
    
    # RAG 시스템 초기화
    rag = TechDocRAG()
    
    # 시스템 구축
    rag.build_rag_system()
    
    # 테스트 질문들
    test_questions = [
        "DB 커넥션 풀 오류 해결 방법?",
        "NullPointerException 방지하는 방법?", 
        "OutOfMemoryError가 발생하면 어떻게 해야 해?",
        "사용자 서비스에서 널 포인터 에러가 나는데?"
    ]
    
    print("\n" + "="*60)
    print("🎯 질문-답변 테스트")
    print("="*60)
    
    for question in test_questions:
        rag.query(question)
        print("\n" + "="*60)

if __name__ == "__main__":
    test_rag_system()