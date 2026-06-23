#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

cat <<'EOF'

Python environment setup complete.

To use this environment in a new terminal, run:

    source .venv/bin/activate

Then start JupyterLab with:

    jupyter lab
EOF
