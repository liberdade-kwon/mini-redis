# 미니 Redis 구현 로드맵 (Kotlin)

> 목표: Redis를 "온전히 이해"하기 위해, 실제 Redis의 구조를 따라가며 미니 Redis를 직접 구현한다.
> 규칙: **명령 실행은 반드시 싱글 스레드 + 이벤트 루프(java.nio Selector)로 구현한다.**
> (Selector는 리눅스에서 epoll, macOS에서 kqueue를 감싸는 JVM 추상화 — Redis의 ae.c와 정확히 같은 역할)

각 스테이지를 완료하면 코드를 공유 → 리뷰 + 자동 테스트 → 통과 시 "실제 Redis는 어떻게 했나" 비교 학습 → 다음 스테이지.

---

## Module A — 기초 & 이벤트 루프 (Redis의 뼈대)

- [x] **Stage 1. TCP 서버 + PING/PONG** ✅ 2026-07-20 통과 (클라우드 테스트 6/6)
      6379 포트 바인드, `PING`에 `+PONG\r\n` 응답. 이 단계만 블로킹 I/O 허용.
- [x] **Stage 2. 이벤트 루프 전환 (핵심 스테이지)** ✅ 2026-07-21 통과 (5/5 + Stage 1 회귀 6/6)
      java.nio `Selector` 기반 싱글 스레드로 재작성. 다중 클라이언트 동시 처리.
      → 실제 Redis 비교: `ae.c`, `ae_epoll.c` / `ae_kqueue.c`
- [ ] **Stage 3. RESP 프로토콜 파서 + ECHO**
      RESP array/bulk string 파싱. **partial read**(명령이 여러 패킷에 쪼개져 오는 경우) 처리.
      → 비교: `networking.c`의 `readQueryFromClient()`, 클라이언트별 query buffer
- [ ] **Stage 4. SET / GET + 명령 테이블**
      HashMap 키스페이스, 명령 이름 → 핸들러 함수 디스패치 구조.
      → 비교: `server.c`의 command table, `t_string.c`
- [ ] **Stage 5. TTL — lazy expiration**
      `SET key val PX 100`, `EXPIRE`, `TTL`. 접근 시점에 만료 체크.
      → 비교: `expire.c`의 `expireIfNeeded()`
- [ ] **Stage 6. TTL — active expiration + serverCron**
      이벤트 루프에 타이머 이벤트 통합(Selector timeout 활용), 주기적 만료 키 샘플링 삭제.
      → 비교: `serverCron()`, `activeExpireCycle()` — CodeCrafters에는 없는 심화

## Module B — 자료구조

- [ ] **Stage 7. Lists** — RPUSH/LPUSH/LRANGE/LPOP/LLEN
- [ ] **Stage 8. BLPOP (블로킹 명령)**
      스레드를 재우지 않고 이벤트 루프 안에서 "대기 중인 클라이언트" 목록으로 구현.
      → 비교: `blocked.c` — 싱글 스레드에서 블로킹 명령이 가능한 이유
- [ ] **Stage 9. 인코딩 최적화 (심화)** — 작은 리스트는 배열, 커지면 연결 구조로 전환
      → 비교: `listpack.c`, `quicklist.c`, `OBJECT ENCODING`

## Module C — 트랜잭션

- [ ] **Stage 10. INCR/DECR**
- [ ] **Stage 11. MULTI / EXEC / DISCARD** — 명령 큐잉, 큐잉 중 문법 오류 처리
- [ ] **Stage 12. WATCH — 낙관적 락**
      → 비교: `multi.c` — 싱글 스레드에서 트랜잭션이 공짜인 이유

## Module D — 영속화

- [ ] **Stage 13. RDB 쓰기/읽기** — 바이너리 스냅샷 포맷 직접 설계 후 실제 RDB 포맷 파싱
- [ ] **Stage 14. 백그라운드 스냅샷** — fork()가 없는 JVM에서의 대안 구현 + COW 논의
- [ ] **Stage 15. AOF** — 쓰기 명령 append, 재시작 시 replay, fsync 정책 3종
- [ ] **Stage 16. AOF rewrite (심화)**

## Module E — 복제

- [ ] **Stage 17. REPLICAOF 핸드셰이크** — PING → REPLCONF → PSYNC
- [ ] **Stage 18. 전체 동기화** — RDB 전송
- [ ] **Stage 19. 명령 전파** — 마스터가 쓰기 명령을 레플리카로 스트리밍
- [ ] **Stage 20. offset / ACK / WAIT**
      → 비교: `replication.c` — Redis에서 가장 어렵고 가장 배울 게 많은 파트

## Module F — Pub/Sub (보너스)

- [ ] **Stage 21. SUBSCRIBE / PUBLISH**

---

## 진행 방식

1. 스테이지 과제(`stages/STAGE_XX.md`)를 읽고 구현
2. 로컬에서 `tests/stageXX.sh`로 빠르게 자가 검증 (macOS에서 실행 가능)
3. 폴더가 연결되어 있으니 "스테이지 N 다 했어"라고 말하면 → 코드 리뷰 + 클라우드에서 빌드/자동 테스트 → 피드백
4. 통과하면 실제 Redis 소스의 해당 부분을 함께 비교 분석
