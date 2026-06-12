#!/bin/bash
# Save the port that Render wants us to listen on
RENDER_PORT=${PORT:-8000}

# Start the Node.js frontend server on port 3000
PORT=3000 node /app/frontend/.output/server/index.mjs &

# Start the Python FastAPI backend in the foreground
exec uvicorn app.main:app --host 0.0.0.0 --port $RENDER_PORT --workers 2
