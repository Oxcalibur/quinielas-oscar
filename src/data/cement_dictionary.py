import logging
from typing import Any

__all__ = ["TEAM_MAPPING", "normalize_team_name"]

logger = logging.getLogger(__name__)

TEAM_MAPPING: dict[str, str] = {
    "real madrid": "Real Madrid",
    "real madrid cf": "Real Madrid",
    "rmadrid": "Real Madrid",
    "fc barcelona": "FC Barcelona",
    "barcelona": "FC Barcelona"
}


def normalize_team_name(api_name: Any) -> str:
    """
    Normalize a given team name using the predefined TEAM_MAPPING.
    
    Args:
        api_name (Any): The raw team name from an API or external source.
        
    Returns:
        str: The normalized team name.
        
    Raises:
        TypeError: If the api_name is not a string.
        KeyError: If the cleaned team name is not found in TEAM_MAPPING.
    """
    if not isinstance(api_name, str):
        logger.warning("Invalid type for team name: %s", type(api_name))
        raise TypeError(f"Expected string for team name, got {type(api_name)}")
    
    cleaned: str = api_name.strip().lower()
    if cleaned not in TEAM_MAPPING:
        logger.warning("Team name not found in dictionary: %s", cleaned)
        raise KeyError(f"Unmapped team name: {cleaned}")
        
    return TEAM_MAPPING[cleaned]