"""
파일명: 1_basic_drain3_test.py
목적: Drain3 기본 개념 학습 및 테스트 (최신 버전 호환)
사용법: python 1_basic_drain3_test.py
"""

from drain3 import TemplateMiner

def explain_drain3_concepts():
    """Drain3 핵심 개념 설명"""
    print("🎓 Drain3 핵심 개념 설명")
    print("=" * 50)
    
    print("\n1️⃣ 클러스터링이란?")
    print("   🎯 목적: 비슷한 로그들을 자동으로 묶어주는 것")
    print("   📝 예시:")
    print("      입력 → 'User 123 login failed'")
    print("      입력 → 'User 456 login failed'") 
    print("      입력 → 'User 789 login failed'")
    print("      결과 → 'User <*> login failed' (하나의 패턴으로 묶임)")
    
    print("\n2️⃣ 템플릿이란?")
    print("   🎯 목적: 로그 패턴을 일반화한 것")
    print("   📝 구성:")
    print("      - 고정 부분: 항상 같은 단어들 ('ERROR', 'at', 'line' 등)")
    print("      - 변수 부분: 바뀌는 부분 (<*>로 표시)")
    print("   💡 예시: 'ERROR at line <*> in file <*>'")
    
    print("\n3️⃣ 유사도 임계값이란?")
    print("   🎯 목적: 얼마나 비슷해야 같은 클러스터로 볼지 결정")
    print("   📊 설정값: 0.4 (40%)")
    print("   💭 의미: 두 로그가 40% 이상 비슷하면 같은 패턴으로 분류")

def basic_drain3_test():
    """Drain3 기본 사용법 테스트 (최신 버전 호환)"""
    print("\n🧪 Drain3 기본 테스트 시작")
    print("=" * 50)
    
    # 가장 간단한 방법으로 시작
    try:
        template_miner = TemplateMiner()
        print("✅ TemplateMiner 생성 성공")
        
    except Exception as e:
        print(f"❌ TemplateMiner 생성 실패: {e}")
        return
    
    # 테스트용 로그 데이터
    test_logs = [
        # 같은 패턴 1: NullPointerException (숫자만 다름)
        "ERROR NullPointerException at UserService.findById(123)",
        "ERROR NullPointerException at UserService.findById(456)", 
        "ERROR NullPointerException at UserService.findById(789)",
        
        # 같은 패턴 2: Database connection (시간만 다름)
        "ERROR Database connection failed - timeout after 30s",
        "ERROR Database connection failed - timeout after 45s",
        
        # 같은 패턴 3: FileNotFoundException (파일명만 다름)
        "ERROR FileNotFoundException: config/app.properties not found",
        "ERROR FileNotFoundException: config/db.properties not found",
        
        # 다른 패턴: SQL Exception
        "ERROR SQL Exception: Duplicate entry 'user123' for key 'username'"
    ]
    
    print("\n📚 로그 학습 과정:")
    
    # 각 로그를 Drain3에 학습시키기
    for i, log in enumerate(test_logs, 1):
        try:
            result = template_miner.add_log_message(log)
            
            print(f"\n{i:2d}번째 로그:")
            print(f"   입력: {log}")
            
            # 반환값 타입 확인 및 처리
            if isinstance(result, dict):
                # dict 형태인 경우
                cluster_id = result.get('cluster_id', 'unknown')
                template = result.get('template_mined', 'unknown')
                print(f"   클러스터: {cluster_id}")
                print(f"   템플릿: {template}")
                
                # 클러스터 정보 조회 (새로운 방식)
                try:
                    # drain 객체에서 직접 클러스터 조회
                    if hasattr(template_miner, 'drain') and hasattr(template_miner.drain, 'clusters'):
                        clusters = template_miner.drain.clusters
                        if isinstance(clusters, dict) and cluster_id in clusters:
                            cluster = clusters[cluster_id]
                            print(f"   발생횟수: {cluster.size}번")
                        elif hasattr(clusters, '__len__'):
                            print(f"   전체 클러스터 수: {len(clusters)}개")
                except Exception as e:
                    print(f"   클러스터 정보 조회 실패: {e}")
                    
            else:
                # 기존 객체 형태인 경우
                print(f"   클러스터: {getattr(result, 'cluster_id', 'unknown')}")
                print(f"   템플릿: {getattr(result, 'template', 'unknown')}")
            
            # 디버깅 정보
            print(f"   💡 result 타입: {type(result)}")
            if isinstance(result, dict):
                print(f"   💡 result 키들: {list(result.keys())}")
                
        except Exception as e:
            print(f"   ❌ 로그 처리 실패: {e}")
            print(f"   💡 result 타입: {type(result) if 'result' in locals() else 'undefined'}")
    
    # 최종 결과 요약 (수정된 방식)
    print("\n📊 최종 클러스터링 결과:")
    print("-" * 30)
    
    try:
        # 여러 방법으로 클러스터 정보 접근 시도
        clusters = None
        
        # 방법 1: drain.clusters 직접 접근
        if hasattr(template_miner, 'drain') and hasattr(template_miner.drain, 'clusters'):
            clusters = template_miner.drain.clusters
            print(f"✅ 클러스터 접근 성공 (방법 1)")
        
        # 방법 2: 다른 속성 시도
        elif hasattr(template_miner, 'clusters'):
            clusters = template_miner.clusters
            print(f"✅ 클러스터 접근 성공 (방법 2)")
        
        if clusters is not None:
            if isinstance(clusters, dict):
                print(f"총 {len(clusters)}개의 서로 다른 에러 패턴 발견:")
                
                for cluster_id, cluster in clusters.items():
                    try:
                        if hasattr(cluster, 'log_template_tokens'):
                            template_str = ' '.join(cluster.log_template_tokens)
                        elif hasattr(cluster, 'get_template'):
                            template_str = cluster.get_template()
                        else:
                            template_str = str(cluster)
                            
                        size = getattr(cluster, 'size', 'unknown')
                        print(f"클러스터 {cluster_id}: {template_str} ({size}번)")
                        
                        # 패턴 분석
                        if 'NullPointer' in template_str:
                            print(f"   🎯 분석: NPE 패턴 - 널체크 코드 필요")
                        elif 'Database' in template_str:
                            print(f"   🎯 분석: DB 연결 문제 - 커넥션 풀 확인 필요")
                        elif 'FileNotFound' in template_str:
                            print(f"   🎯 분석: 파일 문제 - 경로 및 권한 확인 필요")
                            
                    except Exception as e:
                        print(f"클러스터 {cluster_id}: 정보 추출 실패 ({e})")
            else:
                print(f"클러스터 타입: {type(clusters)}")
                print(f"클러스터 개수: {len(clusters) if hasattr(clusters, '__len__') else 'unknown'}")
        else:
            print("❌ 클러스터 정보에 접근할 수 없습니다")
            
            # 디버깅 정보
            print(f"💡 template_miner 속성들: {dir(template_miner)}")
            if hasattr(template_miner, 'drain'):
                print(f"💡 drain 속성들: {dir(template_miner.drain)}")
                
    except Exception as e:
        print(f"❌ 결과 출력 실패: {e}")

