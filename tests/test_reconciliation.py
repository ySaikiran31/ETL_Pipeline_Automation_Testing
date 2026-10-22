"""RECONCILIATION validations - one parametrised test per registered check (suite: reconciliation)."""
import pytest
from tests.helpers import validation_params


@pytest.mark.parametrize("spec", validation_params("reconciliation"))
def test_reconciliation(spec, qa_run):
    qa_run(spec)
