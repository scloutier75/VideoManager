#!/usr/bin/env bash
set -e

echo "=== VideoManager Setup ==="

# ── Backend ────────────────────────────────────────────────────────────────────
echo ""
echo "→ Setting up Python backend..."
cd backend

python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip -q
pip install -r requirements.txt -q

echo "  Backend dependencies installed."
echo ""
echo "  Edit backend/.env to set your database credentials and scan folders."

deactivate
cd ..

# ── Frontend ───────────────────────────────────────────────────────────────────
echo ""
echo "→ Setting up Vue.js frontend..."
cd frontend

npm install

echo "  Frontend dependencies installed."
cd ..

echo ""
echo "=== Setup complete ==="
echo ""
echo "To start the API server:"
echo "  cd backend && source venv/bin/activate && uvicorn app.main:app --reload"
echo ""
echo "To start the frontend:"
echo "  cd frontend && npm run dev"
echo ""
echo "NOTE: ffmpeg must be installed for video analysis."
echo "  Ubuntu/Debian:  sudo apt install ffmpeg"
echo "  Fedora/RHEL:    sudo dnf install ffmpeg"
