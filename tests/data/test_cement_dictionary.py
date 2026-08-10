from typing import Any
from unittest.mock import Mock, patch

import pytest

from src.data.cement_dictionary import TEAM_MAPPING, normalize_team_name


def test_team_mapping_contents() -> None:
    """Validate that the TEAM_MAPPING dictionary contains key expected mappings."""
    assert isinstance(TEAM_MAPPING, dict)
    assert TEAM_MAPPING.get("real madrid") == "Real Madrid"
    assert TEAM_MAPPING.get("real madrid cf") == "Real Madrid"
    assert TEAM_MAPPING.get("rmadrid") == "Real Madrid"
    assert TEAM_MAPPING.get("fc barcelona") == "FC Barcelona"
    assert TEAM_MAPPING.get("barcelona") == "FC Barcelona"


def test_team_mapping_structure() -> None:
    """Ensure that all TEAM_MAPPING keys are clean, non-empty, and lowercase."""
    for key, value in TEAM_MAPPING.items():
        assert isinstance(key, str)
        assert isinstance(value, str)
        assert key == key.strip().lower()
        assert len(key) > 0
        assert len(value) > 0


@patch("src.data.cement_dictionary.logging.getLogger")
def test_normalize_team_name_success(mock_logger: Mock) -> None:
    """Validate successful normalization of valid team names under various formats."""
    import src.data.cement_dictionary

    original_logger = src.data.cement_dictionary.logger
    src.data.cement_dictionary.logger = mock_logger.return_value
    try:
        assert normalize_team_name("real madrid") == "Real Madrid"
        assert normalize_team_name("  Real Madrid CF  ") == "Real Madrid"
    finally:
        src.data.cement_dictionary.logger = original_logger


@patch("src.data.cement_dictionary.logging.getLogger")
def test_normalize_team_name_type_error(mock_logger: Mock) -> None:
    """Verify that a TypeError is raised and logged when api_name is not a string."""
    import src.data.cement_dictionary

    original_logger = src.data.cement_dictionary.logger
    src.data.cement_dictionary.logger = mock_logger.return_value
    try:
        with pytest.raises(TypeError):
            normalize_team_name(123)
        mock_logger.return_value.warning.assert_called()
    finally:
        src.data.cement_dictionary.logger = original_logger


@patch("src.data.cement_dictionary.logging.getLogger")
def test_normalize_team_name_key_error(mock_logger: Mock) -> None:
    """Verify that a KeyError is raised and logged when the team name is unmapped."""
    import src.data.cement_dictionary

    original_logger = src.data.cement_dictionary.logger
    src.data.cement_dictionary.logger = mock_logger.return_value
    try:
        with pytest.raises(KeyError):
            normalize_team_name("Unknown Team")
        mock_logger.return_value.warning.assert_called()
    finally:
        src.data.cement_dictionary.logger = original_logger


@pytest.mark.parametrize(
    "invalid_type",
    [None, 45.67, [], {}, set(), True]
)
@patch("src.data.cement_dictionary.logging.getLogger")
def test_normalize_team_name_various_invalid_types(mock_logger: Mock, invalid_type: Any) -> None:
    """Exhaustively verify TypeError across multiple non-string data types."""
    import src.data.cement_dictionary

    original_logger = src.data.cement_dictionary.logger
    src.data.cement_dictionary.logger = mock_logger.return_value
    try:
        with pytest.raises(TypeError) as exc_info:
            normalize_team_name(invalid_type)
        assert "Expected string for team name" in str(exc_info.value)
        mock_logger.return_value.warning.assert_called_once_with(
            "Invalid type for team name: %s", type(invalid_type)
        )
    finally:
        src.data.cement_dictionary.logger = original_logger


@pytest.mark.parametrize(
    "unmapped_team",
    ["", "   ", "atletico madrid", "chelsea", "fc_barcelona"]
)
@patch("src.data.cement_dictionary.logging.getLogger")
def test_normalize_team_name_various_unmapped_keys(mock_logger: Mock, unmapped_team: str) -> None:
    """Exhaustively verify KeyError across multiple unmapped team names."""
    import src.data.cement_dictionary

    original_logger = src.data.cement_dictionary.logger
    src.data.cement_dictionary.logger = mock_logger.return_value
    try:
        with pytest.raises(KeyError) as exc_info:
            normalize_team_name(unmapped_team)
        cleaned = unmapped_team.strip().lower()
        assert f"Unmapped team name: {cleaned}" in str(exc_info.value)
        mock_logger.return_value.warning.assert_called_once_with(
            "Team name not found in dictionary: %s", cleaned
        )
    finally:
        src.data.cement_dictionary.logger = original_logger


@patch("src.data.cement_dictionary.logging.getLogger")
def test_normalize_team_name_all_mapping_keys(mock_logger: Mock) -> None:
    """Test all defined keys in TEAM_MAPPING to guarantee clean resolution."""
    import src.data.cement_dictionary

    original_logger = src.data.cement_dictionary.logger
    src.data.cement_dictionary.logger = mock_logger.return_value
    try:
        for raw_name, expected_name in TEAM_MAPPING.items():
            # Test lowercase representation
            assert normalize_team_name(raw_name) == expected_name
            # Test uppercase representation
            assert normalize_team_name(raw_name.upper()) == expected_name
            # Test padded representation
            assert normalize_team_name(f" \t {raw_name} \n ") == expected_name
        
        # Verify that warning was never logged during successful matches
        mock_logger.return_value.warning.assert_not_called()
    finally:
        src.data.cement_dictionary.logger = original_logger