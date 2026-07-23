# Stage 4 — SET / GET + 명령 테이블 + 키스페이스

## 목표

드디어 "데이터베이스"가 된다. 키스페이스(키→값 저장소)를 만들고 `SET`/`GET`을
구현하며, 명령이 늘어나기 시작했으니 디스패치를 **명령 테이블** 구조로 정리한다.

```
redis-cli -p 6379 set name kwon   → OK
redis-cli -p 6379 get name        → "kwon"
redis-cli -p 6379 get nothing     → (nil)
```

## 배경 지식 (10분)

### 키스페이스는 그냥 해시맵이다 (진짜로)

Redis의 심장인 키스페이스는 개념적으로 `HashMap<String, 값>` 하나다. 실제 Redis도
`redisDb` 구조체의 `dict` 필드 — 해시테이블 — 가 전부다. 우리는 Kotlin의
`mutableMapOf`로 시작한다. (Redis의 dict가 특별한 건 incremental rehashing 때문인데,
그건 뒤 스테이지의 심화 주제로 남겨둔다)

### 락이 왜 없어도 되는가 — 배운 이론이 실전이 되는 순간

키스페이스는 **모든 클라이언트가 공유하는 전역 상태**다. 멀티스레드 서버라면
여기에 락이 필요했겠지만, 우리 이벤트 루프는 명령을 한 번에 하나씩 실행하므로
`map[key] = value`에 어떤 동기화도 필요 없다. 클라이언트 A의 SET 도중에 B의 GET이
끼어드는 일은 **구조적으로 불가능**하다. 테스트 [7]이 이걸 검증한다 —
A가 SET한 값을 B가 GET으로 읽는다 (연결은 달라도 키스페이스는 하나).

### 응답 프로토콜 추가분

| 상황 | 응답 | 의미 |
|---|---|---|
| SET 성공 | `+OK\r\n` | simple string |
| GET 히트 | `$4\r\nkwon\r\n` | bulk string (ECHO와 동일) |
| GET 미스 | `$-1\r\n` | **null bulk string** — "없음"의 RESP 표현. redis-cli는 (nil)로 표시 |
| 인자 개수 오류 | `-ERR wrong number of arguments for 'set' command\r\n` | 에러 |

## 요구사항

1. `SET key value` → 저장 후 `+OK\r\n`. 같은 키에 다시 SET하면 덮어쓴다
2. `GET key` → 있으면 bulk string, 없으면 `$-1\r\n`
3. 키는 **대소문자 구분** (`name` ≠ `NAME`), 명령 이름은 여전히 구분 없음
4. **인자 개수 검증**: `SET k`(인자 부족), `GET`(인자 없음) 등은
   `-ERR wrong number of arguments for '<명령>' command\r\n`.
   잘못된 명령이 서버를 죽이거나 다른 클라이언트에 영향을 주면 안 된다
5. **명령 테이블 리팩터링**: when 분기 대신, "명령 이름 → (핸들러, 요구 인자 수)"
   맵 구조로. 새 명령 추가 = 테이블에 한 줄 추가가 되도록
6. 키스페이스는 전역 하나. 어떤 클라이언트가 접속했든 같은 데이터를 본다

## 구현 가이드

### 수도코드 뼈대

```
// Commands.kt (새 파일 추천)

val keyspace = mutableMapOf<String, String>()     // 전역 키스페이스 (락 불필요 — 왜인지 설명할 수 있어야 함)

// 명령 하나의 정의: 핸들러 + 인자 개수 규칙
class CommandSpec(
    val arity: Int,                               // 명령 포함 총 인자 수. SET=3, GET=2, PING=1, ECHO=2
    val handler: (List<String>) -> String
)

val commandTable = mapOf(
    "PING" to CommandSpec(1) { "+PONG\r\n" },
    "ECHO" to CommandSpec(2) { parts -> /* Stage 3에서 만든 것 이동 */ },
    "SET"  to CommandSpec(3) { parts -> /* ※ keyspace에 저장 → +OK */ },
    "GET"  to CommandSpec(2) { parts -> /* ※ 조회 → bulk or $-1 */ },
)

fun execute(parts: List<String>): String {
    val name = parts[0].uppercase()
    val spec = commandTable[name] ?: return "-ERR unknown command '${parts[0]}'\r\n"
    // ※ 인자 개수 검증: parts.size와 spec.arity 비교 → 틀리면 wrong number of arguments 에러
    return spec.handler(parts)
}
```

