#!/usr/bin/env python3
"""Stage 2 로컬 자가 테스트 — 동시성 검증 포함"""
import socket, struct, sys, time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 6379
PING = b"*1\r\n$4\r\nPING\r\n"
PONG = b"+PONG\r\n"
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

# [1] 핵심: 동시 접속 2명 교차 응답 (Stage 1에서는 불가능했던 것)
a, b = conn(), conn()
b.sendall(PING)                       # 나중에 접속한 b가 먼저 보냄
rb = recv_exact(b, 7)
a.sendall(PING)                       # a도 응답받아야 함
ra = recv_exact(a, 7)
b.sendall(PING)                       # b 한 번 더
rb2 = recv_exact(b, 7)
a.close(); b.close()
check("동시 2명 교차 PING/PONG", ra == PONG and rb == PONG and rb2 == PONG,
      f"a={ra!r} b1={rb!r} b2={rb2!r}")

# [2] 동시 10명 전원 응답
socks = [conn() for _ in range(10)]
for s in socks: s.sendall(PING)
oks = [recv_exact(s, 7) == PONG for s in socks]
for s in socks: s.close()
check("동시 10명 전원 PONG", all(oks), f"{oks.count(True)}/10")

# [3] 파이프라인 3연속 (Stage 1 동작 보존)
s = conn(); s.sendall(PING * 3)
r = recv_exact(s, 21); s.close()
check("파이프라인 3연속", r == PONG * 3, repr(r))

# [4] 쪼개진 패킷 (partial read 직접 처리 확인)
s = conn()
s.sendall(b"*1\r\n$4\r\nPI"); time.sleep(0.3); s.sendall(b"NG\r\n")
r = recv_exact(s, 7); s.close()
check("쪼개진 패킷", r == PONG, repr(r))

# [5] 한 명의 RST가 다른 클라이언트에 영향 없는지
a, b = conn(), conn()
a.sendall(PING); recv_exact(a, 7)
a.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
a.close()  # a가 험하게 퇴장
time.sleep(0.3)
b.sendall(PING)
r = recv_exact(b, 7); b.close()
check("RST 후 다른 클라이언트 정상 + 서버 생존", r == PONG, repr(r))

passed = sum(results)
print(f"\n결과: {passed}/{len(results)} 통과")
if passed == len(results):
    print("🎉 Stage 2 로컬 테스트 통과! (싱글 스레드 여부는 정식 리뷰에서 확인합니다)")
sys.exit(0 if passed == len(results) else 1)
