"""
Production AI Agent — Kết hợp tất cả Day 12 concepts

Checklist:
  ✅ Config từ environment (12-factor)
  ✅ Structured JSON logging
  ✅ API Key authentication
  ✅ Rate limiting
  ✅ Cost guard
  ✅ Input validation (Pydantic)
  ✅ Health check + Readiness probe
  ✅ Graceful shutdown
  ✅ Security headers
  ✅ CORS
  ✅ Error handling
"""
import os
import sys
# Ngăn chặn việc shadow thư mục 'utils' bởi thư viện hệ thống
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv()
import time
import signal
import logging
import json
from datetime import datetime, timezone
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Security, Depends, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Generator, Optional, List, Dict, Any
import uvicorn

from app.config import settings

# Mock LLM (thay bằng OpenAI/Anthropic khi có API key)
from utils.mock_llm import ask as llm_ask

# Import agent functionalities từ dự án Day 6
from app.agent import (
    run_safety_guardrails,
    execute_mock_agent,
    OpenAIProvider,
    OpenAICompatibleProvider,
    GeminiProvider,
    VaccineAssistantAgent
)

# ─────────────────────────────────────────────────────────
# Logging — JSON structured
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_request_count = 0
_error_count = 0

# ─────────────────────────────────────────────────────────
# Simple In-memory Rate Limiter
# ─────────────────────────────────────────────────────────
_rate_windows: dict[str, deque] = defaultdict(deque)

def check_rate_limit(key: str):
    now = time.time()
    window = _rate_windows[key]
    while window and window[0] < now - 60:
        window.popleft()
    if len(window) >= settings.rate_limit_per_minute:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} req/min",
            headers={"Retry-After": "60"},
        )
    window.append(now)

# ─────────────────────────────────────────────────────────
# Simple Cost Guard
# ─────────────────────────────────────────────────────────
_daily_cost = 0.0
_cost_reset_day = time.strftime("%Y-%m-%d")

def check_and_record_cost(input_tokens: int, output_tokens: int):
    global _daily_cost, _cost_reset_day
    today = time.strftime("%Y-%m-%d")
    if today != _cost_reset_day:
        _daily_cost = 0.0
        _cost_reset_day = today
    if _daily_cost >= settings.daily_budget_usd:
        raise HTTPException(503, "Daily budget exhausted. Try tomorrow.")
    cost = (input_tokens / 1000) * 0.00015 + (output_tokens / 1000) * 0.0006
    _daily_cost += cost

# ─────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key or api_key != settings.agent_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header: X-API-Key: <key>",
        )
    return api_key

# ─────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }))
    time.sleep(0.1)  # simulate init
    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))

    yield

    _is_ready = False
    logger.info(json.dumps({"event": "shutdown"}))

# ─────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if "server" in response.headers:
            del response.headers["server"]
        duration = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration,
        }))
        return response
    except Exception as e:
        _error_count += 1
        raise

# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000,
                          description="Your question for the agent")

class AskResponse(BaseModel):
    question: str
    answer: str
    model: str
    timestamp: str

class ChatMessage(BaseModel):
    from_role: str = "user"
    text: str

    class Config:
        fields = {'from_role': 'from'}
        populate_by_name = True

class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]]

class CallbackRequest(BaseModel):
    name: str
    phone: str
    details: Optional[str] = ""

# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────

