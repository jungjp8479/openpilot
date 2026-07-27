#!/usr/bin/env python3
from typing import Any

MSG_TELEMETRY = "telemetry"
MSG_COMMAND = "command"
MSG_ACK = "ack"
MSG_ERROR = "error"

ERR_NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
ERR_UNAUTHORIZED = "UNAUTHORIZED"
ERR_INVALID = "INVALID"


def telemetry_message(data: dict[str, Any]) -> dict[str, Any]:
  return {"type": MSG_TELEMETRY, "data": data}


def ack_message(cmd_id: str, ok: bool = True) -> dict[str, Any]:
  return {"type": MSG_ACK, "id": cmd_id, "ok": ok}


def error_message(cmd_id: str | None, code: str, message: str) -> dict[str, Any]:
  msg: dict[str, Any] = {"type": MSG_ERROR, "code": code, "message": message}
  if cmd_id is not None:
    msg["id"] = cmd_id
  return msg
