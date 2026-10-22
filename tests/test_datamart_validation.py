"""DATA MART validations - one parametrised test per registered check (suite: datamart_validation)."""
import pytest
from tests.helpers import validation_params


@pytest.mark.parametrize("spec", validation_params("datamart_validation"))
def test_datamart_validation(spec, qa_run):
    qa_run(spec)
