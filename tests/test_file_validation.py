"""FILE STRUCTURE validations - one parametrised test per registered check (suite: file_validation)."""
import pytest
from tests.helpers import validation_params


@pytest.mark.parametrize("spec", validation_params("file_validation"))
def test_file_validation(spec, qa_run):
    qa_run(spec)
