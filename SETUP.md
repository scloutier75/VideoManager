# Mount the NAS into wsl as read-only
sudo mkdir -p /mnt/v
sudo mount -t drvfs V: /mnt/v -o ro,uid=$(id -u),gid=$(id -g),metadata

# Start the API: 
cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 9000

# Start the UI: 
cd frontend && npm run dev