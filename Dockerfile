# ============================================================
# Combined Dockerfile for Backend & Frontend Deployment
# ============================================================

# Stage 1: Build Frontend (Node)
FROM node:20-slim AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install --legacy-peer-deps
COPY frontend/ ./
RUN npm run build

# Stage 2: Build Backend (Python dependencies)
FROM python:3.11-slim AS backend-builder
WORKDIR /build
RUN apt-get update && apt-get install -y gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY 06-lab-complete/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 3: Combined Runtime
FROM python:3.11-slim AS runtime

# Copy Node.js from official image to run the frontend server
COPY --from=node:20-slim /usr/local /usr/local

# Create a non-root user
RUN groupadd -r agent && useradd -r -g agent -d /app agent

WORKDIR /app

# Copy Python packages from builder
COPY --from=backend-builder /root/.local /app/.local

# Copy compiled frontend from frontend builder
COPY --from=frontend-builder /build/frontend/.output /app/frontend/.output

# Copy application code
COPY 06-lab-complete/app/ ./app/
COPY 06-lab-complete/utils/ ./utils/
COPY 06-lab-complete/mock_data/ ./mock_data/

# Copy start script
COPY start.sh ./start.sh
RUN chmod +x ./start.sh

RUN chown -R agent:agent /app

USER agent

ENV PATH=/app/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Health check ( FastAPI backend handles this )
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
    || exit 1

CMD ["./start.sh"]
