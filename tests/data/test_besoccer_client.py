import pytest
import requests
from unittest.mock import patch, Mock
from src.data.besoccer_client import BeSoccerClient


def test_module_exports() -> None:
    import src.data.besoccer_client as bc
    assert "BeSoccerClient" in bc.__all__


def test_client_initialization() -> None:
    client = BeSoccerClient(api_key="test_key", base_url="http://test.com")
    assert client.api_key == "test_key"
    assert client.base_url == "http://test.com"


@patch("src.data.besoccer_client.requests.get")
@patch("src.data.besoccer_client.logger")
def test_fetch_matches_success(mock_logger: Mock, mock_get: Mock) -> None:
    mock_response = Mock()
    mock_response.json.return_value = [
        {"home_team": "real madrid", "away_team": "barca"}
    ]
    mock_get.return_value = mock_response
    
    client = BeSoccerClient("test_key", "http://test.com")
    result = client.fetch_matches(1)
    
    mock_get.assert_called_once_with(
        "http://test.com/matches",
        params={"league": 1, "key": "test_key"},
        timeout=10
    )
    assert len(result) == 1
    assert result[0]["home_team"] == "Real Madrid"
    assert result[0]["away_team"] == "FC Barcelona"


@patch("src.data.besoccer_client.requests.get")
@patch("src.data.besoccer_client.logger")
def test_fetch_matches_api_response_not_list(mock_logger: Mock, mock_get: Mock) -> None:
    mock_response = Mock()
    mock_response.json.return_value = {"home_team": "real madrid", "away_team": "barca"}
    mock_get.return_value = mock_response
    
    client = BeSoccerClient("key", "url")
    result = client.fetch_matches(1)
    
    assert len(result) == 1
    assert result[0]["home_team"] == "Real Madrid"
    assert result[0]["away_team"] == "FC Barcelona"


@patch("src.data.besoccer_client.requests.get")
@patch("src.data.besoccer_client.logger")
def test_fetch_matches_dict_with_non_list_keys_fallback(mock_logger: Mock, mock_get: Mock) -> None:
    mock_response = Mock()
    mock_response.json.return_value = {"data": [{"home_team": "real madrid"}]}
    mock_get.return_value = mock_response
    
    client = BeSoccerClient("key", "url")
    result = client.fetch_matches(1)
    
    assert len(result) == 1
    assert result[0]["home_team"] == "Real Madrid"


@patch("src.data.besoccer_client.requests.get")
@patch("src.data.besoccer_client.logger")
def test_fetch_matches_multiple_lists_in_dict(mock_logger: Mock, mock_get: Mock) -> None:
    mock_response = Mock()
    mock_response.json.return_value = {
        "ignored_str": "value",
        "matches": [{"home_team": "real madrid"}],
        "other_list": [{"home_team": "barca"}]
    }
    mock_get.return_value = mock_response
    
    client = BeSoccerClient("key", "url")
    result = client.fetch_matches(1)
    
    # Python 3.7+ dict preserves insertion order, so "matches" should be picked first
    assert len(result) == 1
    assert result[0]["home_team"] == "Real Madrid"


@patch("src.data.besoccer_client.requests.get")
@patch("src.data.besoccer_client.logger")
def test_fetch_matches_ignores_non_dict_elements(mock_logger: Mock, mock_get: Mock) -> None:
    mock_response = Mock()
    mock_response.json.return_value = ["string_element", {"home_team": "real madrid"}]
    mock_get.return_value = mock_response
    
    client = BeSoccerClient("key", "url")
    result = client.fetch_matches(1)
    
    assert len(result) == 1
    assert result[0]["home_team"] == "Real Madrid"


@patch("src.data.besoccer_client.requests.get")
@patch("src.data.besoccer_client.logger")
def test_fetch_matches_normalization_only_on_target_keys(mock_logger: Mock, mock_get: Mock) -> None:
    mock_response = Mock()
    mock_response.json.return_value = [{"other_key": "real madrid"}]
    mock_get.return_value = mock_response
    
    client = BeSoccerClient("key", "url")
    result = client.fetch_matches(1)
    
    assert result[0]["other_key"] == "real madrid"


