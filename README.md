# xy

第一步：最小可用的 Claude Code 网页对话壳子。

## 前置条件

- 已安装 Python 3.9+
- 已安装并登录 [Claude Code CLI](https://code.claude.com)，命令行输入 `claude --version` 能正常输出

## 后端

```bash
cd backend
pip install -r ../requirements.txt
uvicorn main:app --reload --port 8000
```

后端只有一个接口 `POST /chat`：

- 请求体：`{"message": "你好", "session_id": null}`
- 内部会启动 `claude -p --input-format stream-json --output-format stream-json --verbose --include-partial-messages --model claude-sonnet-4-6 --dangerously-skip-permissions` 子进程
- 如果 `session_id` 不为空，会额外带上 `--resume <session_id>` 复用会话
- 响应是 SSE（`text/event-stream`），把 claude 子进程 stdout 的每一行 JSON 原样转发，最后追加一条 `{"type": "done", "session_id": "..."}`

## 前端

直接用浏览器打开 `frontend/index.html` 即可（双击或右键“用浏览器打开”）。

- 输入框 + 发送按钮，回车也可发送
- 消息列表：用户在右，AI 在左，流式打字机效果
- `session_id` 存在 `localStorage`（key: `xy_session_id`），刷新页面后继续复用同一个会话

## 测试 /chat 接口

后端启动后，用 curl 测试（Windows PowerShell 用 `curl.exe`）：

```bash
curl.exe -N -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" -d "{\"message\": \"你好\", \"session_id\": null}"
```

正常情况下会看到一行行 `data: {...}` 的 SSE 输出，最后一行是 `data: {"type": "done", "session_id": "xxxx-xxxx"}`。把这个 `session_id` 填到下一次请求里可以验证 `--resume` 是否生效。

## 备注

`--input-format stream-json` 的输入/输出协议 Anthropic 官方没有完整公开文档，`backend/main.py` 里对 stdout 的处理是尽量原样转发给前端，前端按已知的事件类型（`stream_event` 里的 `content_block_delta`、最终的 `assistant` 消息、`error`、`done`）做了兼容解析。如果实际跑起来发现字段对不上，把真实收到的 JSON 行发给我，我再调整解析逻辑。
