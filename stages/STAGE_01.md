# Stage 1 — TCP 서버 바인드 + PING/PONG

## 목표

6379 포트에서 TCP 연결을 받고, 클라이언트가 보내는 `PING` 명령에 `+PONG\r\n`으로 응답하는 서버를 만든다.

## 배경 지식 (5분)

redis-cli가 `PING`을 보낼 때 실제 소켓에 흐르는 바이트는 이렇다 (RESP 프로토콜):

```
*1\r\n$4\r\nPING\r\n
```

- `*1` — 원소 1개짜리 배열
- `$4` — 길이 4인 bulk string
- `PING` — 명령 이름

서버의 정상 응답은 simple string:

```
+PONG\r\n
```

**Stage 1에서는 파싱하지 않아도 된다.** 뭔가 읽히면 `+PONG\r\n`을 돌려주는 것으로 충분하다.
(제대로 된 RESP 파서는 Stage 3에서 만든다. 단, 아래 요구사항 3번 주의)

## 요구사항

1. 6379 포트에 바인드한다 (인자로 포트를 받으면 그 포트 사용 — Main.kt 스켈레톤 참고)
2. 클라이언트가 접속해서 데이터를 보내면 `+PONG\r\n`을 응답한다
3. **같은 연결에서 PING을 여러 번 보내면, 그 횟수만큼 응답해야 한다** (한 번 응답하고 연결을 닫으면 안 됨)
4. 클라이언트가 연결을 끊으면 서버는 죽지 않고 다음 연결을 받는다
5. 이 스테이지에서는 블로킹 I/O(`java.net.ServerSocket`) 사용 가능. 클라이언트는 한 번에 하나만 처리해도 OK

## 자가 테스트

```bash
./gradlew run          # 터미널 1에서 서버 실행
bash tests/stage01.sh  # 터미널 2에서 테스트
```

redis-cli가 설치되어 있다면 이것도 가능:

```bash
redis-cli -p 6379 ping   # → PONG
```

## 힌트 (막힐 때만 열어보기)

<details>
<summary>힌트 1 — 뼈대</summary>

`ServerSocket(port)` → `accept()` 루프 → 소켓의 inputStream에서 read → outputStream에 `+PONG\r\n` write → flush.
</details>

<details>
<summary>힌트 2 — 요구사항 3을 놓치기 쉬운 이유</summary>

read 한 번 → write 한 번 하고 소켓을 닫아버리면 두 번째 PING이 실패한다.
클라이언트별로 "read가 -1(EOF)을 돌려줄 때까지" 반복하는 내부 루프가 필요하다.
</details>

## 생각해볼 것 (완료 후 리뷰 때 이야기할 주제)

- 클라이언트 A가 접속해 있는 동안 클라이언트 B가 접속하면 무슨 일이 일어나는가? 직접 실험해보라.
  (터미널 두 개에서 `nc localhost 6379` 실행) — 이 문제가 Stage 2의 존재 이유다.
- `read()`는 어디서 블로킹되는가? 그 동안 이 스레드는 무엇을 하는가?

## 실제 Redis에서는

- 리스닝 소켓 생성: `listenToPort()` (`server.c`) — 우리의 ServerSocket에 해당
- 단, Redis는 accept조차 이벤트 루프의 이벤트다: 리스닝 fd가 epoll에 등록되어 있고,
  "accept 가능" 이벤트가 오면 `acceptTcpHandler()` (`networking.c`)가 실행된다. Stage 2에서 이 구조를 만든다.
