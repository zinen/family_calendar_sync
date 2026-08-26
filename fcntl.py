"""Compatibility shim for running Home Assistant's test plugin on Windows."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import sys


if sys.platform == "win32":
    # Home Assistant's test plugin imports ``homeassistant.runner``, which
    # imports the Unix-only ``fcntl`` module even though these tests never
    # start Home Assistant's process runner. Its only required lock API can be
    # a no-op for the in-process test harness.
    LOCK_EX = 2
    LOCK_NB = 4

    def flock(*_args: object) -> None:
        """Provide the file-lock API expected by Home Assistant's runner."""

else:
    # This file shadows the standard-library extension on Unix when pytest is
    # run from the repository root. Load and re-export that real extension so
    # Unix test runs retain normal file-locking behavior.
    _spec = importlib.machinery.PathFinder.find_spec(__name__, sys.path[1:])
    if _spec is None or _spec.loader is None:
        raise ImportError("Unable to load the standard-library fcntl module")
    _module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_module)
    globals().update(_module.__dict__)
