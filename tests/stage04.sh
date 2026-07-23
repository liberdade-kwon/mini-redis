#!/usr/bin/env bash
# Stage 4 자가 테스트 — 서버가 6379(또는 $1 포트)에서 실행 중이어야 함
command -v python3 >/dev/null || { echo "python3가 필요합니다"; exit 1; }
python3 "$(dirname "$0")/stage04.py" "${1:-6379}"
