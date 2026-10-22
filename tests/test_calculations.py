"""Monetary calculation validations (CAL-xxx)."""
import pytest
from tests.helpers import validation_params


@pytest.mark.parametrize("spec", validation_params("business_rules", include={"CAL"}))
def test_calculations(spec, qa_run):
    qa_run(spec)
