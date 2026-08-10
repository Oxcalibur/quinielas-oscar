from unittest.mock import Mock, patch

import pytest
import requests

from src.data.besoccer_client import BeSoccerClient


@patch("src.data.besoccer_client.requests.get")
def test_fetch_matches_success_list_payload(mock_get: Mock) -> None:
    """Validate matches are parsed correctly when the API returns a list payload."""
    mock_response = Mock()
    mock_response.json.return_value = [
        {"home_team": "real madrid", "away_team": "barcelona"}
    ]
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    client = BeSoccerClient("dummy_key", "http://dummy.url")
    result = client.fetch_matches(1)

    assert result == [{"home_team": "Real Madrid", "away_team": "FC Barcelona"}]
    mock_get.assert_called_once_with(
        "http://dummy.url/matches",
        params={"api_key": "dummy_key", "league_id": 1},
        timeout=10,
    )


@patch("src.data.besoccer_client.requests.get")
def test_fetch_matches_success_dict_payload(mock_get: Mock) -> None:
    """Validate matches are parsed correctly when the API returns a dictionary payload wrapping a list."""
    mock_response = Mock()
    mock_response.json.return_value = {
        "matches": [
            {"home_team": "rmadrid", "away_team": "fc barcelona"}
        ]
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    client = BeSoccerClient("dummy_key", "http://dummy.url")
    result = client.fetch_matches(1)

    assert result == [{"home_team": "Real Madrid", "away_team": "FC Barcelona"}]


@patch("src.data.besoccer_client.requests.get")
def test_fetch_matches_network_failure(mock_get: Mock) -> None:
    """Validate that requests.RequestException is logged and re-raised upon network failure."""
    mock_get.side_effect = requests.RequestException("Network error")
    client = BeSoccerClient("dummy_key", "http://dummy.url")
    with pytest.raises(requests.RequestException):
        client.fetch_matches(1)


@patch("src.data.besoccer_client.requests.get")
def test_fetch_matches_key_error_unmapped_team(mock_get: Mock) -> None:
    """Validate that KeyError is raised when a team name is not defined in cement_dictionary."""
    mock_response = Mock()
    mock_response.json.return_value = [
        {"home_team": "Unknown FC", "away_team": "real madrid"}
    ]
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    client = BeSoccerClient("dummy_key", "http://dummy.url")
    with pytest.raises(KeyError) as exc_info:
        client.fetch_matches(1)
    assert "Unmapped team name" in str(exc_info.value)


@patch("src.data.besoccer_client.requests.get")
def test_fetch_matches_key_error_missing_keys(mock_get: Mock) -> None:
    """Validate that KeyError is raised if the keys 'home_team' or 'away_team' are missing in the item."""
    mock_response = Mock()
    mock_response.json.return_value = [{"other_key": "value"}]
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    client = BeSoccerClient("dummy_key", "http://dummy.url")
    with pytest.raises(KeyError) as exc_info:
        client.fetch_matches(1)
    assert "Missing 'home_team' or 'away_team'" in str(exc_info.value)


@patch("src.data.besoccer_client.requests.get")
def test_fetch_matches_skips_non_dict_items(mock_get: Mock) -> None:
    """Validate that TypeError is raised if a payload item is not a dictionary."""
    mock_response = Mock()
    mock_response.json.return_value = ["not_a_dict"]
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    client = BeSoccerClient("dummy_key", "http://dummy.url")
    with pytest.raises(TypeError) as exc_info:
        client.fetch_matches(1)
    assert "Item in payload is not a dictionary" in str(exc_info.value)


@patch("src.data.besoccer_client.requests.get")
def test_fetch_matches_fail_fast_on_non_dict_items(mock_get: Mock) -> None:
    """Validate that match processing fails fast with TypeError when encountering any non-dict items."""
    mock_response = Mock()
    mock_response.json.return_value = [
        {"home_team": "real madrid", "away_team": "barcelona"},
        "invalid_string"
    ]
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    client = BeSoccerClient("dummy_key", "http://dummy.url")
    with pytest.raises(TypeError) as exc_info:
        client.fetch_matches(1)
    assert "Item in payload is not a dictionary" in str(exc_info.value)


@patch("src.data.besoccer_client.requests.get")
def test_fetch_matches_unexpected_payload_shape(mock_get: Mock) -> None:
    """Validate that ValueError is raised if the returned payload has an unsupported shape (neither dict nor list)."""
    mock_response = Mock()
    mock_response.json.return_value = "invalid_payload_shape"
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    client = BeSoccerClient("dummy_key", "http://dummy.url")
    with pytest.raises(ValueError) as exc_info:
        client.fetch_matches(1)
    assert "Unexpected payload shape" in str(exc_info.value)


@patch("src.data.besoccer_client.requests.get")
def test_fetch_matches_normalize_type_error(mock_get: Mock) -> None:
    """Validate that TypeError is raised and forwarded when normalized_team_name receives a non-string type."""
    mock_response = Mock()
    mock_response.json.return_value = [
        {"home_team": 12345, "away_team": "barcelona"}
    ]
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    client = BeSoccerClient("dummy_key", "http://dummy.url")
    with pytest.raises(TypeError) as exc_info:
        client.fetch_matches(1)
    assert "Expected string for team name" in str(exc_info.value)