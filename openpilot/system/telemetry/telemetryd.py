#!/usr/bin/env python3
import argparse
import json
import logging
import mimetypes
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from openpilot.common.params import Params
from openpilot.system.telemetry.aggregator import TelemetryAggregator
from openpilot.system.telemetry.commands import handle_command
from openpilot.system.telemetry.protocol import error_message, telemetry_message

STATIC_DIR = Path(__file__).resolve().parent / "static"
BROADCAST_HZ = 10.0
DEFAULT_PORT = 8080


class TelemetryState:
  def __init__(self) -> None:
    self.params = Params()
    self.aggregator = TelemetryAggregator()
    self.lock = threading.Lock()
    self.snapshot = self.aggregator.snapshot()
    self.sse_clients: list[threading.Event] = []

  def update_snapshot(self) -> dict:
    with self.lock:
      self.snapshot = self.aggregator.update()
      for event in self.sse_clients:
        event.set()
      return self.snapshot

  def register_sse(self) -> tuple[threading.Event, dict]:
    event = threading.Event()
    with self.lock:
      self.sse_clients.append(event)
      snapshot = self.snapshot
    return event, snapshot

  def unregister_sse(self, event: threading.Event) -> None:
    with self.lock:
      if event in self.sse_clients:
        self.sse_clients.remove(event)

  def expected_token(self) -> str | None:
    token = self.params.get("TelemetryToken")
    return token if token else None

  def check_token(self, path: str) -> bool:
    expected = self.expected_token()
    if expected is None:
      return True
    query = parse_qs(urlparse(path).query)
    return query.get("token", [None])[0] == expected


class TelemetryHandler(BaseHTTPRequestHandler):
  state: TelemetryState

  def log_message(self, format: str, *args: object) -> None:  # noqa: A002
    pass

  def _send_json(self, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode()
    self.send_response(status)
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", str(len(body)))
    self.end_headers()
    self.wfile.write(body)

  def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
    self.send_response(status)
    self.send_header("Content-Type", content_type)
    self.send_header("Content-Length", str(len(body)))
    self.end_headers()
    self.wfile.write(body)

  def _static_path(self, route: str) -> Path | None:
    if route == "/":
      route = "/index.html"
    file_path = (STATIC_DIR / route.lstrip("/")).resolve()
    static_root = STATIC_DIR.resolve()
    if not str(file_path).startswith(str(static_root)):
      return None
    return file_path if file_path.is_file() else None

  def do_GET(self) -> None:
    route = urlparse(self.path).path

    if not self.state.check_token(self.path):
      self._send_bytes(401, b"Unauthorized\n", "text/plain")
      return

    if route == "/api/snapshot":
      with self.state.lock:
        snapshot = self.state.snapshot
      self._send_json(200, snapshot)
      return

    if route == "/api/events":
      self.send_response(200)
      self.send_header("Content-Type", "text/event-stream")
      self.send_header("Cache-Control", "no-cache")
      self.send_header("Connection", "keep-alive")
      self.end_headers()

      event, snapshot = self.state.register_sse()
      try:
        self.wfile.write(f"data: {json.dumps(telemetry_message(snapshot))}\n\n".encode())
        self.wfile.flush()
        while True:
          if not event.wait(timeout=15.0):
            self.wfile.write(b": keepalive\n\n")
            self.wfile.flush()
            continue
          event.clear()
          with self.state.lock:
            payload = telemetry_message(self.state.snapshot)
          self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
          self.wfile.flush()
      except (BrokenPipeError, ConnectionResetError):
        pass
      finally:
        self.state.unregister_sse(event)
      return

    file_path = self._static_path(route)
    if file_path is None:
      self._send_bytes(404, b"Not Found\n", "text/plain")
      return

    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    self._send_bytes(200, file_path.read_bytes(), content_type)

  def do_POST(self) -> None:
    route = urlparse(self.path).path
    if route != "/api/command":
      self._send_bytes(404, b"Not Found\n", "text/plain")
      return

    if not self.state.check_token(self.path):
      self._send_bytes(401, b"Unauthorized\n", "text/plain")
      return

    length = int(self.headers.get("Content-Length", 0))
    try:
      message = json.loads(self.rfile.read(length))
    except json.JSONDecodeError:
      self._send_json(400, error_message(None, "INVALID", "invalid JSON"))
      return

    self._send_json(200, handle_command(message))


class TelemetryHTTPServer(ThreadingHTTPServer):
  daemon_threads = True
  allow_reuse_address = True
  state: TelemetryState


def broadcaster(state: TelemetryState, stop: threading.Event) -> None:
  interval = 1.0 / BROADCAST_HZ
  while not stop.wait(interval):
    state.update_snapshot()


def main() -> None:
  parser = argparse.ArgumentParser(description="openpilot live telemetry server")
  parser.add_argument("--host", default="0.0.0.0")
  parser.add_argument("--port", type=int, default=None)
  args = parser.parse_args()

  logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
  logger = logging.getLogger("telemetryd")

  params = Params()
  if args.port is not None:
    port = args.port
  else:
    port_str = params.get("TelemetryServerPort")
    port = int(port_str) if port_str else DEFAULT_PORT

  state = TelemetryState()
  stop = threading.Event()
  threading.Thread(target=broadcaster, args=(state, stop), name="telemetry-broadcaster", daemon=True).start()

  server = TelemetryHTTPServer((args.host, port), TelemetryHandler)
  server.state = state
  logger.info("listening on http://%s:%d", args.host, port)

  def shutdown_handler(*_args) -> None:
    stop.set()
    server.shutdown()

  signal.signal(signal.SIGINT, shutdown_handler)
  signal.signal(signal.SIGTERM, shutdown_handler)

  try:
    server.serve_forever()
  finally:
    stop.set()
    server.server_close()


if __name__ == "__main__":
  main()
