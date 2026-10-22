"""DISTRIBUTOR + FACT SALES validations - one parametrised test per registered check (suite: sales_validation)."""
import pytest
from tests.helpers import validation_params


@pytest.mark.parametrize("spec", validation_params("sales_validation"))
def test_sales_validation(spec, qa_run):
    qa_run(spec)
