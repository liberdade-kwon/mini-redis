# Stage 5 — TTL: lazy expiration (SET PX / EXPIRE / TTL)

## 목표

키에 **수명**을 부여한다. `SET key val PX 100`(100ms 후 만료), `EXPIRE`, `TTL`을
구현하고, 만료된 키는 **접근하는 순간** 사라지게 한다(lazy expiration).

```
redis-cli -p 6379 set session abc PX 100   → OK
redis-cli -p 6379 get session              → "abc"   (100ms 내)
(200ms 후)
redis-cli -p 6379 get session              → (nil)   (만료됨)
redis-cli -p 6379 ttl session              → (integer) -2
```

## 배경 지식 (10분)

### 만료를 "언제" 처리하나 — 두 가지 전략

키가 만료 시각을 지났다고 해서 그 순간 누군가 지워주는 게 아니다. Redis는 두 전략을 쓴다:

1. **lazy (수동적)**: 키에 **접근할 때** 만료됐는지 확인하고, 지났으면 그때 삭제.
   이번 스테이지에서 구현한다. 장점은 단순함, 단점은 "접근 안 하면 영원히 메모리 점유".
2. **active (능동적)**: 백그라운드에서 주기적으로 만료된 키를 골라 삭제.
   Stage 6에서 serverCron과 함께 구현한다.

실제 Redis는 **둘 다** 쓴다 — lazy로 정확성을, active로 메모리 회수를 보장한다.

### 만료 시각은 어떻게 저장하나

키스페이스(값 저장)와 **별도로**, "키 → 만료 절대시각(epoch millis)" 맵을 하나 더 둔다.
실제 Redis도 `redisDb`에 `dict *dict`(값)와 `dict *expires`(만료)를 분리해서 갖는다.
왜 상대시간(TTL)이 아니라 **절대시각**으로 저장하나? — 상대시간이면 시간이 흐를수록
매번 갱신해야 하지만, 절대시각이면 "지금 > 만료시각?" 한 번의 비교로 끝나기 때문이다.

### 이번 스테이지의 핵심 규칙

**모든 키 접근 경로에서 만료를 먼저 확인**해야 한다. GET만 고치면 안 된다 —
만료된 키는 어디서 접근하든 "없는 것"으로 보여야 하므로, 값 조회 전에
`expireIfNeeded(key)` 같은 관문을 통과시키는 구조가 필요하다.

## 요구사항

1. `SET key val PX <밀리초>` → 저장 + 만료시각 설정. 기존 `SET key val`도 계속 동작
   (PX 없으면 만료 없음). 옵션 파싱이 생기므로 SET의 arity 고정이 깨진다 — 아래 힌트 참고
2. `SET key val EX <초>` → 초 단위 버전도 지원 (PX는 밀리초, EX는 초)
3. `EXPIRE key <초>` → 기존 키에 만료 부여. 키 있으면 `:1\r\n`, 없으면 `:0\r\n` (integer 응답)
4. `TTL key` → 남은 수명(초). 규칙: 키 없음 → `:-2`, 키는 있지만 만료 없음 → `:-1`,
   있으면 → 남은 초(올림 또는 내림 무관, 양수)
5. **lazy expiration**: 만료된 키는 GET/TTL 등 접근 시 삭제되고 "없음"으로 응답.
   값 맵과 만료 맵 **양쪽에서** 제거할 것
6. SET으로 키를 덮어쓰면 기존 만료는 사라진다 (PX/EX 없이 SET하면 영속 키가 됨)

## 구현 가이드

### 수도코드 뼈대

```
val keyspace = mutableMapOf<String, String>()
val expires  = mutableMapOf<String, Long>()      // key -> 만료 절대시각(epoch millis)

// 모든 조회의 관문: 만료됐으면 지우고 true 반환
fun expireIfNeeded(key: String): Boolean {
    val at = expires[key] ?: return false          // 만료 설정 없음
    if (now() >= at) {                             // ※ now() = System.currentTimeMillis()
        keyspace.remove(key)
        expires.remove(key)
        return true
    }
    return false
}

// GET을 이렇게 바꾼다
"GET" -> {
    expireIfNeeded(parts[1])                        // 먼저 관문 통과
    val v = keyspace[parts[1]] ?: return null-bulk
    ...
}

// SET: 옵션 파싱
"SET" -> {
    val key = parts[1]; val value = parts[2]
    keyspace[key] = value
    expires.remove(key)                             // ※ 기존 만료 제거 (덮어쓰기 규칙)
    // ※ parts[3]이 "PX"/"EX"(대소문자 무관)면 parts[4]를 숫자로 읽어
    //    expires[key] = now() + (PX면 그대로 / EX면 *1000)
    "+OK\r\n"
}

// TTL
"TTL" -> {
    if (expireIfNeeded(key) || key 없음) → ":-2\r\n"
    else if (expires[key] 없음) → ":-1\r\n"
    else → ":${(expires[key]!! - now() + 999) / 1000}\r\n"   // 남은 초
}
```

