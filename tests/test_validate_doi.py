"""Unit tests for validate_doi edge cases."""

from download import validate_doi


def test_valid_doi():
    assert validate_doi("10.1000/test") is True


def test_valid_doi_with_special_chars():
    assert validate_doi("10.1371/journal.pone.0001636") is True


def test_valid_doi_with_prefix():
    assert validate_doi("doi:10.1000/test") is True


def test_valid_doi_with_uppercase_prefix():
    assert validate_doi("DOI:10.1000/test") is True


def test_valid_doi_with_whitespace():
    assert validate_doi("  10.1000/test  ") is True


def test_invalid_doi_no_slash():
    assert validate_doi("10.1000") is False


def test_invalid_doi_wrong_prefix():
    assert validate_doi("11.1000/test") is False


def test_invalid_doi_random_string():
    assert validate_doi("bad-doi") is False


def test_invalid_doi_empty():
    assert validate_doi("") is False


def test_invalid_doi_whitespace_only():
    assert validate_doi("   ") is False
