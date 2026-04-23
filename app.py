"""非Gradio版本：FastAPI + 原生前端。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.agent import AgentConfig, AscendAgent

ROOT = Path(__file__).resolve().parent
KB = ROOT / "data" / "knowledge.json"
WEB_DIR = ROOT / "web"


def load_dotenv_file(path: Path) -> None:
    """轻量读取 .env（不覆盖已存在环境变量）。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv_file(ROOT / ".env")
AGENT = AscendAgent(KB)

app = FastAPI(title="Ascend 310 Agent", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/web", StaticFiles(directory=str(WEB_DIR)), name="web")


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    top_k: int = 6
    temperature: float = 0.2
    mode: str = "balanced"
    enable_remote: bool = True


def _remote_env_status() -> dict[str, bool]:
    return {
        "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "OPENAI_BASE_URL": bool(os.getenv("OPENAI_BASE_URL", "").strip()),
        "OPENAI_MODEL": bool(os.getenv("OPENAI_MODEL", "").strip()),
    }


def _kb_status() -> dict[str, Any]:
    exists = KB.exists()
    return {
        "path": str(KB),
        "exists": exists,
        "size_bytes": KB.stat().st_size if exists else 0,
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(WEB_DIR / "index.html"))


@app.get("/api/health")
def health() -> dict[str, Any]:
    remote_status = _remote_env_status()
    kb_status = _kb_status()
    remote_ready = all(remote_status.values())
    kb_ready = bool(kb_status.get("exists"))
    return {
        "ok": kb_ready,
        "service": "ascend-310-agent",
        "version": "2.0.0",
        "remote_llm_ready": remote_ready,
        "checks": {
            "knowledge_base_ready": kb_ready,
            "remote_llm_env_ready": remote_ready,
        },
        "knowledge_base": kb_status,
        "env": remote_status,
    }


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict[str, Any]:
    msg = req.message.strip()
    if not msg:
        return {"error": "message is empty"}
    history = [m.model_dump() for m in req.history]
    cfg = AgentConfig(
        top_k=max(3, min(20, req.top_k)),
        temperature=max(0.0, min(1.0, req.temperature)),
        mode=req.mode if req.mode in {"fast", "balanced", "deep"} else "balanced",
        enable_remote=req.enable_remote,
    )
    try:
        result = AGENT.chat(msg, history, cfg)
    except Exception:
        return {
            "error": "服务暂时不可用，请检查知识库文件和环境变量后重试。",
            "hint": "可先访问 /api/health 查看详细状态。",
        }
    return {
        "answer": result.answer,
        "intent": result.intent,
        "plan": result.plan,
        "evidences": result.evidences,
        "review_notes": result.review_notes,
        "used_remote": result.used_remote,
        "source_url": result.source_url,
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "7860"))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("app:app", host=host, port=port, reload=False)
