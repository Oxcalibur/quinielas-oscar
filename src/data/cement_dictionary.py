import logging

__all__ = ["normalize_team_name", "TEAM_MAPPING"]

logger = logging.getLogger(__name__)

TEAM_MAPPING: dict[str, str] = {
    "real madrid": "Real Madrid",
    "real madrid cf": "Real Madrid",
    "rmadrid": "Real Madrid",
    "fc barcelona": "FC Barcelona",
    "barcelona": "FC Barcelona",
    "barca": "FC Barcelona",
    "atletico madrid": "Atletico de Madrid",
    "atletico": "Atletico de Madrid",
    "sevilla fc": "Sevilla FC",
    "sevilla": "Sevilla FC"
}

def normalize_team_name(api_name: str) -> str:
    if not isinstance(api_name, str):
        logger.warning(f"Invalid type for team name: {type(api_name)}")
        raise TypeError(f"Team name must be a string, got {type(api_name)}")
    
    cleaned_name = api_name.strip().lower()
    if cleaned_name not in TEAM_MAPPING:
        logger.warning(f"Team name not found in dictionary: {api_name}")
        raise KeyError(f"Unmapped team name: {api_name}")
        
    return TEAM_MAPPING[cleaned_name]