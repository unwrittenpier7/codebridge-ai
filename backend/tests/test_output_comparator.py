from app.services.output_comparator import compare_outputs, normalize_output


def test_identical_outputs_match():
    assert compare_outputs("15\n", "15").matches


def test_trailing_whitespace_and_crlf_are_not_behavioral_differences():
    assert compare_outputs("15  \r\n\n", "15\n").matches


def test_different_values_do_not_match():
    outcome = compare_outputs("15", "16")
    assert not outcome.matches
    assert "expected '15' but received '16'" in outcome.difference


def test_float_formatting_differs_by_default():
    """`3.0` and `3` are different bytes; tolerance must be requested explicitly."""
    assert not compare_outputs("3.0", "3").matches
    assert not compare_outputs("0.1000000000", "0.1").matches


def test_float_formatting_matches_when_tolerance_is_enabled():
    assert compare_outputs("3.0", "3", numeric_tolerance=True).matches
    assert compare_outputs("0.1000000000", "0.1", numeric_tolerance=True).matches
    assert compare_outputs("1e3", "1000.0", numeric_tolerance=True).matches


def test_numeric_tolerance_does_not_ignore_non_numeric_tokens():
    assert not compare_outputs("yes", "no", numeric_tolerance=True).matches
    assert not compare_outputs("1 yes", "1 no", numeric_tolerance=True).matches


def test_extra_line_is_a_difference():
    outcome = compare_outputs("1\n2", "1\n2\n3")
    assert not outcome.matches


def test_normalize_output_strips_trailing_blank_lines():
    assert normalize_output("a\nb\n\n\n") == "a\nb"


def test_leading_and_internal_whitespace_is_significant():
    assert not compare_outputs("  15", "15").matches
    assert not compare_outputs("1  2", "1 2").matches
