"""
Compatibility layer.

The shared thermoelectric schema now lives in evaluation/schema.py (the
method-independent contract). This module re-exports it so existing imports
(`from .schema import CANDIDATE_FIELDS`, ...) keep working unchanged.
"""

import sys
from pathlib import Path

try:
    from evaluation.schema import *  # noqa: F401,F403
    from evaluation.schema import (  # explicit names used inside regex_extractor
        CANDIDATE_FIELDS, CANONICAL_UNITS, GOLD_FIELDS, PROPERTIES,
        TE_RECORD_FIELDS, TE_SCHEMA,
    )
except ModuleNotFoundError:
    # Run from outside the project root: add the project root to the path.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from evaluation.schema import *  # noqa: F401,F403
    from evaluation.schema import (
        CANDIDATE_FIELDS, CANONICAL_UNITS, GOLD_FIELDS, PROPERTIES,
        TE_RECORD_FIELDS, TE_SCHEMA,
    )
