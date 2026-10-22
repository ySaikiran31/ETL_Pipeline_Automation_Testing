"""CUSTOMER MASTER + REFERENCE validations - one parametrised test per registered check (suite: customer_validation)."""
import pytest
from tests.helpers import validation_params


@pytest.mark.parametrize("spec", validation_params("customer_validation"))
def test_customer_validation(spec, qa_run):
    qa_run(spec)
