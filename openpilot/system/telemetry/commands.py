#!/usr/bin/env python3
from typing import Any, Callable

from openpilot.common.params import Params
from openpilot.system.telemetry.protocol import (
  ERR_INVALID,
  ERR_NOT_IMPLEMENTED,
  ERR_NOT_READY,
  ack_message,
  error_message,
)
from openpilot.system.test_sequence.config import STATE_ARMED, STATE_POSITION_SET
from openpilot.system.test_sequence.readiness import (
  MSG_POSITION,
  check_ready,
  get_state,
  trigger_is_set,
)


def handle_command(
  message: dict[str, Any],
  *,
  params: Params,
  get_snapshot: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
  cmd_id = message.get("id")
  if message.get("type") != "command":
    return error_message(cmd_id, ERR_NOT_IMPLEMENTED, "expected command message")

  name = message.get("name")
  if not isinstance(name, str):
    return error_message(cmd_id, ERR_INVALID, "missing command name")

  if name == "set_position":
    return _cmd_set_position(cmd_id, params, get_snapshot)
  if name == "ready":
    return _cmd_ready(cmd_id, params, get_snapshot)

  return error_message(cmd_id, ERR_NOT_IMPLEMENTED, f"command '{name}' is not implemented yet")


def _cmd_set_position(
  cmd_id: str | None,
  params: Params,
  get_snapshot: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
  snap = get_snapshot()
  gps = snap.get("gps", {})
  if not gps.get("hasFix") or gps.get("lat") is None or gps.get("lon") is None:
    return error_message(cmd_id, ERR_INVALID, "GPS fix required to set position")

  lat = float(gps["lat"])
  lon = float(gps["lon"])
  params.put("TestSequenceTriggerLat", lat, block=True)
  params.put("TestSequenceTriggerLon", lon, block=True)
  state = get_state(params)
  if state == "idle":
    params.put("TestSequenceState", STATE_POSITION_SET, block=True)
  return ack_message(str(cmd_id) if cmd_id is not None else "")


def _cmd_ready(
  cmd_id: str | None,
  params: Params,
  get_snapshot: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
  snap = get_snapshot()
  op = snap.get("openpilot", {})
  speed_kph = float(snap.get("speed", {}).get("kph", 0.0))
  state = get_state(params)

  ready, reason = check_ready(
    engaged=bool(op.get("engaged")),
    active=bool(op.get("active")),
    state=state,
    trigger_set=trigger_is_set(state),
    speed_kph=speed_kph,
  )
  if not ready:
    return error_message(cmd_id, ERR_NOT_READY, reason or MSG_POSITION)

  params.put_bool("TestSequenceArmed", True, block=True)
  params.put("TestSequenceState", STATE_ARMED, block=True)
  return ack_message(str(cmd_id) if cmd_id is not None else "")