@patch("src.data.besoccer_client.requests.get")
@patch("src.data.besoccer_client.logger")
def test_fetch_matches_aborts_on_invalid_data_type(mock_logger: Mock, mock_get: Mock) -> None:
    mock_response = Mock()
    mock_response.json.return_value = [{"home_team": 123}]
    mock_get.return_value = mock_response
    
    client = BeSoccerClient("key", "url")
    with pytest.raises(TypeError):
        client.fetch_matches(1)


@patch("src.data.besoccer_client.requests.get")
@patch("src.data.besoccer_client.logger")
def test_fetch_matches_aborts_on_unmapped_team_name(mock_logger: Mock, mock_get: Mock) -> None:
    mock_response = Mock()
    mock_response.json.return_value = [{"home_team": "Unknown FC"}]
    mock_get.return_value = mock_response
    
    client = BeSoccerClient("key", "url")
    with pytest.raises(KeyError):
        client.fetch_matches(1)


@patch("src.data.besoccer_client.requests.get")
@patch("src.data.besoccer_client.logger")
def test_fetch_matches_non_200_http_error(mock_logger: Mock, mock_get: Mock) -> None:
    mock_get.side_effect = requests.HTTPError("404 Not Found")
    
    client = BeSoccerClient("key", "url")
    with pytest.raises(requests.HTTPError):
        client.fetch_matches(1)
    mock_logger.warning.assert_called_once()


@patch("src.data.besoccer_client.requests.get")
@patch("src.data.besoccer_client.logger")
def test_fetch_matches_connection_timeout(mock_logger: Mock, mock_get: Mock) -> None:
    mock_get.side_effect = requests.Timeout("Timeout")
    
    client = BeSoccerClient("key", "url")
    with pytest.raises(requests.Timeout):
        client.fetch_matches(1)
    mock_logger.warning.assert_called_once()


@patch("src.data.besoccer_client.requests.get")
@patch("src.data.besoccer_client.logger")
def test_fetch_matches_none_teams_fields_handled_correctly(mock_logger: Mock, mock_get: Mock) -> None:
    mock_response = Mock()
    mock_response.json.return_value = [{"home_team": None, "away_team": "barca"}]
    mock_get.return_value = mock_response
    
    client = BeSoccerClient("key", "url")
    result = client.fetch_matches(1)
    assert result[0]["home_team"] is None
    assert result[0]["away_team"] == "FC Barcelona"


@patch("src.data.besoccer_client.requests.get")
@patch("src.data.besoccer_client.logger")
def test_fetch_matches_missing_teams_fields_passed_through(mock_logger: Mock, mock_get: Mock) -> None:
    mock_response = Mock()
    mock_response.json.return_value = [{"id": 1}]
    mock_get.return_value = mock_response
    
    client = BeSoccerClient("key", "url")
    result = client.fetch_matches(1)
    assert result[0]["id"] == 1


@patch("src.data.besoccer_client.requests.get")
@patch("src.data.besoccer_client.logger")
def test_fetch_matches_unexpected_payload_shape(mock_logger: Mock, mock_get: Mock) -> None:
    mock_response = Mock()
    mock_response.json.return_value = "unexpected string"
    mock_get.return_value = mock_response
    
    client = BeSoccerClient("key", "url")
    result = client.fetch_matches(1)
    assert result == []


@patch("src.data.besoccer_client.requests.get")
@patch("src.data.besoccer_client.logger")
def test_fetch_matches_mixed_valid_and_missing_keys(mock_logger: Mock, mock_get: Mock) -> None:
    mock_response = Mock()
    mock_response.json.return_value = [
        {"home_team": "real madrid"},
        {"away_team": "barca"},
        {"home_team": None, "away_team": None},
        {"other_field": "val"}
    ]
    mock_get.return_value = mock_response
    
    client = BeSoccerClient("key", "url")
    result = client.fetch_matches(1)
    
    assert len(result) == 4
    assert result[0]["home_team"] == "Real Madrid"
    assert result[1]["away_team"] == "FC Barcelona"
    assert result[2]["home_team"] is None
    assert result[2]["away_team"] is None
    assert result[3]["other_field"] == "val"