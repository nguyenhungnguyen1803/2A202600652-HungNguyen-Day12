# Deployment Information

## Public URL
https://ai-agent-production-day12.onrender.com

## Platform
Render

## Test Commands

### 1. Health Check (Liveness Probe)
```bash
curl https://ai-agent-production-day12.onrender.com/health
# Expected Response: {"status": "ok", "uptime_seconds": ..., "version": "1.0.0"}
```

### 2. Readiness Check (Readiness Probe)
```bash
curl https://ai-agent-production-day12.onrender.com/ready
# Expected Response: {"ready": true}
```

### 3. API Test (Requires X-API-Key)
```bash
curl -X POST https://ai-agent-production-day12.onrender.com/ask \
  -H "X-API-Key: my-secret-key-123" \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"Explain Docker in one sentence.\"}"
```

### 4. API Test without Key (Authentication Check)
```bash
curl -X POST https://ai-agent-production-day12.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"Hello\"}"
# Expected Response: {"detail": "Invalid or missing API key. Include header: X-API-Key: <key>"} (Status 401)
```

## Environment Variables Set
- `PORT`: `8000` (được Render inject tự động)
- `AGENT_API_KEY`: `my-secret-key-123` (API key dùng để xác thực)
- `RATE_LIMIT_PER_MINUTE`: `20` (giới hạn số request/phút)
- `DAILY_BUDGET_USD`: `5.0` (ngưỡng chi phí trong ngày)
- `ENVIRONMENT`: `production`

## Screenshots
- Deployment dashboard: [dashboard.png](screenshots/dashboard.png)
- Service running: [running.png](screenshots/running.png)
- Test results: [test.png](screenshots/test.png)
