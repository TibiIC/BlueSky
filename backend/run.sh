#!/bin/sh
# Start the report backend locally: ./run.sh  (then open http://localhost:8000)
# Creates .venv and installs requirements on first run, or when requirements.txt changes.
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
	python3 -m venv .venv
fi
if [ ! -f .venv/.installed ] || [ requirements.txt -nt .venv/.installed ]; then
	.venv/bin/pip install -q -r requirements.txt
	touch .venv/.installed
fi

if [ -f .env ]; then
	set -a; . ./.env; set +a
fi

exec .venv/bin/uvicorn climate_lens.app:app --reload --port "${PORT:-8000}"
