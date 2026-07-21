# Stage 3 — 진짜 RESP 파서 + ECHO + 에러 응답

## 목표

지금까지의 "줄 단위 + PING 판별" 지름길을 청산하고, **RESP 프로토콜을 스펙대로
파싱하는 파서**를 만든다. 파서가 생기면 인자 있는 명령이 가능해진다 — 첫 손님은 `ECHO`.

이번 스테이지부터 **진짜 redis-cli로 여러분의 서버를 테스트할 수 있다**:

```
redis-cli -p 6379 ping          → PONG
redis-cli -p 6379 echo hello    → "hello"
```

## 배경 지식 (10분)

### 왜 줄 단위 파싱을 버려야 하나

지금 코드는 `*1`, `$4` 줄을 버리고 `PING` 줄만 본다. 이 방식은 두 곳에서 깨진다:

1. **명령의 경계를 모른다**: `SET name PING`이 오면 세 번째 bulk가 "PING"이라서
   엉뚱하게 +PONG을 응답하게 된다. `*3`을 읽고 "이 명령은 원소 3개"임을 세어야
   명령 단위 경계가 생긴다.
2. **binary-safe가 아니다**: `ECHO "a\r\nb"` — 데이터 안에 \r\n이 있으면
   줄 단위 세계가 무너진다. `$4`가 선언한 길이만큼 **바이트를 세서** 읽어야 한다.

"구조는 구분자로, 데이터는 길이로" — RESP의 이중 프레이밍을 코드로 구현하는 것이
이번 과제다.

### 파싱 대상 문법 (이것만 하면 된다)

클라이언트 → 서버는 항상 "bulk string의 배열" 형태다:

```
*<원소 개수>\r\n
$<길이>\r\n<정확히 길이만큼의 바이트>\r\n     ← 원소 개수만큼 반복
```

예: ECHO hello → `*2\r\n$4\r\nECHO\r\n$5\r\nhello\r\n`

### 파서의 핵심 계약: "부족하면 소비하지 말 것"

누적 버퍼의 앞부분에서 명령 하나를 파싱해보고:
- **완성** → 그만큼 버퍼에서 제거하고 명령 반환. 버퍼에 남은 게 있으면 또 시도 (파이프라인)
- **미완성** (\*는 왔는데 $가 아직, 데이터가 길이보다 짧게 도착 등)
  → **버퍼를 건드리지 않고** "아직"이라고 반환. 다음 READ 이벤트에서 재시도

Stage 2의 `if (idx == -1) break`와 같은 원리를 프로토콜 전체로 확장하는 것.
실제 Redis의 `processMultibulkBuffer()`가 정확히 이 계약으로 동작한다.

## 요구사항

1. RESP 배열/bulk string 파서 구현. **길이 기반으로 바이트를 세며** 파싱한다
   (bulk 데이터 내부의 \r\n에도 안전해야 함)
2. 파싱 결과는 `List<String>` 같은 "명령 + 인자들"로 나오고, 이후 명령 디스패치는
   그 리스트로 판단한다 (첫 원소가 명령 이름)
3. 명령 이름은 **대소문자 무관** (`ping`, `PING`, `Ping` 모두 동작)
4. `PING` → `+PONG\r\n`
5. `ECHO <msg>` → `$<len>\r\n<msg>\r\n` (bulk string으로 응답. len은 **바이트 길이**)
6. 모르는 명령 → `-ERR unknown command '<이름>'\r\n`
7. 파이프라인/쪼개진 패킷: 명령이 아무 지점에서 잘려 도착해도 동작
   (bulk 데이터 한가운데에서 잘리는 경우 포함!)
8. 파서를 별도 파일(예: `Resp.kt`)로 분리해볼 것 — main이 커지기 시작하는 시점이다

## 자가 테스트

```bash
./gradlew run
bash tests/stage03.sh        # 새 테스트 (binary-safe, 잘린 bulk 등 8케이스)
redis-cli -p 6379 echo hello # brew install redis 했다면 실제 클라이언트로!
```

## 힌트 (막힐 때만)

<details>
<summary>힌트 1 — 누적 버퍼를 String에서 바꿔야 하나?</summary>

엄밀한 binary-safe를 위해서는 ByteArray 누적이 맞다. 다만 이번 스테이지는
UTF-8 문자열 데이터까지만 다루므로 StringBuilder를 유지해도 테스트는 통과한다.
단, 길이 계산은 문자 수가 아니라 **바이트 수** 기준임을 잊지 말 것
(`str.toByteArray().size`). 여유가 있으면 ByteArray 전환에 도전해보라 —
Stage 13(RDB)에서 어차피 필요해진다.
</details>

<details>
<summary>힌트 2 — 파서의 뼈대</summary>

"시도하고, 부족하면 통째로 물리기" 패턴:

```
fun tryParse(buffer): 명령 or null   // null = 아직 데이터 부족
    pos = 0
    '*' 확인, \r\n까지 숫자 읽기 → n     (없으면 null)
    n번 반복:
        '$' 확인, \r\n까지 숫자 읽기 → len   (없으면 null)
        buffer에 pos부터 len+2바이트가 있는가? (없으면 null)
        len바이트 잘라 원소로, pos += len+2
    성공: buffer에서 pos만큼 제거하고 명령 반환
```

포인트: 중간에 실패하면 **아무것도 제거하지 않고** null. 성공했을 때만 한꺼번에 제거.
</details>

<details>
<summary>힌트 3 — 디스패치 구조</summary>

파싱된 `List<String>`에 대해 `when (parts[0].uppercase())` 분기가 명령 테이블의
씨앗이 된다. Stage 4에서 SET/GET이 이 when에 추가된다.
</details>

## 생각해볼 것 (리뷰 때 토론)

- 여러분의 tryParse는 실패 시 "처음부터 다시" 파싱한다. 1MB짜리 bulk가 1024바이트씩
  나눠 도착하면 파싱 시도가 몇 번 일어나고, 각 시도의 비용은? 실제 Redis는
  이걸 어떻게 피할까? (힌트: 파싱 상태를 저장해두는 방법 — `client` 구조체의
  multibulklen/bulklen 필드)
- `-ERR`로 시작하는 에러 응답을 받은 redis-cli는 어떻게 표시할까? 직접 확인해보라.

## 실제 Redis에서는

- 파서: `networking.c`의 `processMultibulkBuffer()` — 여러분의 tryParse
- inline command 파서: `processInlineBuffer()` — telnet용 별도 경로가 따로 있다
- 디스패치: `server.c`의 `processCommand()` + 명령 테이블 (`commands.def`)
- 응답 생성: `networking.c`의 `addReply*()` 함수군
- 통과 후 함께 볼 것: `processMultibulkBuffer()`의 "파싱 상태 저장" 최적화
