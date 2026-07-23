#!/usr/bin/env python3
"""Stage 4 로컬 자가 테스트 — SET/GET, 키스페이스 공유, arity 검증"""
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

def recv_line(s):
    buf = b""
    try:
        while not buf.endswith(b"\r\n"):
            c = s.recv(1)
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

# [1] SET → +OK
s = conn(); s.sendall(cmd("SET", "name", "kwon"))
r = recv_exact(s, 5)
check("SET name kwon → +OK", r == b"+OK\r\n", repr(r))

# [2] GET 히트 (같은 연결)
s.sendall(cmd("GET", "name"))
r = recv_exact(s, 10); s.close()
check("GET name → $4 kwon", r == b"$4\r\nkwon\r\n", repr(r))

# [3] GET 미스 → $-1
s = conn(); s.sendall(cmd("GET", "nothing_here"))
r = recv_exact(s, 5); s.close()
check("GET 미스 → $-1 (nil)", r == b"$-1\r\n", repr(r))

# [4] 덮어쓰기
s = conn(); s.sendall(cmd("SET", "name", "redis") + cmd("GET", "name"))
r = recv_exact(s, 5 + 11); s.close()
check("SET 덮어쓰기", r == b"+OK\r\n$5\r\nredis\r\n", repr(r))

# [5] 키 대소문자 구분
s = conn(); s.sendall(cmd("GET", "NAME"))
r = recv_exact(s, 5); s.close()
check("GET NAME (다른 키) → nil", r == b"$-1\r\n", repr(r))

# [6] arity 오류 → -ERR wrong number
s = conn(); s.sendall(cmd("SET", "only_key"))
r = recv_line(s)
ok1 = r.startswith(b"-ERR wrong number")
s.sendall(cmd("GET"))
r2 = recv_line(s); s.close()
ok2 = r2.startswith(b"-ERR wrong number")
check("SET k / GET (인자 부족) → wrong number", ok1 and ok2, f"{r!r} {r2!r}")

# [7] 키스페이스 공유: A가 SET, B가 GET
a = conn(); a.sendall(cmd("SET", "shared", "yes"))
recv_exact(a, 5)
b = conn(); b.sendall(cmd("GET", "shared"))
r = recv_exact(b, 9); a.close(); b.close()
check("연결 A의 SET을 연결 B가 GET", r == b"$3\r\nyes\r\n", repr(r))

# [8] arity 오류 후 서버/연결 생존
s = conn(); s.sendall(cmd("SET", "x"))
recv_line(s)
s.sendall(cmd("PING"))
r = recv_exact(s, 7); s.close()
check("에러 후 같은 연결에서 PING 정상", r == b"+PONG\r\n", repr(r))

# [9] 회귀: ECHO
s = conn(); s.sendall(cmd("ECHO", "still-works"))
r = recv_exact(s, 18); s.close()
check("회귀: ECHO", r == b"$11\r\nstill-works\r\n", repr(r))

passed = sum(results)
print(f"\n결과: {passed}/{len(results)} 통과")
if passed == len(results):
    print("🎉 Stage 4 로컬 테스트 통과! 이제 여러분의 서버는 데이터베이스입니다. '다 했어'를 외쳐주세요.")
sys.exit(0 if passed == len(results) else 1)
