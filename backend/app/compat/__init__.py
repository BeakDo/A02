"""Runtime compatibility shims for newer Python versions.

This project currently pins FastAPI to a build that depends on Pydantic v1.
However, Pydantic v1.10 assumes the CPython ``typing.ForwardRef`` private
API from Python 3.12 and earlier.  Python 3.13 changed the signature of the
``ForwardRef._evaluate`` method by introducing a required ``recursive_guard``
keyword-only argument.  Attempting to run the application on Python 3.13 thus
raises ``TypeError: ForwardRef._evaluate() missing 1 required keyword-only
argument`` during FastAPI start-up when the OpenAPI schemas are generated.

To preserve compatibility on Python 3.13 without forking our dependency tree,
we gently patch ``ForwardRef._evaluate`` so that the older Pydantic call-site
continues to work.  The shim is a no-op on older interpreters and is applied as
early as possible by the application entry point.
"""

from __future__ import annotations

import sys
from typing import ForwardRef

__all__ = ["ensure_runtime_compatibility"]


_PATCHED = False


def ensure_runtime_compatibility() -> None:
    """Apply runtime patches required for supported Python versions.

    The function is idempotent and safe to call multiple times.  On Python
    versions prior to 3.13 no action is taken.
    """

    global _PATCHED
    if _PATCHED:
        return

    if sys.version_info < (3, 13):
        return

    original_evaluate = ForwardRef._evaluate

    def _evaluate(self, globalns, localns, recursive_guard=None):  # type: ignore[override]
        if recursive_guard is None:
            recursive_guard = set()
        return original_evaluate(self, globalns, localns, recursive_guard)

    ForwardRef._evaluate = _evaluate  # type: ignore[attr-defined]
    _PATCHED = True

