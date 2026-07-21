#!/usr/bin/env python3
"""Stage 3 로컬 자가 테스트 — RESP 파서 검증 (binary-safe, 잘린 bulk 포함)"""
import socket, sys, time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 6379
results = []

def conn():
    s = socket.create_connection(("127.0.0.1", PORT), timeout=3)
    s.settimeout(3)
    return s

def recv_exact(s, n):
    buf = b""
    try:
        while len(buf) < n:
            c = s.recv(n - len(buf))
            if not c: break
            buf += c
    except socket.timeout:
        pass
    return buf

def check(name, cond, detail=""):
    results.append(cond)
    print(("  ok  " if cond else "  FAIL") + f" {name}" + (f"  ({detail})" if detail and not cond else ""))

def cmd(*parts):
    out = f"*{len(parts)}\r\n".encode()
    for p in parts:
        b = p if isinstance(p, bytes) else p.encode()
        out += f"${len(b)}\r\n".encode() + b + b"\r\n"
    return out

# [1] PING (회귀)
s = conn(); s.sendall(cmd("PING"))
r = recv_exact(s, 7); s.close()
check("PING → +PONG", r == b"+PONG\r\n", repr(r))

# [2] ECHO 기본
s = conn(); s.sendall(cmd("ECHO", "hello"))
r = recv_exact(s, 11); s.close()
check("ECHO hello → $5 hello", r == b"$5\r\nhello\r\n", repr(r))

# [3] 대소문자 무관
s = conn(); s.sendall(cmd("echo", "hi") + cmd("Ping"))
r = recv_exact(s, 8 + 7); s.close()
check("소문자 echo / Ping", r == b"$2\r\nhi\r\n+PONG\r\n", repr(r))

# [4] binary-safe: 데이터 안에 \r\n
payload = b"a\r\nb"
s = conn(); s.sendall(cmd("ECHO", payload))
expected = b"$4\r\na\r\nb\r\n"
r = recv_exact(s, len(expected)); s.close()
check("ECHO 'a\\r\\nb' (binary-safe)", r == expected, repr(r))

# [5] bulk 데이터 한가운데서 잘린 패킷
full = cmd("ECHO", "abcdefgh")
s = conn()
s.sendall(full[:full.index(b"abcdefgh") + 3])   # 데이터 3바이트까지만
time.sleep(0.3)
s.sendall(full[full.index(b"abcdefgh") + 3:])   # 나머지
expected = b"$8\r\nabcdefgh\r\n"
r = recv_exact(s, len(expected)); s.close()
check("bulk 중간에서 잘린 패킷", r == expected, repr(r))

# [6] 파이프라인: ECHO + PING + ECHO 한 패킷
s = conn(); s.sendall(cmd("ECHO", "one") + cmd("PING") + cmd("ECHO", "two"))
expected = b"$3\r\none\r\n+PONG\r\n$3\r\ntwo\r\n"
r = recv_exact(s, len(expected)); s.close()
check("파이프라인 3연속 혼합", r == expected, repr(r))

# [7] 모르는 명령 → -ERR
s = conn(); s.sendall(cmd("FOO", "bar"))
r = recv_exact(s, 4); s.close()
check("모르는 명령 → -ERR ...", r.startswith(b"-ERR"), repr(r))

# [8] SET name PING 함정 (셋째 인자가 PING이어도 PONG하면 안 됨)
s = conn(); s.sendall(cmd("SET", "name", "PING"))
r = recv_exact(s, 4); s.close()
check("SET name PING → PONG 아님(-ERR)", r.startswith(b"-ERR"), repr(r))

passed = sum(results)
print(f"\n결과: {passed}/{len(results)} 통과")
if passed == len(results):
    print("🎉 Stage 3 로컬 테스트 통과! redis-cli로도 놀아보고, '다 했어'를 외쳐주세요.")
sys.exit(0 if passed == len(results) else 1)
