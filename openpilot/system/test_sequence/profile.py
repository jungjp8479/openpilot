#!/usr/bin/env python3
import numpy as np

from openpilot.common.realtime import DT_CTRL
from openpilot.system.test_sequence.config import (
  CRUISE_SPEED_KPH,
  DECEL_ACCEL,
  HOLD_DURATION_S,
  HOLD_SPEED_KPH,
)
from openpilot.tools.longitudinal_maneuvers.maneuversd import Action


def _ramp_time(speed_delta_kph: float, accel: float) -> float:
  return (speed_delta_kph / 3.6) / accel


def build_test_actions() -> list[Action]:
  decel_t = _ramp_time(CRUISE_SPEED_KPH - HOLD_SPEED_KPH, DECEL_ACCEL)
  accel_t = _ramp_time(CRUISE_SPEED_KPH - HOLD_SPEED_KPH, DECEL_ACCEL)
  return [
    Action([-DECEL_ACCEL], [decel_t]),
    Action([0.0], [HOLD_DURATION_S]),
    Action([DECEL_ACCEL], [accel_t]),
  ]


class TestProfileRunner:
  def __init__(self) -> None:
    self.actions = build_test_actions()
    self._action_index = 0
    self._action_frames = 0
    self._finished = False

  def reset(self) -> None:
    self._action_index = 0
    self._action_frames = 0
    self._finished = False

  @property
  def finished(self) -> bool:
    return self._finished

  def step(self) -> float:
    if self._finished:
      return 0.0

    action = self.actions[self._action_index]
    accel = float(np.interp(self._action_frames * DT_CTRL, action.time_bp, action.accel_bp))
    self._action_frames += 1

    if self._action_frames > (action.time_bp[-1] / DT_CTRL):
      if self._action_index < len(self.actions) - 1:
        self._action_index += 1
        self._action_frames = 0
      else:
        self._finished = True

    return accel
