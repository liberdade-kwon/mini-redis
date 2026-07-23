# 진행 기록

| 날짜 | 스테이지 | 결과 / 리뷰 요약 |
|---|---|---|
| 2026-07-19 | 준비 | 커리큘럼 확정, 스캐폴드 생성. Stage 1 진행 중 |
| 2026-07-20 | Stage 1 ✅ | 클라우드 테스트 6/6 통과. 이중 루프(accept/대화), BufferedReader 줄 단위 프레이밍, use+try로 FIN/RST 모두 처리. 학습: TCP 스트림 무경계, RESP \r\n 프레이밍, FIN vs RST, use 범위 = 리소스 수명 |
| 2026-07-21 | Stage 2 ✅ | 5/5 + Stage 1 회귀 6/6 통과. Selector 이벤트 루프, OP_ACCEPT/OP_READ 분리, attach로 클라이언트별 누적 버퍼, 줄 조립 직접 구현(partial read 대응), 예외 시 해당 클라이언트만 정리. 학습: epoll↔Selector 대응, ready list=명단 vs 데이터, 이벤트 단위 처리와 원자성, select vs poll vs epoll, io_uring completion 모델 |
| 2026-07-22 | Stage 3 ✅ | 8/8 + Stage 2 회귀 5/5 통과. 길이 기반 RESP 파서(Resp.kt 분리), try-parse/커밋 패턴, ECHO bulk 응답, -ERR 에러 응답. 첫 시도의 버그 6개(커밋 누락, -1 미확인, off-by-one, 한 자리 수 가정 등)를 정답과 대조하며 학습. 알려진 한계: non-ASCII 바이트 길이(→Stage 13 전 ByteArray 전환). 학습: 이중 프레이밍 구현, 트랜잭션식 파싱(조회/커밋), ByteBuffer 커서와 partial write 대비 |