def debug_drain3_version():
    """Drain3 버전 및 구조 확인"""
    print("\n🔍 Drain3 디버깅 정보")
    print("=" * 30)
    
    try:
        import drain3
        print(f"Drain3 버전: {getattr(drain3, '__version__', 'unknown')}")
        
        template_miner = TemplateMiner()
        
        # 테스트 로그 하나만 넣어보기
        test_log = "ERROR test message 123"
        result = template_miner.add_log_message(test_log)
        
        print(f"add_log_message 반환 타입: {type(result)}")
        print(f"반환값 내용: {result}")
        
        if isinstance(result, dict):
            print(f"Dict 키들: {list(result.keys())}")
            for key, value in result.items():
                print(f"  {key}: {value} (타입: {type(value)})")
        
        # template_miner 구조 확인
        print(f"\nTemplateMiner 속성들:")
        for attr in dir(template_miner):
            if not attr.startswith('_'):
                print(f"  {attr}")
        
        # drain 객체 확인
        if hasattr(template_miner, 'drain'):
            print(f"\nDrain 객체 속성들:")
            for attr in dir(template_miner.drain):
                if not attr.startswith('_'):
                    print(f"  {attr}")
                    
    except Exception as e:
        print(f"❌ 디버깅 실패: {e}")

if __name__ == "__main__":
    print("🎓 Drain3 기본 학습 프로그램 (최신 버전 호환)")
    
    print("\n선택하세요:")
    print("1. 개념 설명")
    print("2. 기본 테스트")
    print("3. 디버깅 정보")
    
    try:
        choice = input("선택 (1-3): ").strip()
        
        if choice == "1":
            explain_drain3_concepts()
        elif choice == "2":
            explain_drain3_concepts()
            basic_drain3_test()
        elif choice == "3":
            debug_drain3_version()
        else:
            print("전체 실행:")
            explain_drain3_concepts()
            basic_drain3_test()
            debug_drain3_version()
            
    except KeyboardInterrupt:
        print("\n👋 프로그램 종료")
    
    print("\n✅ 실행 완료!")
    print("💡 다음: 2_clustering_monitor.py로 실시간 모니터링 해보세요")