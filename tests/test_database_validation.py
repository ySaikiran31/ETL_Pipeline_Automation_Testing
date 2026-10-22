"""DATABASE + SQL validations - one parametrised test per registered check (suite: database_validation)."""
import pytest
from tests.helpers import validation_params


@pytest.mark.parametrize("spec", validation_params("database_validation"))
def test_database_validation(spec, qa_run):
    qa_run(spec)
