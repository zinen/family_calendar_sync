"""Compatibility shim for running Home Assistant's test plugin on Windows."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys


if sys.platform == "win32":
    # The test harness imports Home Assistant's runner but never starts it.
    # Windows has no process resource-limit API, so a stable no-op is enough.
    RLIMIT_NOFILE = 7

    def getrlimit(_resource: int) -> tuple[int, int]:
        """Return a stable synthetic file-descriptor limit."""

        return 2048, 2048

    def setrlimit(_resource: int, _limits: tuple[int, int]) -> None:
        """Accept a resource-limit update without changing process state."""

else:
    _spec = importlib.machinery.PathFinder.find_spec(__name__, sys.path[1:])
    if _spec is None or _spec.loader is None:
        raise ImportError("Unable to load the standard-library resource module")
    _module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_module)
    globals().update(_module.__dict__)
