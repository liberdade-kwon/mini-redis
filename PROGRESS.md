# 진행 기록

| 날짜 | 스테이지 | 결과 / 리뷰 요약 |
|---|---|---|
| 2026-07-19 | 준비 | 커리큘럼 확정, 스캐폴드 생성. Stage 1 진행 중 |
| 2026-07-20 | Stage 1 ✅ | 클라우드 테스트 6/6 통과. 이중 루프(accept/대화), BufferedReader 줄 단위 프레이밍, use+try로 FIN/RST 모두 처리. 학습: TCP 스트림 무경계, RESP \r\n 프레이밍, FIN vs RST, use 범위 = 리소스 수명 |
| 2026-07-21 | Stage 2 ✅ | 5/5 + Stage 1 회귀 6/6 통과. Selector 이벤트 루프, OP_ACCEPT/OP_READ 분리, attach로 클라이언트별 누적 버퍼, 줄 조립 직접 구현(partial read 대응), 예외 시 해당 클라이언트만 정리. 학습: epoll↔Selector 대응, ready list=명단 vs 데이터, 이벤트 단위 처리와 원자성, select vs poll vs epoll, io_uring completion 모델 |
