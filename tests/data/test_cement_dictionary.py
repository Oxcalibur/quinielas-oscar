import pytest
from unittest.mock import patch, Mock
from src.data.cement_dictionary import normalize_team_name, TEAM_MAPPING

def test_cement_dictionary_all_export() -> None:
    import src.data.cement_dictionary as cd
    assert "normalize_team_name" in cd.__all__
    assert "TEAM_MAPPING" in cd.__all__

def test_team_mapping_integrity() -> None:
    assert isinstance(TEAM_MAPPING, dict)
    assert len(TEAM_MAPPING) > 0
    for key, value in TEAM_MAPPING.items():
        assert isinstance(key, str)
        assert isinstance(value, str)
        assert key == key.strip().lower()

@pytest.mark.parametrize("input_name, expected", [
    ("real madrid", "Real Madrid"),
    ("  Real Madrid CF  ", "Real Madrid"),
    ("rmadrid", "Real Madrid"),
    ("barca", "FC Barcelona"),
    ("  SeViLlA  ", "Sevilla FC"),
    ("atletico", "Atletico de Madrid"),
])
def test_normalize_team_name_variations(input_name: str, expected: str) -> None:
    assert normalize_team_name(input_name) == expected

def test_all_mapping_entries_resolve() -> None:
    for key, value in TEAM_MAPPING.items():
        assert normalize_team_name(key) == value
        assert normalize_team_name(key.upper()) == value
        assert normalize_team_name(f"  {key}  ") == value

@patch("src.data.cement_dictionary.logger")
def test_normalize_team_name_type_error(mock_logger: Mock) -> None:
    invalid_input = 123
    with pytest.raises(TypeError) as exc_info:
        normalize_team_name(invalid_input)  # type: ignore
    
    assert "Team name must be a string" in str(exc_info.value)
    mock_logger.warning.assert_called_once_with("Invalid type for team name: <class 'int'>")

@patch("src.data.cement_dictionary.logger")
def test_normalize_team_name_key_error(mock_logger: Mock) -> None:
    unknown_team = "Unknown FC"
    with pytest.raises(KeyError) as exc_info:
        normalize_team_name(unknown_team)
        
    assert "Unmapped team name: Unknown FC" in str(exc_info.value)
    mock_logger.warning.assert_called_once_with("Team name not found in dictionary: Unknown FC")