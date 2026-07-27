#!/usr/bin/env python3
from typing import Any

from openpilot.common.params import Params
from openpilot.system.test_sequence.config import (
  ENTRY_SPEED_MAX_KPH,
  ENTRY_SPEED_MIN_KPH,
  LOCKED_STATES,
  STATE_IDLE,
)

MSG_ENGAGE = "Engage openpilot to get ready"
MSG_POSITION = "Set trigger position first"
MSG_SPEED = "Set cruise to 70 km/h to get ready"
MSG_ALREADY_STARTED = "Test already started"


def trigger_is_set(state: str) -> bool:
  return state not in (STATE_IDLE, None, "")


def check_ready(
  *,
  engaged: bool,
  active: bool,
  state: str,
  trigger_set: bool,
  speed_kph: float,
) -> tuple[bool, str | None]:
  if state in LOCKED_STATES:
    return False, MSG_ALREADY_STARTED
  if not (engaged and active):
    return False, MSG_ENGAGE
  if not trigger_set:
    return False, MSG_POSITION
  if not (ENTRY_SPEED_MIN_KPH <= speed_kph <= ENTRY_SPEED_MAX_KPH):
    return False, MSG_SPEED
  return True, None


def get_state(params: Params) -> str:
  state = params.get("TestSequenceState")
  if not state:
    return STATE_IDLE
  if isinstance(state, bytes):
    state = state.decode()
  return str(state)


def build_test_sequence_status(
  params: Params,
  *,
  engaged: bool,
  active: bool,
  speed_kph: float,
  gps_lat: float | None,
  gps_lon: float | None,
  gps_has_fix: bool,
) -> dict[str, Any]:
  state = get_state(params)
  trigger_lat = float(params.get("TestSequenceTriggerLat", return_default=True))
  trigger_lon = float(params.get("TestSequenceTriggerLon", return_default=True))
  trigger_set = trigger_is_set(state)
  armed = params.get_bool("TestSequenceArmed")

  ready, ready_message = check_ready(
    engaged=engaged,
    active=active,
    state=state,
    trigger_set=trigger_set,
    speed_kph=speed_kph,
  )

  distance_m: float | None = None
  if trigger_set and gps_has_fix and gps_lat is not None and gps_lon is not None:
    from openpilot.system.test_sequence.geo import haversine_m
    distance_m = haversine_m(gps_lat, gps_lon, trigger_lat, trigger_lon)

  countdown_raw = params.get("TestSequenceCountdownSec", return_default=True)
  countdown_sec: int | None = None
  if state == "countdown" and countdown_raw is not None and int(countdown_raw) >= 0:
    countdown_sec = int(countdown_raw)

  return {
    "state": state,
    "triggerSet": trigger_set,
    "triggerLat": trigger_lat if trigger_set else None,
    "triggerLon": trigger_lon if trigger_set else None,
    "armed": armed,
    "ready": ready,
    "readyMessage": ready_message,
    "distanceM": distance_m,
    "countdownSec": countdown_sec,
  }
