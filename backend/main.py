import asyncio
import json
import shutil
import sys
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL = "claude-sonnet-4-6"
CLAUDE_BIN = shutil.which("claude") or "claude"


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


def build_command(session_id: Optional[str]) -> list:
    cmd = [
        CLAUDE_BIN,
        "-p",
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--model", MODEL,
        "--dangerously-skip-permissions",
        "--mcp-config", "./mcp.json",
        "--strict-mcp-config",
    ]
    if session_id:
        cmd += ["--resume", session_id]

    if sys.platform == "win32" and CLAUDE_BIN.lower().endswith((".cmd", ".bat")):
        cmd = ["cmd", "/c"] + cmd

    return cmd


def sse_event(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_chat(message: str, session_id: Optional[str]):
    cmd = build_command(session_id)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        yield sse_event({
            "type": "error",
            "error": "claude 命令未找到，请确认已安装 Claude Code CLI 并加入 PATH",
        })
        return

    user_line = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": message}],
        },
    }
    proc.stdin.write((json.dumps(user_line, ensure_ascii=False) + "\n").encode("utf-8"))
    await proc.stdin.drain()
    proc.stdin.close()

    latest_session_id = session_id

    async for raw_line in proc.stdout:
        line = raw_line.decode("utf-8", errors="ignore").strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        sid = data.get("session_id")
        if sid:
            latest_session_id = sid

        yield sse_event(data)

    stderr_bytes = await proc.stderr.read()
    returncode = await proc.wait()

    if returncode != 0 and stderr_bytes:
        yield sse_event({
            "type": "error",
            "error": stderr_bytes.decode("utf-8", errors="ignore").strip(),
        })

    yield sse_event({"type": "done", "session_id": latest_session_id})


@app.post("/chat")
async def chat(req: ChatRequest):
    return StreamingResponse(
        stream_chat(req.message, req.session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
