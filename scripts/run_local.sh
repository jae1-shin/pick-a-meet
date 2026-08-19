#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -x .venv/bin/uvicorn ]]; then
  echo "가상환경이 없습니다. 먼저 python3 -m venv .venv && .venv/bin/pip install -e '.[dev]' 를 실행하세요." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo ".env 파일이 없습니다. .env.example을 복사하고 로컬 설정을 입력하세요." >&2
  exit 1
fi

source .venv/bin/activate
exec uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
