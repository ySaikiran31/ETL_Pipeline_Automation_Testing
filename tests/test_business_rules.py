"""Product-family (PRD), key/code mapping (MAP) and temporal (BR) business rules."""
import pytest
from tests.helpers import validation_params


@pytest.mark.parametrize("spec", validation_params("business_rules", exclude={"CAL"}))
def test_business_rules(spec, qa_run):
    qa_run(spec)
