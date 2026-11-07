#!/bin/sh
# Serve the SBTN review page locally: ./run.sh [notebook]  (then open http://localhost:8300)
# Re-exports the page from the notebook on every start. Needs only python3.
set -e
cd "$(dirname "$0")"
python3 export.py "$@"
echo "SBTN review at http://localhost:${PORT:-8300}"
exec python3 -m http.server "${PORT:-8300}" --bind 127.0.0.1 --directory site
