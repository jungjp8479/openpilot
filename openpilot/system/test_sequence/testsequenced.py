#!/usr/bin/env python3
import math
import time

from opendbc.car.structs import car

from openpilot.cereal import messaging
from openpilot.common.constants import CV
from openpilot.common.gps import get_gps_location_service
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog
from openpilot.system.test_sequence.config import (
  COUNTDOWN_SECONDS,
  ENTRY_SPEED_MAX_KPH,
  ENTRY_SPEED_MIN_KPH,
  GPS_FRESHNESS_S,
  GPS_MAX_ACCURACY_M,
  STATE_ARMED,
  STATE_COMPLETE,
  STATE_COUNTDOWN,
  STATE_IDLE,
  STATE_POSITION_SET,
  STATE_RUNNING,
  TRIGGER_RADIUS_M,
)
from openpilot.system.test_sequence.geo import haversine_m
from openpilot.system.test_sequence.profile import TestProfileRunner
from openpilot.system.test_sequence.readiness import get_state, trigger_is_set


class TestSequenceController:
  def __init__(self) -> None:
    self.params = Params()
    self.gps_service = get_gps_location_service(self.params)
    self.profile = TestProfileRunner()
    self.countdown_start_mono: float | None = None
    self._cp: car.CarParams | None = None

  def _speed_kph(self, v_ego: float) -> float:
    return float(v_ego * CV.MS_TO_KPH)

  def _gps_ok(self, sm: messaging.SubMaster) -> bool:
    if not sm.valid[self.gps_service]:
      return False
    gps = sm[self.gps_service]
    if not gps.hasFix:
      return False
    age = time.monotonic() - sm.logMonoTime[self.gps_service] / 1e9
    if age > GPS_FRESHNESS_S:
      return False
    if gps.horizontalAccuracy and gps.horizontalAccuracy > GPS_MAX_ACCURACY_M:
      return False
    return True

  def _engaged(self, sm: messaging.SubMaster) -> bool:
    if not sm.valid["selfdriveState"]:
      return False
    ss = sm["selfdriveState"]
    return bool(ss.enabled and ss.active)

  def _long_active(self, sm: messaging.SubMaster) -> bool:
    return sm.valid["carControl"] and bool(sm["carControl"].longActive)

  def _distance_to_trigger(self, sm: messaging.SubMaster) -> float | None:
    if not self._gps_ok(sm):
      return None
    lat = float(sm[self.gps_service].latitude)
    lon = float(sm[self.gps_service].longitude)
    t_lat = float(self.params.get("TestSequenceTriggerLat", return_default=True))
    t_lon = float(self.params.get("TestSequenceTriggerLon", return_default=True))
    return haversine_m(lat, lon, t_lat, t_lon)

  def _in_entry_speed_window(self, sm: messaging.SubMaster) -> bool:
    if not sm.valid["carState"]:
      return False
    kph = self._speed_kph(max(sm["carState"].vEgo, 0.0))
    return ENTRY_SPEED_MIN_KPH <= kph <= ENTRY_SPEED_MAX_KPH

  def _trigger_conditions(self, sm: messaging.SubMaster) -> bool:
    if not self.params.get_bool("TestSequenceArmed"):
      return False
    if not self._engaged(sm) or not self._long_active(sm):
      return False
    if not self._in_entry_speed_window(sm):
      return False
    dist = self._distance_to_trigger(sm)
    return dist is not None and dist <= TRIGGER_RADIUS_M

  def _set_state(self, state: str) -> None:
    self.params.put("TestSequenceState", state, block=True)

  def _clear_countdown(self) -> None:
    self.countdown_start_mono = None
    self.params.put("TestSequenceCountdownSec", -1, block=True)

  def _disengage_reset(self) -> None:
    state = get_state(self.params)
    self.params.put_bool("TestSequenceArmed", False, block=True)
    self.params.put_bool("TestSequenceActive", False, block=True)
    self._clear_countdown()
    self.profile.reset()
    if trigger_is_set(state):
      self._set_state(STATE_POSITION_SET)
    else:
      self._set_state(STATE_IDLE)

  def _update_countdown(self, sm: messaging.SubMaster) -> None:
    if self.countdown_start_mono is None:
      return

    if not self._trigger_conditions(sm):
      self._clear_countdown()
      self._set_state(STATE_ARMED)
      return

    elapsed = time.monotonic() - self.countdown_start_mono
    remaining = max(0, math.ceil(COUNTDOWN_SECONDS - elapsed))
    self.params.put("TestSequenceCountdownSec", remaining, block=True)

    if remaining <= 0:
      self._clear_countdown()
      self._set_state(STATE_RUNNING)
      self.params.put_bool("TestSequenceActive", True, block=True)
      self.profile.reset()

  def update_state_machine(self, sm: messaging.SubMaster) -> None:
    state = get_state(self.params)

    if state in (STATE_ARMED, STATE_COUNTDOWN, STATE_RUNNING) and not self._engaged(sm):
      self._disengage_reset()
      return

    if state == STATE_ARMED and self._trigger_conditions(sm):
      self.countdown_start_mono = time.monotonic()
      self._set_state(STATE_COUNTDOWN)
      self.params.put("TestSequenceCountdownSec", COUNTDOWN_SECONDS, block=True)
      return

    if state == STATE_COUNTDOWN:
      self._update_countdown(sm)
      return

    if state == STATE_RUNNING and self.profile.finished:
      self.params.put_bool("TestSequenceActive", False, block=True)
      self.params.put_bool("TestSequenceArmed", False, block=True)
      self._set_state(STATE_COMPLETE)

  def publish_longitudinal(self, sm: messaging.SubMaster, pm: messaging.PubMaster) -> None:
    state = get_state(self.params)
    if state != STATE_RUNNING or self._cp is None:
      return

    plan_send = messaging.new_message("longitudinalPlan")
    plan_send.valid = sm.all_checks(["carState", "carControl"])
    longitudinal_plan = plan_send.longitudinalPlan

    v_ego = max(sm["carState"].vEgo, 0.0) if sm.valid["carState"] else 0.0
    accel = self.profile.step()

    longitudinal_plan.aTarget = accel
    longitudinal_plan.shouldStop = v_ego < self._cp.vEgoStopping and accel < 1e-2
    longitudinal_plan.allowBrake = True
    longitudinal_plan.allowThrottle = True
    longitudinal_plan.hasLead = True
    longitudinal_plan.speeds = [0.2]

    pm.send("longitudinalPlan", plan_send)


def main() -> None:
  params = Params()
  cloudlog.info("testsequenced waiting for CarParams")
  CP = messaging.log_from_bytes(params.get("CarParams", block=True), car.CarParams)

  gps_service = get_gps_location_service(params)
  sm = messaging.SubMaster(["carState", "carControl", "selfdriveState", gps_service], poll="carState")
  pm = messaging.PubMaster(["longitudinalPlan"])

  controller = TestSequenceController()
  controller._cp = CP

  while True:
    sm.update()
    controller.update_state_machine(sm)
    controller.publish_longitudinal(sm, pm)


if __name__ == "__main__":
  main()
