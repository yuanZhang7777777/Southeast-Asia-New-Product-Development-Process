from app.field_mapping import empty_value, mapped_text


def test_unmatched_or_blank_source_fields_stay_empty_not_zero() -> None:
    assert empty_value(None) is None
    assert empty_value("") is None
    assert empty_value("  ") is None
    assert mapped_text({}) is None
    assert mapped_text({"A": ""}, "A") is None
