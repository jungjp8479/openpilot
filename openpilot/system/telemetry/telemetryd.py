#!/usr/bin/env python3
import argparse
import asyncio
import json
import logging
import mimetypes
import signal
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from openpilot.system.telemetry.deps import ensure_python_deps

ensure_python_deps()

import websockets
from websockets.asyncio.server import serve
from websockets.http11 import Response

from openpilot.common.params import Params
from openpilot.system.telemetry.aggregator import TelemetryAggregator
from openpilot.system.telemetry.commands import handle_command
from openpilot.system.telemetry.protocol import error_message, status_message, telemetry_message

STATIC_DIR = Path(__file__).resolve().parent / "static"
BROADCAST_HZ = 10.0
DEFAULT_PORT = 8080


class TelemetryServer:
  def __init__(self, host: str, port: int) -> None:
    self.host = host
    self.port = port
    self.params = Params()
    self.aggregator = TelemetryAggregator()
    self.clients: set[websockets.ServerConnection] = set()
    self.lock = asyncio.Lock()
    self.last_message: dict = status_message(streaming=False, offroad=True)
    self.logger = logging.getLogger("telemetryd")

  def _expected_token(self) -> str | None:
    token = self.params.get("TelemetryToken")
    return token if token else None

  def _check_token(self, path: str) -> bool:
    expected = self._expected_token()
    if expected is None:
      return True
    query = parse_qs(urlparse(path).query)
    return query.get("token", [None])[0] == expected

  def _static_path(self, route: str) -> Path | None:
    if route == "/":
      route = "index.html"
    elif route.startswith("/static/"):
      route = route[len("/static/"):]
    else:
      route = route.lstrip("/")
    file_path = (STATIC_DIR / route).resolve()
    static_root = STATIC_DIR.resolve()
    if not str(file_path).startswith(str(static_root)):
      return None
    return file_path if file_path.is_file() else None

  async def broadcast(self, message: dict) -> None:
    payload = json.dumps(message)
    async with self.lock:
      self.last_message = message
      dead: list[websockets.ServerConnection] = []
      for client in self.clients:
        try:
          await client.send(payload)
        except websockets.ConnectionClosed:
          dead.append(client)
      for client in dead:
        self.clients.discard(client)

  async def broadcaster(self) -> None:
    interval = 1.0 / BROADCAST_HZ
    while True:
      if self.params.get_bool("IsOffroad"):
        await self.broadcast(status_message(streaming=False, offroad=True))
        await asyncio.sleep(1.0)
      else:
        snapshot = await asyncio.to_thread(self.aggregator.update)
        await self.broadcast(telemetry_message(snapshot))
        await asyncio.sleep(interval)

  async def process_request(self, connection: websockets.ServerConnection, request: websockets.Request):
    route = urlparse(request.path).path

    if not self._check_token(request.path):
      return connection.respond(401, "Unauthorized")

    if route == "/ws":
      return None

    if route == "/api/snapshot":
      if self.params.get_bool("IsOffroad"):
        body = json.dumps(self.aggregator.idle_snapshot()).encode()
      else:
        body = json.dumps(self.aggregator.snapshot()).encode()
      return Response(200, "OK", [("Content-Type", "application/json")], body)

    file_path = self._static_path(route)
    if file_path is None:
      return connection.respond(404, "Not Found")

    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    return Response(200, "OK", [("Content-Type", content_type)], file_path.read_bytes())

  async def ws_handler(self, websocket: websockets.ServerConnection) -> None:
    path = websocket.request.path if websocket.request else ""
    if urlparse(path).path != "/ws":
      await websocket.close(1008, "invalid path")
      return
    if not self._check_token(path):
      await websocket.close(1008, "unauthorized")
      return

    async with self.lock:
      self.clients.add(websocket)
      await websocket.send(json.dumps(self.last_message))
    self.logger.info("client connected (%d total)", len(self.clients))

    try:
      async for raw in websocket:
        try:
          message = json.loads(raw)
        except json.JSONDecodeError:
          await websocket.send(json.dumps(error_message(None, "INVALID", "invalid JSON")))
          continue
        response = handle_command(message)
        await websocket.send(json.dumps(response))
    except websockets.ConnectionClosed:
      pass
    finally:
      async with self.lock:
        self.clients.discard(websocket)
      self.logger.info("client disconnected (%d total)", len(self.clients))

  async def run(self) -> None:
    async with serve(
      self.ws_handler,
      self.host,
      self.port,
      process_request=self.process_request,
    ):
      self.logger.info("listening on http://%s:%d", self.host, self.port)
      await self.broadcaster()


def main() -> None:
  parser = argparse.ArgumentParser(description="openpilot live telemetry server")
  parser.add_argument("--host", default="0.0.0.0")
  parser.add_argument("--port", type=int, default=None)
  args = parser.parse_args()

  logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

  params = Params()
  if args.port is not None:
    port = args.port
  else:
    port_str = params.get("TelemetryServerPort")
    port = int(port_str) if port_str else DEFAULT_PORT

  server = TelemetryServer(args.host, port)
  loop = asyncio.new_event_loop()
  asyncio.set_event_loop(loop)

  broadcaster_task = loop.create_task(server.run())

  def shutdown_handler(*_args) -> None:
    broadcaster_task.cancel()

  try:
    loop.add_signal_handler(signal.SIGINT, shutdown_handler)
    loop.add_signal_handler(signal.SIGTERM, shutdown_handler)
  except NotImplementedError:
    pass

  try:
    loop.run_until_complete(broadcaster_task)
  except asyncio.CancelledError:
    pass
  finally:
    loop.close()


if __name__ == "__main__":
  main()
