"""Unit tests for stage-7 search and Property request contracts."""

import pytest
from pydantic import ValidationError

from mylabdata.schemas.catalog import PropertyUpdateRequest, SearchCondition


def test_search_condition_requires_attribute_and_entry_identifiers() -> None:
    condition = SearchCondition(
        attribute_key="score",
        entry_key="score.default",
        operator="between",
        value=1,
        second_value=2,
    )
    assert condition.attribute_key == "score"

    with pytest.raises(ValidationError, match="Attribute identifier"):
        SearchCondition(entry_id=1, operator="eq", value=1)


def test_property_request_requires_exactly_one_strict_value_and_source() -> None:
    request = PropertyUpdateRequest(value_boolean=True, source="manual:user")
    assert request.value_boolean is True

    with pytest.raises(ValidationError, match="exactly one"):
        PropertyUpdateRequest(
            value_number=1,
            value_boolean=True,
            source="manual:user",
        )
    with pytest.raises(ValidationError, match="must be boolean"):
        PropertyUpdateRequest(value_boolean=1, source="manual:user")
