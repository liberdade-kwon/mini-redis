#!/usr/bin/env python3
"""Stage 5 로컬 자가 테스트 — TTL, lazy expiration (시간 의존, 몇 초 소요)"""
import socket, sys, time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 6379
results = []

def conn():
    s = socket.create_connection(("127.0.0.1", PORT), timeout=3)
    s.settimeout(3)
    return s

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

def recv_bulk(s):
    """$len\r\n...\r\n 또는 $-1\r\n 을 통째로 읽음"""
    head = recv_line(s)
    if head == b"$-1\r\n" or not head.startswith(b"$"):
        return head
    n = int(head[1:-2])
    body = b""
    while len(body) < n + 2:
        c = s.recv(n + 2 - len(body))
        if not c: break
        body += c
    return head + body

def check(name, cond, detail=""):
    results.append(cond)
    print(("  ok  " if cond else "  FAIL") + f" {name}" + (f"  ({detail})" if detail and not cond else ""))

def cmd(*parts):
    out = f"*{len(parts)}\r\n".encode()
    for p in parts:
        b = p if isinstance(p, bytes) else str(p).encode()
        out += f"${len(b)}\r\n".encode() + b + b"\r\n"
    return out

# [1] SET PX + GET 즉시 (살아있음)
s = conn(); s.sendall(cmd("SET", "sess", "abc", "PX", "300")); recv_line(s)
s.sendall(cmd("GET", "sess"))
r = recv_bulk(s)
check("SET PX 후 즉시 GET → 값", r == b"$3\r\nabc\r\n", repr(r))

# [2] 만료 후 GET → nil
time.sleep(0.4)
s.sendall(cmd("GET", "sess"))
r = recv_bulk(s)
check("PX 만료 후 GET → nil", r == b"$-1\r\n", repr(r))

# [3] EX (초 단위) 동작
s.sendall(cmd("SET", "k2", "v2", "EX", "10")); recv_line(s)
s.sendall(cmd("TTL", "k2"))
r = recv_line(s)
ok = r.startswith(b":") and 1 <= int(r[1:-2]) <= 10
check("SET EX 10 → TTL 1~10", ok, repr(r))

# [4] TTL: 만료 없는 키 → -1
s.sendall(cmd("SET", "perm", "x")); recv_line(s)
s.sendall(cmd("TTL", "perm"))
r = recv_line(s)
check("영속 키 TTL → :-1", r == b":-1\r\n", repr(r))

# [5] TTL: 없는 키 → -2
s.sendall(cmd("TTL", "ghost"))
r = recv_line(s)
check("없는 키 TTL → :-2", r == b":-2\r\n", repr(r))

# [6] EXPIRE 기존 키 → :1
s.sendall(cmd("EXPIRE", "perm", "10"))
r = recv_line(s)
check("EXPIRE 기존 키 → :1", r == b":1\r\n", repr(r))

# [7] EXPIRE 없는 키 → :0
s.sendall(cmd("EXPIRE", "ghost", "10"))
r = recv_line(s)
check("EXPIRE 없는 키 → :0", r == b":0\r\n", repr(r))

# [8] SET 덮어쓰기가 기존 만료 제거
s.sendall(cmd("SET", "sess2", "a", "PX", "300")); recv_line(s)
s.sendall(cmd("SET", "sess2", "b")); recv_line(s)   # PX 없이 덮어쓰기
time.sleep(0.4)
s.sendall(cmd("GET", "sess2"))
r = recv_bulk(s)
check("SET 덮어쓰기 → 만료 사라짐(영속)", r == b"$1\r\nb\r\n", repr(r))

# [9] TTL이 만료된 키 → -2 (lazy delete 확인)
s.sendall(cmd("SET", "k3", "v", "PX", "200")); recv_line(s)
time.sleep(0.3)
s.sendall(cmd("TTL", "k3"))
r = recv_line(s)
check("만료된 키 TTL → :-2", r == b":-2\r\n", repr(r))

# [10] 회귀: 일반 SET/GET
s.sendall(cmd("SET", "plain", "hello")); recv_line(s)
s.sendall(cmd("GET", "plain"))
r = recv_bulk(s); s.close()
check("회귀: 일반 SET/GET", r == b"$5\r\nhello\r\n", repr(r))

passed = sum(results)
print(f"\n결과: {passed}/{len(results)} 통과")
if passed == len(results):
    print("🎉 Stage 5 로컬 테스트 통과! '다 했어'를 외쳐주세요.")
sys.exit(0 if passed == len(results) else 1)
