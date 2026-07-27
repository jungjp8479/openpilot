#!/usr/bin/env python3
from typing import Any

from openpilot.system.telemetry.protocol import ERR_NOT_IMPLEMENTED, error_message


def handle_command(message: dict[str, Any]) -> dict[str, Any]:
  cmd_id = message.get("id")
  if message.get("type") != "command":
    return error_message(cmd_id, ERR_NOT_IMPLEMENTED, "expected command message")

  name = message.get("name")
  if not isinstance(name, str):
    return error_message(cmd_id, ERR_NOT_IMPLEMENTED, "missing command name")

  return error_message(cmd_id, ERR_NOT_IMPLEMENTED, f"command '{name}' is not implemented yet")
