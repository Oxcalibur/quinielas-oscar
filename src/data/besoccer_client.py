import logging
from typing import Any

import requests

from src.data.cement_dictionary import normalize_team_name

__all__ = ["BeSoccerClient"]

logger = logging.getLogger(__name__)


class BeSoccerClient:
    def __init__(self, api_key: str, base_url: str) -> None:
        self.api_key: str = api_key
        self.base_url: str = base_url

    def fetch_matches(self, league_id: int) -> list[dict[str, Any]]:
        url: str = f"{self.base_url}/matches"
        params: dict[str, Any] = {"api_key": self.api_key, "league_id": league_id}
        
        try:
            response: requests.Response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data: Any = response.json()
        except requests.RequestException as e:
            logger.warning("API request failed: %s", e)
            raise

        payload: list[Any] = []
        if isinstance(data, dict):
            for val in data.values():
                if isinstance(val, list):
                    payload = val
                    break
        elif isinstance(data, list):
            payload = data
        else:
            logger.warning("Unexpected payload shape")
            raise ValueError("Unexpected payload shape")

        matches: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                logger.warning("Item in payload is not a dictionary")
                raise TypeError("Item in payload is not a dictionary")
            
            if "home_team" not in item or "away_team" not in item:
                logger.warning("Missing team keys in item")
                raise KeyError("Missing 'home_team' or 'away_team' in match item")
            
            item["home_team"] = normalize_team_name(item["home_team"])
            item["away_team"] = normalize_team_name(item["away_team"])
            
            matches.append(item)
        
        return matches