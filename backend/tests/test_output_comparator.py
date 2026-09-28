from app.services.output_comparator import compare_outputs, normalize_output


def test_identical_outputs_match():
    assert compare_outputs("15\n", "15").matches


def test_trailing_whitespace_and_crlf_are_not_behavioral_differences():
    assert compare_outputs("15  \r\n\n", "15\n").matches


def test_different_values_do_not_match():
    outcome = compare_outputs("15", "16")
    assert not outcome.matches
    assert "expected '15' but received '16'" in outcome.difference


def test_float_formatting_within_tolerance_matches():
    assert compare_outputs("3.0", "3").matches
    assert compare_outputs("0.1000000000", "0.1").matches


def test_extra_line_is_a_difference():
    outcome = compare_outputs("1\n2", "1\n2\n3")
    assert not outcome.matches


def test_normalize_output_strips_trailing_blank_lines():
    assert normalize_output("a\nb\n\n\n") == "a\nb"
