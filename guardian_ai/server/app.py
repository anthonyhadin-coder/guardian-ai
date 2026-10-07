from __future__ import annotations
import asyncio
import json
import os
import uuid
from typing import Dict, Optional, Any
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from guardian_ai.agent import GuardianAgent
from guardian_ai.core.analyzer import RepositoryAnalyzer
from guardian_ai.core.models import ExecutionTraceStep, EngineeringReport
from guardian_ai.providers.factory import get_llm_provider

app = FastAPI(title="Guardian AI — Autonomous SWE Agent API")

static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# In-memory storage for active run streams and reports
active_runs: Dict[str, Dict[str, Any]] = {}

class RunRequest(BaseModel):
    repo_path: str
    task: str
    provider: Optional[str] = None
    max_iterations: int = 3

class ScanRequest(BaseModel):
    repo_path: str

@app.get("/api/health")
def health_check():
    return {"status": "ok", "system": "Guardian AI"}

@app.get("/api/demo-repos")
def list_demo_repos():
    demos_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "demo_repos"))
    available = []
    if os.path.exists(demos_path):
        for item in os.listdir(demos_path):
            item_path = os.path.join(demos_path, item)
            if os.path.isdir(item_path):
                available.append({
                    "id": item,
                    "name": item.replace("_", " ").title(),
                    "path": item_path,
                    "default_task": "Fix session timeout enforcement so password reset tokens remain valid for their full expiration window while preserving login session timeout."
                })
    return {"demos": available}

@app.post("/api/scan")
def scan_repository(req: ScanRequest):
    repo_path = os.path.abspath(req.repo_path)
    if not os.path.isdir(repo_path):
        raise HTTPException(status_code=400, detail=f"Directory '{repo_path}' does not exist")
    analyzer = RepositoryAnalyzer(repo_path)
    metadata = analyzer.analyze()
    return metadata.model_dump()

@app.post("/api/run")
async def start_agent_run(req: RunRequest, background_tasks: BackgroundTasks):
    repo_path = os.path.abspath(req.repo_path)
    if not os.path.isdir(repo_path):
        raise HTTPException(status_code=400, detail=f"Directory '{repo_path}' does not exist")

    run_id = str(uuid.uuid4())
    event_queue: asyncio.Queue = asyncio.Queue()
    active_runs[run_id] = {
        "queue": event_queue,
        "report": None,
        "status": "RUNNING"
    }

    def on_step_callback(step: ExecutionTraceStep):
        # Synchronously put into queue for async consumer
        asyncio.run_coroutine_threadsafe(
            event_queue.put({"type": "step", "data": step.model_dump()}),
            loop
        )

    loop = asyncio.get_event_loop()

    def run_agent_worker():
        try:
            provider = get_llm_provider(req.provider)
            agent = GuardianAgent(
                repo_path=repo_path,
                provider=provider,
                max_repair_iterations=req.max_iterations,
                event_callback=on_step_callback
            )
            report = agent.run(req.task)
            active_runs[run_id]["report"] = report.model_dump()
            active_runs[run_id]["status"] = "COMPLETED"
            asyncio.run_coroutine_threadsafe(
                event_queue.put({"type": "complete", "data": report.model_dump()}),
                loop
            )
        except Exception as e:
            active_runs[run_id]["status"] = "FAILED"
            asyncio.run_coroutine_threadsafe(
                event_queue.put({"type": "error", "error": str(e)}),
                loop
            )

    background_tasks.add_task(run_agent_worker)
    return {"run_id": run_id, "status": "STARTED"}

@app.get("/api/stream/{run_id}")
async def stream_agent_progress(run_id: str):
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail="Run ID not found")

    queue = active_runs[run_id]["queue"]

    async def event_generator():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("type") in ("complete", "error"):
                    break
            except asyncio.TimeoutError:
                # Keepalive ping
                yield "data: {\"type\": \"ping\"}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/", response_class=HTMLResponse)
def index_view():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Guardian AI Web Dashboard</h1>"
