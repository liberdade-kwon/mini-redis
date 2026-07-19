#!/usr/bin/env bash
# Stage 1 자가 테스트 — 서버가 6379(또는 $1 포트)에서 실행 중이어야 함
set -u
PORT="${1:-6379}"
PASS=0; FAIL=0

check() {
  local name="$1" expected="$2" actual="$3"
  if [[ "$actual" == "$expected" ]]; then
    echo "  ok: $name"; PASS=$((PASS+1))
  else
    echo "  FAIL: $name"
    echo "        expected: $(printf '%q' "$expected")"
    echo "        actual:   $(printf '%q' "$actual")"
    FAIL=$((FAIL+1))
  fi
}

echo "[1] 단일 PING"
RESP=$(printf '*1\r\n$4\r\nPING\r\n' | nc -w 2 localhost "$PORT" | head -c 7)
check "PING -> +PONG" "$(printf '+PONG\r\n' | head -c 7)" "$RESP"

echo "[2] 같은 연결에서 PING 3회"
RESP=$(printf '*1\r\n$4\r\nPING\r\n*1\r\n$4\r\nPING\r\n*1\r\n$4\r\nPING\r\n' | nc -w 2 localhost "$PORT")
COUNT=$(printf '%s' "$RESP" | grep -c PONG)
check "PONG 3회 수신" "3" "$COUNT"

echo "[3] 연결 종료 후 재접속"
printf '*1\r\n$4\r\nPING\r\n' | nc -w 2 localhost "$PORT" > /dev/null
RESP=$(printf '*1\r\n$4\r\nPING\r\n' | nc -w 2 localhost "$PORT" | head -c 7)
check "재접속 후에도 PONG" "$(printf '+PONG\r\n' | head -c 7)" "$RESP"

echo
echo "결과: $PASS 통과, $FAIL 실패"
[[ $FAIL -eq 0 ]] && echo "🎉 Stage 1 로컬 테스트 통과! 코드를 공유해주면 정식 리뷰를 시작할게요."
exit $FAIL
