#!/usr/bin/env python3
import math


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
  r = 6378137.0
  p1, p2 = math.radians(lat1), math.radians(lat2)
  dlat = math.radians(lat2 - lat1)
  dlon = math.radians(lon2 - lon1)
  a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
  return 2 * r * math.asin(math.sqrt(a))
