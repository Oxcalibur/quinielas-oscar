__all__ = ["BeSoccerClient"]

import logging
from typing import Any
import requests
from src.data.cement_dictionary import normalize_team_name

logger = logging.getLogger(__name__)


class BeSoccerClient:
    def __init__(self, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url

    def fetch_matches(self, league_id: int) -> list[dict[str, Any]]:
        url = f"{self.base_url}/matches"
        params = {"league": league_id, "key": self.api_key}

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.warning(
                f"Network error fetching matches for league {league_id}: {e}"
            )
            raise

        data = response.json()
        if not isinstance(data, list):
            if isinstance(data, dict):
                possible_lists = [v for v in data.values() if isinstance(v, list)]
                if possible_lists:
                    data = possible_lists[0]
                else:
                    data = [data]
            else:
                data = []

        processed_matches: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue

            if "home_team" in item and item["home_team"] is not None:
                item["home_team"] = normalize_team_name(item["home_team"])
            if "away_team" in item and item["away_team"] is not None:
                item["away_team"] = normalize_team_name(item["away_team"])

            processed_matches.append(item)

        return processed_matches