Main.kt의 기존 execute는 삭제하고 이 파일의 것을 쓴다. 이벤트 루프는 손대지 않는다 —
파서와 디스패치가 분리되어 있으면 명령이 늘어도 루프는 불변이라는 걸 체감하는 것도 이번 목표.

### API 치트시트 (이번 스테이지에서 처음 쓰는 것들)

| API | 하는 일 | 주의점 |
|---|---|---|
| `mutableMapOf<String, String>()` | 수정 가능한 해시맵 생성 | 파일 최상위에 두면 전역(싱글톤)이 된다 |
| `map[key] = value` | 저장/덮어쓰기 | 이미 있으면 조용히 덮어씀 — SET의 스펙과 일치 |
| `map[key]` | 조회, 없으면 **null** | Kotlin의 null 안전성과 `$-1` 응답이 자연스럽게 만난다: `?: return "$-1\r\n"` 패턴 |
| `mapOf("A" to x, ...)` | 읽기 전용 맵 리터럴 | 명령 테이블용 — 실행 중 안 바뀌므로 mutable일 필요 없음 |
| `(List<String>) -> String` | 함수 타입 | 핸들러를 값으로 다루는 것 — Redis 명령 테이블의 함수 포인터에 해당 |
| `{ parts -> ... }` | 람다 | CommandSpec에 핸들러를 넘길 때 |

## 자가 테스트

```bash
./gradlew run
bash tests/stage04.sh
redis-cli -p 6379          # 대화형으로 set/get 갖고 놀기 추천
```

## 힌트 (막힐 때만)

<details>
<summary>힌트 1 — arity 검증을 테이블 조회 "뒤"에 두는 이유</summary>

모르는 명령의 에러(-ERR unknown command)가 인자 검증보다 우선이어야 자연스럽다.
`FOO a b c`는 "인자 개수 오류"가 아니라 "모르는 명령"이다.
</details>

<details>
<summary>힌트 2 — GET의 null 처리 한 줄</summary>

`val v = keyspace[parts[1]] ?: return "$-1\r\n"` — 이후는 ECHO의 bulk 조립과 동일하다.
공통화하고 싶다면 `fun bulk(s: String): String` 헬퍼를 만들어 ECHO/GET이 같이 쓰게 하라.
</details>

## 생각해볼 것 (리뷰 때 토론)

- SET과 GET이 동시에 실행될 수 없는 이유를, 이벤트 루프의 코드 위치로 정확히
  설명할 수 있는가? ("싱글 스레드라서"보다 한 단계 구체적으로)
- 실제 Redis의 SET은 `SET k v EX 10 NX` 같은 옵션이 붙는다. 지금의 arity 고정
  방식으로는 표현이 안 되는데, Redis 명령 테이블은 이걸 어떻게 표현할까?
  (힌트: 음수 arity)
- 값이 1GB짜리 문자열이면 GET 응답의 write는 어떻게 될까? (partial write가
  드디어 현실이 되는 시나리오 — 다음 스테이지들 어딘가에서 만난다)

## 실제 Redis에서는

- 키스페이스: `server.h`의 `redisDb` → `dict *dict` (해시테이블)
- 명령 테이블: `commands.def` (자동 생성) + `server.c`의 `lookupCommand()` —
  여러분의 commandTable과 lookup이 정확히 이 구조
- arity 검증: `processCommand()`가 `cmd->arity`로 검사 — 음수면 "최소 N개"
- SET/GET 구현체: `t_string.c`의 `setCommand()` / `getCommand()`
- 통과 후 함께 볼 것: `lookupCommand()`와 `processCommand()`의 검증 순서
