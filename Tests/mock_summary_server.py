"""Local SSE fixture. Uses only synthetic text and a caller-provided data root."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import sys
import time


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body["stream"] is True
        prompt = body["messages"][0]["content"]
        if "__full_input__" in prompt:
            transcript = body["messages"][1]["content"]
            assert len(transcript) > 60000 and transcript.endswith("结尾不可丢失"), "input was silently truncated"
        if "__error__" in prompt:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": "test key rejected"}}).encode())
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json" if "__json__" in prompt else "text/event-stream")
        self.end_headers()
        if "__json__" in prompt:
            self.wfile.write(json.dumps({"choices": [{"message": {"content": "# 普通 JSON\n\n兼容输出。"}, "finish_reason": "length" if "__length__" in prompt else "stop"}]}, ensure_ascii=False).encode())
            return
        if "__old__" in prompt:
            pieces, delay = ["# 旧请求", "\n\n过期内容。"], 0.8
        elif "__new__" in prompt:
            pieces, delay = ["# 新请求", "\n\n替换成功。"], 0.1
        elif "__full_input__" in prompt:
            pieces, delay = ["# 全文已收到"], 0.1
        else:
            pieces, delay = ["# 总结", "\n\n- **模块**", "\n  - **子类**", "\n    - 具体说明"], 0.2
        try:
            for piece in pieces:
                payload = ("data: " + json.dumps({"choices": [{"delta": {"content": piece}}]}, ensure_ascii=False) + "\n\n").encode()
                # Split a UTF-8 character over socket writes, as a real network can.
                split = next(i for i, byte in enumerate(payload) if byte > 127) + 1
                self.wfile.write(payload[:split])
                self.wfile.flush()
                self.wfile.write(payload[split:])
                self.wfile.flush()
                time.sleep(delay)
            if "__disconnect__" in prompt:
                return
            if "__stream_error__" in prompt:
                self.wfile.write(b'data: {"error":{"message":"stream interrupted"}}\n\n')
            if "__filter__" in prompt:
                self.wfile.write(b'data: {"choices":[{"delta":{},"finish_reason":"content_filter"}]}\n\n')
            if "__length__" in prompt:
                self.wfile.write(b'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\n')
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


root = Path(sys.argv[1]) / "data"
root.mkdir(parents=True, exist_ok=True)
server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
(root / "config.env").write_text(
    f"OPENROUTER_API_KEY=test-only\nOPENROUTER_BASE=http://127.0.0.1:{server.server_port}/v1\nSUMMARY_MODEL=test-stream\n"
)
(root / "server-ready").touch()
server.serve_forever()
