#!/usr/bin/env python3
import os
import subprocess
import sys

from openpilot.common.basedir import BASEDIR

DEPS_DIR = os.path.join(BASEDIR, "python_deps")
MARKER = os.path.join(DEPS_DIR, ".websockets_installed")


def setup_python_deps() -> None:
  if DEPS_DIR not in sys.path:
    sys.path.insert(0, DEPS_DIR)


def install_python_deps() -> None:
  os.makedirs(DEPS_DIR, exist_ok=True)
  if os.path.exists(MARKER):
    return

  subprocess.check_call([
    sys.executable, "-m", "pip", "install",
    "websockets", "--target", DEPS_DIR,
  ])
  with open(MARKER, "w", encoding="utf-8") as f:
    f.write("ok\n")


def ensure_python_deps() -> None:
  setup_python_deps()
  try:
    import websockets  # noqa: F401
  except ImportError:
    install_python_deps()
    setup_python_deps()
