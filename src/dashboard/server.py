import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parents[2]
REPORTS_DIR = BASE_DIR / "reports"
LIVE_METRICS_PATH = REPORTS_DIR / "live_metrics.jsonl"
FINAL_REPORT_PATH = REPORTS_DIR / "final_report.json"

app = FastAPI(title="ai5g Live Dashboard")
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(str(Path(__file__).resolve().parent / "static" / "index.html"))


@app.get("/api/summary")
async def summary() -> JSONResponse:
    return JSONResponse(_read_json(FINAL_REPORT_PATH))


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket) -> None:
    await websocket.accept()
    offset = 0
    last_size = 0

    try:
        while True:
            if not LIVE_METRICS_PATH.exists():
                await asyncio.sleep(0.5)
                continue

            size = LIVE_METRICS_PATH.stat().st_size
            if size < last_size:
                offset = 0
            last_size = size

            with LIVE_METRICS_PATH.open("r", encoding="utf-8") as handle:
                handle.seek(offset)
                while True:
                    line = handle.readline()
                    if not line:
                        break
                    offset = handle.tell()
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload: Optional[Dict[str, Any]] = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    await websocket.send_json(payload)

            await asyncio.sleep(0.4)
    except WebSocketDisconnect:
        return
