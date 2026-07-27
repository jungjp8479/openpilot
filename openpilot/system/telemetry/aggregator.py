#!/usr/bin/env python3
import time
from typing import Any

from opendbc.car.common.conversions import Conversions as CV

from openpilot.cereal import messaging
from openpilot.common.gps import get_gps_location_service
from openpilot.common.params import Params


class TelemetryAggregator:
  def __init__(self) -> None:
    self.params = Params()
    self.gps_service = get_gps_location_service(self.params)
    self.services = ["carState", "selfdriveState", self.gps_service]
    self.sm = messaging.SubMaster(self.services)
    self._snapshot: dict[str, Any] = self._empty_snapshot()

  def _empty_snapshot(self) -> dict[str, Any]:
    return {
      "ts": time.time(),
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
    }

  def update(self) -> dict[str, Any]:
    self.sm.update(0)

    snap = self._empty_snapshot()
    snap["ts"] = time.time()

    if self.sm.valid["carState"]:
      cs = self.sm["carState"]
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

    if self.sm.valid["selfdriveState"]:
      ss = self.sm["selfdriveState"]
      snap["openpilot"]["engaged"] = bool(ss.enabled)
      snap["openpilot"]["active"] = bool(ss.active)

    if self.sm.valid[self.gps_service]:
      gps = self.sm[self.gps_service]
      snap["gps"] = {
        "lat": float(gps.latitude) if gps.latitude else None,
        "lon": float(gps.longitude) if gps.longitude else None,
        "accuracyM": float(gps.horizontalAccuracy) if gps.horizontalAccuracy else None,
        "hasFix": bool(gps.hasFix),
        "satellites": int(gps.satelliteCount),
        "bearingDeg": float(gps.bearingDeg) if gps.bearingDeg else None,
      }

    self._snapshot = snap
    return snap

  def snapshot(self) -> dict[str, Any]:
    return self._snapshot
