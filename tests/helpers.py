"""Helpers shared by the test modules."""
import pytest

from src.registry import checks_for


def validation_params(suite: str, include=None, exclude=None):
    """Build pytest params for one suite, optionally filtered by test-id prefix."""
    out = []
    for spec in checks_for(suite):
        prefix = spec.test_id.split("-")[0]
        if include and prefix not in include:
            continue
        if exclude and prefix in exclude:
            continue
        marks = [pytest.mark.db] if any(r.startswith("db") for r in spec.requires) or spec.test_id == "DB-001" else [pytest.mark.files]
        out.append(pytest.param(spec, id=spec.test_id, marks=marks))
    return out
