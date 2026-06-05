from __future__ import annotations

import base64
import json
import os
import socket
import struct
import time
import urllib.request
from dataclasses import dataclass
from typing import Any


class CdpError(RuntimeError):
    pass


@dataclass
class ChromeTarget:
    id: str
    title: str
    url: str
    websocket_url: str


class CdpClient:
    def __init__(self, cdp_url: str = "http://127.0.0.1:9222", target_url_contains: str = "koreanair.com"):
        self.cdp_url = cdp_url.rstrip("/")
        self.target_url_contains = target_url_contains
        self.sock: socket.socket | None = None
        self.next_id = 1

    def list_targets(self) -> list[ChromeTarget]:
        with urllib.request.urlopen(self.cdp_url + "/json/list", timeout=5) as r:
            pages = json.loads(r.read().decode())
        targets = []
        for p in pages:
            if p.get("type") != "page" or not p.get("webSocketDebuggerUrl"):
                continue
            targets.append(ChromeTarget(p.get("id", ""), p.get("title", ""), p.get("url", ""), p["webSocketDebuggerUrl"]))
        return targets

    def pick_target(self) -> ChromeTarget:
        targets = self.list_targets()
        for t in targets:
            if self.target_url_contains in t.url:
                return t
        if targets:
            return targets[0]
        raise CdpError("No Chrome page target found. Is Chrome running with --remote-debugging-port?")

    def connect(self) -> ChromeTarget:
        target = self.pick_target()
        self.sock = self._ws_connect(target.websocket_url)
        self.call("Runtime.enable")
        self.call("Page.enable")
        return target

    def close(self) -> None:
        if self.sock:
            self.sock.close()
            self.sock = None

    def call(self, method: str, params: dict[str, Any] | None = None, timeout: float = 15) -> dict[str, Any]:
        if not self.sock:
            raise CdpError("CDP socket is not connected")
        msg_id = self.next_id
        self.next_id += 1
        self._ws_send({"id": msg_id, "method": method, "params": params or {}})
        end = time.time() + timeout
        while time.time() < end:
            msg = self._ws_recv()
            if not msg:
                continue
            if msg.get("id") == msg_id:
                if "error" in msg:
                    raise CdpError(f"{method} failed: {msg['error']}")
                return msg
        raise TimeoutError(method)

    def evaluate(self, expression: str, timeout: float = 30) -> Any:
        res = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
                "timeout": int(timeout * 1000),
            },
            timeout=timeout + 5,
        )
        result = res.get("result", {}).get("result", {})
        if result.get("subtype") == "error" or "exceptionDetails" in res.get("result", {}):
            raise CdpError(json.dumps(res, ensure_ascii=False)[:2000])
        return result.get("value")

    def ensure_koreanair_page(self) -> None:
        value = self.evaluate("location.href")
        if not isinstance(value, str) or "koreanair.com" not in value:
            self.call("Page.navigate", {"url": "https://www.koreanair.com/"})
            time.sleep(3)

    def _ws_connect(self, wsurl: str) -> socket.socket:
        if not wsurl.startswith("ws://"):
            raise CdpError(f"Unsupported websocket URL: {wsurl}")
        rest = wsurl[5:]
        hostport, path = rest.split("/", 1)
        path = "/" + path
        host, port_s = hostport.split(":", 1) if ":" in hostport else (hostport, "80")
        sock = socket.create_connection((host, int(port_s)), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {hostport}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += sock.recv(4096)
        if b" 101 " not in resp.split(b"\r\n", 1)[0]:
            raise CdpError("WebSocket handshake failed: " + resp[:200].decode(errors="ignore"))
        sock.settimeout(None)
        return sock

    def _ws_send(self, obj: dict[str, Any]) -> None:
        assert self.sock is not None
        data = json.dumps(obj, separators=(",", ":")).encode()
        mask = os.urandom(4)
        n = len(data)
        if n < 126:
            hdr = bytes([0x81, 0x80 | n])
        elif n < 65536:
            hdr = bytes([0x81, 0x80 | 126]) + struct.pack("!H", n)
        else:
            hdr = bytes([0x81, 0x80 | 127]) + struct.pack("!Q", n)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.sock.sendall(hdr + mask + masked)

    def _recvn(self, n: int) -> bytes:
        assert self.sock is not None
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise EOFError
            buf += chunk
        return buf

    def _ws_recv(self) -> dict[str, Any] | None:
        b1, b2 = self._recvn(2)
        opcode = b1 & 0x0F
        masked = b2 & 0x80
        n = b2 & 0x7F
        if n == 126:
            n = struct.unpack("!H", self._recvn(2))[0]
        elif n == 127:
            n = struct.unpack("!Q", self._recvn(8))[0]
        mask = self._recvn(4) if masked else b""
        data = self._recvn(n) if n else b""
        if masked:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        if opcode == 8:
            raise EOFError
        if opcode in (9, 10) or opcode != 1:
            return None
        return json.loads(data.decode(errors="replace"))
