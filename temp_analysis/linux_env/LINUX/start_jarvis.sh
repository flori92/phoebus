#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
echo "========================================"
echo "   J.A.R.V.I.S — Démarrage Linux"
echo "========================================"
./venv/bin/python main2.py
