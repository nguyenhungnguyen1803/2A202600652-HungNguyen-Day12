# Deployment Information

## Public URL
https://your-agent.up.railway.app

## Platform
Railway

## Test Commands

### 1. Health Check (Liveness Probe)
```bash
curl https://your-agent.up.railway.app/health
# Expected Response: {"status": "ok", "uptime_seconds": ..., "version": "1.0.0"}
```

### 2. Readiness Check (Readiness Probe)
```bash
curl https://your-agent.up.railway.app/ready
# Expected Response: {"ready": true}
```

### 3. API Test (Requires X-API-Key)
```bash
curl -X POST https://your-agent.up.railway.app/ask \
  -H "X-API-Key: your-secret-api-key-here" \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"Explain Docker in one sentence.\"}"
```

### 4. API Test without Key (Authentication Check)
```bash
curl -X POST https://your-agent.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"Hello\"}"
# Expected Response: {"detail": "Invalid or missing API key. Include header: X-API-Key: <key>"} (Status 401)
```

## Environment Variables Set
- `PORT`: `8000` (được Railway inject tự động hoặc set thủ công)
- `REDIS_URL`: `redis://...` (được Railway tự sinh khi thêm Redis service)
- `AGENT_API_KEY`: `your-secret-api-key-here` (API key dùng để xác thực)
- `RATE_LIMIT_PER_MINUTE`: `20` (giới hạn số request/phút)
- `DAILY_BUDGET_USD`: `5.0` (ngưỡng chi phí trong ngày)
- `ENVIRONMENT`: `production`

## Screenshots
- Deployment dashboard: [dashboard.png](screenshots/dashboard.png)
- Service running: [running.png](screenshots/running.png)
- Test results: [test.png](screenshots/test.png)
