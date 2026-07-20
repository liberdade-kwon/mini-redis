# Stage 2 — 이벤트 루프 전환 (이 커리큘럼의 핵심 스테이지)

## 목표

Stage 1의 블로킹 서버를 **java.nio Selector 기반 싱글 스레드 이벤트 루프**로 재작성한다.
여러 클라이언트가 **동시에** 연결되어 각자 PING/PONG을 주고받을 수 있어야 한다.

이것이 실제 Redis의 `ae.c` + `ae_epoll.c`가 하는 일이다. JVM의 `Selector`는
리눅스에서 epoll, macOS에서 kqueue를 감싸는 추상화이므로, 지금까지 공부한
"epoll_ctl로 등록 → epoll_wait에서 잠들기 → 준비된 fd만 처리"가 그대로 코드가 된다.

## 배경 지식 (15분)

### Stage 1 구조의 한계 (직접 확인해보라)

Stage 1 서버에 터미널 두 개로 동시에 `nc localhost 6379` 접속해보라.
두 번째 클라이언트는 첫 번째가 끊을 때까지 응답을 못 받는다 — 스레드가
첫 클라이언트의 `readLine()`에 붙잡혀 있기 때문이다. "어디서 기다릴 것인가"를
바꾸는 것이 이번 스테이지의 전부다.

### java.nio 핵심 API ↔ epoll 대응표

| java.nio | epoll (리눅스) | 역할 |
|---|---|---|
| `Selector.open()` | `epoll_create1()` | 이벤트 감시 인스턴스 생성 |
| `channel.register(selector, ops)` | `epoll_ctl(ADD)` | 감시 대상 등록 |
| `selector.select()` | `epoll_wait()` | 이벤트 대기 (여기서 잠듦) |
| `selector.selectedKeys()` | epoll_wait의 반환 배열 | 준비된 fd 목록 |
| `SelectionKey.OP_ACCEPT / OP_READ` | EPOLLIN (리스닝/일반 fd) | 관심 이벤트 종류 |

### 주의: readLine()은 이제 없다

`SocketChannel`은 `ByteBuffer`로 바이트를 직접 읽는다. BufferedReader가
대신 해주던 "줄 조립"을 이제 직접 해야 한다. 그리고 partial read —
`PI`까지만 도착한 상태 — 도 직접 다뤄야 한다: 읽은 바이트를 **클라이언트별
누적 버퍼**에 붙여두고, `\r\n`(또는 `\n`)이 완성된 부분만 잘라 처리하는 방식.
Stage 1에서 라이브러리가 해줬던 일을 손으로 하면서 원리를 체득하는 것이 목표다.

## 요구사항

1. `ServerSocketChannel` + `SocketChannel` + `Selector` 사용, 모든 채널 `configureBlocking(false)`
2. **스레드는 main 하나만.** Thread, ExecutorService, 코루틴 사용 금지
3. accept도 이벤트로 처리한다: 리스닝 채널을 `OP_ACCEPT`로 등록하고,
   이벤트 루프 안에서 accept → 새 채널을 `OP_READ`로 등록
4. 동시에 연결된 클라이언트 N명이 각자 독립적으로 PING → `+PONG\r\n` 응답을 받는다
   (한 클라이언트가 응답을 기다리는 동안 다른 클라이언트도 응답받을 수 있어야 함)
5. Stage 1의 동작 보존: 파이프라인(한 패킷에 PING 여러 개), 쪼개진 패킷,
   정상 종료(EOF), 비정상 종료(RST) 모두 처리. 어떤 클라이언트의 종료/사고도
   다른 클라이언트와 서버에 영향을 주지 않는다
6. 클라이언트별 상태(누적 버퍼 등)는 채널과 함께 관리하고, 연결 종료 시 정리한다

## 자가 테스트

```bash
./gradlew run                # 터미널 1
bash tests/stage02.sh        # 터미널 2 (python3 필요 — 맥 기본 포함)
```

수동 체감 테스트: 터미널 두 개에서 동시에 `nc localhost 6379` → 둘 다
즉시 PING/PONG이 되어야 한다 (Stage 1에서는 안 됐던 그것).

## 힌트 (막힐 때만, 순서대로 열어보기)

<details>
<summary>힌트 1 — 이벤트 루프의 뼈대</summary>

무한 루프 안에서: `selector.select()` (잠듦) → 깨어나면 `selectedKeys()` 순회 →
key가 acceptable이면 accept 처리, readable이면 read 처리 → **처리한 key는
반드시 iterator.remove()** (안 하면 같은 이벤트를 무한 재처리한다 — 자주 하는 실수 1위).
</details>

<details>
<summary>힌트 2 — 클라이언트별 상태는 어디에 두나</summary>

`SelectionKey.attach(객체)` / `key.attachment()`가 정확히 이 용도다.
"이 채널의 누적 문자열 버퍼"를 담는 작은 클래스를 만들어 attach해두면,
READ 이벤트가 올 때마다 그 클라이언트의 상태를 꺼내 쓸 수 있다.
실제 Redis도 fd마다 client 구조체를 두는 것과 같은 구조다.
</details>

<details>
<summary>힌트 3 — read 이벤트 처리의 정석</summary>

`channel.read(buf)`의 반환값 세 가지를 모두 다뤄라:
양수(그만큼 읽음 → 누적 버퍼에 추가 → 완성된 줄 처리), 0(할 것 없음),
-1(EOF → key 취소하고 채널 close). 예외가 나면 RST — 마찬가지로 그 채널만 정리.
누적 버퍼에서 줄 자르기는 `\n` 기준으로 자르고 `\r`을 trim하면 간단하다.
</details>

## 생각해볼 것 (리뷰 때 토론)

- `selector.select()`와 Stage 1의 `readLine()` — 둘 다 "블로킹"인데 무엇이 결정적으로 다른가?
- 클라이언트 1만 명이 접속해 있고 그중 1명만 데이터를 보낸다면, 이 구조에서 CPU는 무슨 일을 하는가?
- 지금 구조에서 어떤 명령 하나가 10초 걸린다면 무슨 일이 일어나는가? (실제 Redis의 KEYS/FLUSHALL 이슈, 그리고 O(1) 명령 설계 철학과 연결됨)

## 실제 Redis에서는

- 이벤트 루프 본체: `ae.c`의 `aeMain()` → `aeProcessEvents()` — 여러분의 while + select() 에 해당
- accept 핸들러: `networking.c`의 `acceptTcpHandler()` — OP_ACCEPT 처리에 해당
- read 핸들러: `networking.c`의 `readQueryFromClient()` — OP_READ 처리에 해당
- 클라이언트별 상태: `server.h`의 `client` 구조체 (querybuf가 여러분의 누적 버퍼)
- 통과 후 함께 볼 것: `ae_epoll.c` 전체 (150줄) — 여러분이 쓴 Selector의 리눅스 구현체
