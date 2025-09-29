import os

# 샘플 기술문서들 생성
DOCS_DIR = r"D:\devcon\docs"
os.makedirs(DOCS_DIR, exist_ok=True)

# DB 관련 문서
db_troubleshooting = """
# DB 커넥션 풀 오류 해결 가이드

## 문제 증상
- Database connection failed
- Connection timeout after 30s  
- Connection pool exhausted
- Too many connections

## 해결 방법

### 1. 커넥션 풀 설정 확인
```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000
      idle-timeout: 600000
```

### 2. 커넥션 누수 확인
- finally 블록에서 connection.close() 확인
- try-with-resources 패턴 사용 권장

### 3. DB 서버 상태 확인
```sql
SHOW PROCESSLIST;
SHOW STATUS LIKE 'Threads_connected';
```

### 4. 모니터링 설정
- HikariCP 메트릭 활성화
- 커넥션 풀 상태 주기적 체크

## 관련 이슈
- JIRA-1234: DB 커넥션 풀 설정 개선
- JIRA-5678: 커넥션 누수 수정
"""

# NPE 관련 문서  
npe_guide = """
# NullPointerException 해결 가이드

## 문제 증상
- NullPointerException in UserService
- NPE at line 123
- java.lang.NullPointerException

## 해결 방법

### 1. 널 체크 패턴
```java
if (user != null && user.getName() != null) {
    return user.getName();
}
```

### 2. Optional 사용
```java
Optional<User> user = userRepository.findById(id);
return user.map(User::getName).orElse("Unknown");
```

### 3. 방어적 프로그래밍
```java
@NonNull
public String getUserName(@Nullable User user) {
    return Objects.requireNonNullElse(user?.getName(), "Guest");
}
```

### 4. 초기화 확인
- @Autowired 필드 초기화 확인
- @PostConstruct 메서드 활용

## 관련 이슈
- JIRA-2345: UserService NPE 수정
- JIRA-6789: Optional 패턴 도입
"""

# 메모리 관련 문서
memory_guide = """
# OutOfMemoryError 해결 가이드

## 문제 증상
- OutOfMemoryError: Java heap space
- GC overhead limit exceeded
- 높은 메모리 사용률

## 해결 방법

### 1. 힙 메모리 설정
```bash
java -Xms512m -Xmx2g -XX:+UseG1GC MyApp
```

### 2. 메모리 프로파일링
- JVisualVM 사용
- 힙 덤프 분석
- 메모리 누수 지점 파악

### 3. 코드 최적화
```java
// 대용량 컬렉션 스트림 처리
users.stream()
    .filter(user -> user.isActive())
    .limit(1000)  // 제한 설정
    .collect(toList());
```

### 4. 가비지 컬렉션 튜닝
- G1GC 사용 권장
- GC 로그 분석

## 관련 이슈
- JIRA-3456: 메모리 최적화 작업
- JIRA-7890: GC 튜닝 완료
"""

# 파일들 저장
docs = {
    "db_troubleshooting.md": db_troubleshooting,
    "npe_guide.md": npe_guide, 
    "memory_guide.md": memory_guide
}

for filename, content in docs.items():
    file_path = os.path.join(DOCS_DIR, filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ 생성됨: {file_path}")

print(f"\n📁 문서 디렉토리: {DOCS_DIR}")
print("🎯 RAG 테스트용 샘플 문서 준비 완료!")