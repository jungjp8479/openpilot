#!/usr/bin/env python3
import time
from typing import Any

from opendbc.car.common.conversions import Conversions as CV

from openpilot.cereal import messaging
from openpilot.common.gps import get_gps_location_service
from openpilot.common.params import Params
from openpilot.system.test_sequence.readiness import build_test_sequence_status


class TelemetryAggregator:
  def __init__(self) -> None:
    self.params = Params()
    self.gps_service = get_gps_location_service(self.params)
    self.services = ["carState", "selfdriveState", self.gps_service]
    self.sm: messaging.SubMaster | None = None
    self._snapshot: dict[str, Any] = self._empty_snapshot(streaming=False)

  def _ensure_submaster(self) -> messaging.SubMaster:
    if self.sm is None:
      self.sm = messaging.SubMaster(self.services)
    return self.sm

  def _empty_snapshot(self, streaming: bool) -> dict[str, Any]:
    return {
      "ts": time.time(),
      "streaming": streaming,
      "speed": {"mps": 0.0, "kph": 0.0},
      "targetSpeed": {"kph": 0.0},
      "gps": {
        "lat": None,
        "lon": None,
        "accuracyM": None,
        "hasFix": False,
        "satellites": 0,
        "bearingDeg": None,
      },
      "driver": {
        "gas": False,
        "brake": False,
        "steeringAngleDeg": 0.0,
        "steeringPressed": False,
        "leftBlinker": False,
        "rightBlinker": False,
      },
      "openpilot": {
        "engaged": False,
        "active": False,
      },
      "testSequence": {
        "state": "idle",
        "triggerSet": False,
        "triggerLat": None,
        "triggerLon": None,
        "armed": False,
        "ready": False,
        "readyMessage": "Engage openpilot to get ready",
        "distanceM": None,
        "countdownSec": None,
      },
    }

  def update(self) -> dict[str, Any]:
    sm = self._ensure_submaster()
    sm.update(0)

    snap = self._empty_snapshot(streaming=True)
    snap["ts"] = time.time()

    if sm.valid["carState"]:
      cs = sm["carState"]
      snap["speed"]["mps"] = float(cs.vEgo)
      snap["speed"]["kph"] = float(cs.vEgo * CV.MS_TO_KPH)
      snap["targetSpeed"]["kph"] = float(cs.vCruise)
      snap["driver"] = {
        "gas": bool(cs.gasPressed),
        "brake": bool(cs.brakePressed),
        "steeringAngleDeg": float(cs.steeringAngleDeg),
        "steeringPressed": bool(cs.steeringPressed),
        "leftBlinker": bool(cs.leftBlinker),
        "rightBlinker": bool(cs.rightBlinker),
      }

    if sm.valid["selfdriveState"]:
      ss = sm["selfdriveState"]
      snap["openpilot"]["engaged"] = bool(ss.enabled)
      snap["openpilot"]["active"] = bool(ss.active)

    if sm.valid[self.gps_service]:
      gps = sm[self.gps_service]
      snap["gps"] = {
        "lat": float(gps.latitude) if gps.latitude else None,
        "lon": float(gps.longitude) if gps.longitude else None,
        "accuracyM": float(gps.horizontalAccuracy) if gps.horizontalAccuracy else None,
        "hasFix": bool(gps.hasFix),
        "satellites": int(gps.satelliteCount),
        "bearingDeg": float(gps.bearingDeg) if gps.bearingDeg else None,
      }

    snap["testSequence"] = build_test_sequence_status(
      self.params,
      engaged=bool(snap["openpilot"]["engaged"]),
      active=bool(snap["openpilot"]["active"]),
      speed_kph=float(snap["speed"]["kph"]),
      gps_lat=snap["gps"]["lat"],
      gps_lon=snap["gps"]["lon"],
      gps_has_fix=bool(snap["gps"]["hasFix"]),
    )

    self._snapshot = snap
    return snap

  def snapshot(self) -> dict[str, Any]:
    return self._snapshot

  def idle_snapshot(self) -> dict[str, Any]:
    snap = self._empty_snapshot(streaming=False)
    snap["testSequence"] = build_test_sequence_status(
      self.params,
      engaged=False,
      active=False,
      speed_kph=0.0,
      gps_lat=None,
      gps_lon=None,
      gps_has_fix=False,
    )
    return snap