### arity 문제 — SET이 가변 인자가 됐다

지금 명령 테이블은 `arity`가 고정 정수다. 그런데 `SET k v`(3)와 `SET k v PX 100`(5)이
둘 다 유효해졌다. 두 가지 해결책 중 선택:

- **간단**: SET의 arity 검증을 "정확히 N"이 아니라 "최소 3"으로. arity를 음수로 두고
  `if (arity < 0) parts.size >= -arity else parts.size == arity`로 해석
  (이게 실제 Redis 방식 — 음수 arity = "최소")
- **더 단순**: SET만 arity 검증에서 예외로 두고 핸들러 안에서 `parts.size` 직접 검사

실제 Redis의 음수 arity를 체험하는 의미로 첫 번째를 추천한다.

### API 치트시트

| API | 하는 일 | 주의점 |
|---|---|---|
| `System.currentTimeMillis()` | 현재 epoch 밀리초(Long) | 절대시각 저장/비교의 기준. 단조증가 아님(NTP 보정 가능)이나 이 단계는 무시 |
| `map.remove(key)` | 키 제거, 없으면 null 반환 | 값 맵·만료 맵 양쪽 다 제거해야 누수 없음 |
| `str.equals("PX", ignoreCase=true)` | 대소문자 무관 비교 | 옵션 이름 px/PX/Px 모두 허용 |
| `str.toLongOrNull()` | 밀리초/초 파싱 | 실패 시 `-ERR value is not an integer...` 응답 권장 |
| `:<정수>\r\n` | RESP integer 응답 | EXPIRE/TTL 응답 형식. `:1\r\n`, `:-2\r\n` 등 |

## 자가 테스트

```bash
./gradlew run
bash tests/stage05.sh        # 시간 의존 테스트 — sleep 포함, 몇 초 걸림
```

## 힌트 (막힐 때만)

<details>
<summary>힌트 1 — expireIfNeeded를 어디서 부를까</summary>

값에 접근하는 모든 명령(GET, TTL, 그리고 뒤 스테이지의 EXISTS/타입 명령들)의
맨 앞. 공통 관문이므로 헬퍼로 빼두면 명령이 늘어도 한 줄씩만 추가된다.
실제 Redis의 `lookupKeyRead()`가 내부에서 `expireIfNeeded()`를 부르는 구조와 같다.
</details>

<details>
<summary>힌트 2 — 시간 테스트가 불안정하면</summary>

now() 비교는 `>=`로. 경계(정확히 만료시각)에서 만료로 치는 게 관례다.
테스트는 여유(PX 100 → 250ms 대기)를 두었으니 로직이 맞으면 안정적으로 통과한다.
</details>

## 생각해볼 것 (리뷰 때 토론)

- lazy expiration만 있으면 생기는 문제: 만료됐지만 아무도 접근 안 하는 키 100만 개가
  메모리를 점유한다. 이게 Stage 6(active expiration)이 필요한 이유. 실제 Redis는
  이걸 방치하면 어떤 지표가 나빠질까?
- 만료 확인에 `System.currentTimeMillis()`를 쓰는데, 서버 시계가 바뀌면(NTP 점프)
  무슨 일이 일어날까? Redis는 왜 monotonic clock을 일부 경로에서 쓸까?
- SET에 PX와 EX를 동시에 주면? 실제 Redis는 에러를 낸다. 지금 구현은?

## 실제 Redis에서는

- 만료 저장: `redisDb`의 `dict *expires` (값과 분리된 별도 dict)
- lazy 삭제: `db.c`의 `expireIfNeeded()` — `lookupKeyRead()`/`lookupKeyWrite()`가 호출
- 절대시각 저장: `setExpire()` — epoch millis
- SET 옵션 파싱: `t_string.c`의 `setGenericCommand()` (NX/XX/EX/PX/KEEPTTL...)
- 음수 arity: `struct redisCommand`의 arity 필드 (음수 = 최소 N개)
- 통과 후 함께 볼 것: `expireIfNeeded()`와 `activeExpireCycle()`의 역할 분담 (Stage 6 예고)