@app.get("/api/info", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "endpoints": {
            "ask": "POST /ask (requires X-API-Key)",
            "health": "GET /health",
            "ready": "GET /ready",
        },
    }


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(
    body: AskRequest,
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """
    Send a question to the AI agent.

    **Authentication:** Include header `X-API-Key: <your-key>`
    """
    # Rate limit per API key
    check_rate_limit(_key[:8])  # use first 8 chars as key bucket

    # Budget check
    input_tokens = len(body.question.split()) * 2
    check_and_record_cost(input_tokens, 0)

    logger.info(json.dumps({
        "event": "agent_call",
        "q_len": len(body.question),
        "client": str(request.client.host) if request.client else "unknown",
    }))

    answer = llm_ask(body.question)

    output_tokens = len(answer.split()) * 2
    check_and_record_cost(0, output_tokens)

    return AskResponse(
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ─────────────────────────────────────────────────────────
# Day 6 Vaccine Assistant Agent Helper Functions & Endpoints
# ─────────────────────────────────────────────────────────

def stream_mock_agent(history: List[Dict[str, Any]]) -> Generator[Dict[str, Any], None, None]:
    result = execute_mock_agent(history)
    text = result.get("text", "")
    yield {"type": "text", "content": text}
    if result.get("tool_data"):
        yield {"type": "tool_data", "content": result["tool_data"]}

def chat_stream_generator(messages: List[Dict[str, Any]], api_key: Optional[str]):
    user_messages = [m for m in messages if m.get("from") == "user"]
    if not messages or not user_messages:
        payload = {
            "type": "text",
            "content": "Chào mừng Anh/Chị đến với Tiêm chủng Long Châu. Bác sĩ Long Châu có thể giúp gì cho mình ạ?"
        }
        yield json.dumps(payload, ensure_ascii=False) + "\n"
        return

    last_user_message = user_messages[-1].get("text", "")
    logger.info(f"Received message from user: {last_user_message}")

    # 1. Run Safety Guardrails Check on user message
    safety_result = run_safety_guardrails(last_user_message, api_key)
    
    if safety_result.get("is_dangerous"):
        logger.warning(f"Safety red flags triggered for query: {last_user_message}")
        payload = {
            "type": "safety_triggered",
            "content": True,
            "text": safety_result["warning_message"],
            "tool_data": {
                "safety_escalation": True,
                "type": safety_result["type"]
            }
        }
        yield json.dumps(payload, ensure_ascii=False) + "\n"
        return

    # 2. Run agent execution
    if api_key:
        logger.info("Executing AI Agent Stream Loop...")
        if os.getenv("OPENAI_API_KEY"):
            provider = OpenAIProvider(
                model_name=os.getenv("OPENAI_MODEL_NAME", "gpt-4o-mini"),
                api_key=os.getenv("OPENAI_API_KEY")
            )
        elif os.getenv("COMPATIBLE_API_KEY"):
            provider = OpenAICompatibleProvider(
                model_name=os.getenv("COMPATIBLE_MODEL_NAME", "mimo-v2.5-pro"),
                base_url=os.getenv("COMPATIBLE_BASE_URL", "http://localhost:8000/v1"),
                api_key=os.getenv("COMPATIBLE_API_KEY")
            )
        elif os.getenv("OPENROUTER_API_KEY"):
            provider = OpenAICompatibleProvider(
                model_name=os.getenv("OPENROUTER_MODEL_NAME", "google/gemini-2.5-flash"),
                base_url="https://openrouter.ai/api/v1",
                api_key=os.getenv("OPENROUTER_API_KEY")
            )
        else:
            provider = GeminiProvider(
                model_name="gemini-2.5-flash",
                api_key=api_key
            )
        
        agent = VaccineAssistantAgent(llm=provider)
        stream_gen = agent.run_stream(messages)
    else:
        logger.info("No API_KEY found. Executing Mock Fallback Agent Stream...")
        stream_gen = stream_mock_agent(messages)
        
    for chunk in stream_gen:
        yield json.dumps(chunk, ensure_ascii=False) + "\n"


@app.get("/api/health", tags=["VaccineAssistant"])
async def health_check_day6():
    api_key = (
        os.getenv("OPENAI_API_KEY") 
        or os.getenv("COMPATIBLE_API_KEY") 
        or os.getenv("OPENROUTER_API_KEY") 
        or os.getenv("GEMINI_API_KEY")
    )
    mode = "Mock Fallback Agent (Out of the box mode)"
    if os.getenv("OPENAI_API_KEY"):
        mode = "OpenAI API Agent"
    elif os.getenv("COMPATIBLE_API_KEY"):
        mode = "OpenAI Compatible Agent"
    elif os.getenv("OPENROUTER_API_KEY"):
        mode = "OpenRouter AI Agent"
    elif os.getenv("GEMINI_API_KEY"):
        mode = "Gemini API Agent"
    return {
        "status": "healthy",
        "has_api_key": bool(api_key),
        "mode": mode
    }


@app.post("/api/chat", tags=["VaccineAssistant"])
def chat_endpoint(payload: ChatRequest):
    messages = payload.messages
    api_key = (
        os.getenv("OPENAI_API_KEY") 
        or os.getenv("COMPATIBLE_API_KEY") 
        or os.getenv("OPENROUTER_API_KEY") 
        or os.getenv("GEMINI_API_KEY")
    )
    return StreamingResponse(
        chat_stream_generator(messages, api_key),
        media_type="application/x-ndjson"
    )


@app.post("/api/callback", tags=["VaccineAssistant"])
async def register_callback(payload: CallbackRequest):
    logger.info(f"Registered pharmacist callback request: Name={payload.name}, Phone={payload.phone}, Details={payload.details}")
    return {
        "status": "success",
        "message": f"Dạ, bác sĩ trực ca đã nhận được thông tin. Hotline hỗ trợ 1800 6928 sẽ liên hệ đến số {payload.phone} trong 15 phút tới để tư vấn trực tiếp cho Anh/Chị {payload.name}."
    }



@app.get("/health", tags=["Operations"])
def health():
    """Liveness probe. Platform restarts container if this fails."""
    status = "ok"
    checks = {"llm": "mock" if not settings.openai_api_key else "openai"}
    return {
        "status": status,
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    """Readiness probe. Load balancer stops routing here if not ready."""
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    return {"ready": True}


@app.get("/metrics", tags=["Operations"])
def metrics(_key: str = Depends(verify_api_key)):
    """Basic metrics (protected)."""
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "daily_cost_usd": round(_daily_cost, 4),
        "daily_budget_usd": settings.daily_budget_usd,
        "budget_used_pct": round(_daily_cost / settings.daily_budget_usd * 100, 1),
    }


# ─────────────────────────────────────────────────────────
# Graceful Shutdown
# ─────────────────────────────────────────────────────────
def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))

signal.signal(signal.SIGTERM, _handle_signal)


# ─────────────────────────────────────────────────────────
# Frontend Proxy Route
# ─────────────────────────────────────────────────────────
import httpx

async_client = httpx.AsyncClient(base_url="http://127.0.0.1:3000")

@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def catch_all_proxy(request: Request, path_name: str):
    url = httpx.URL(path=request.url.path, query=request.url.query.encode("utf-8"))
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    body = await request.body()
    
    req = async_client.build_request(
        method=request.method,
        url=url,
        headers=headers,
        content=body,
    )
    
    try:
        rp_resp = await async_client.send(req, stream=True)
        return StreamingResponse(
            rp_resp.iter_raw(),
            status_code=rp_resp.status_code,
            headers=dict(rp_resp.headers),
        )
    except Exception as e:
        logger.error(f"Failed to proxy to frontend: {e}")
        raise HTTPException(status_code=502, detail="Frontend is currently starting up or offline. Please refresh in a moment.")


if __name__ == "__main__":
    logger.info(f"Starting {settings.app_name} on {settings.host}:{settings.port}")
    logger.info(f"API Key: {settings.agent_api_key[:4]}****")
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
