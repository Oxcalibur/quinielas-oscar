from src.data.besoccer_client import BeSoccerClient

# Whitelist methods to prevent Vulture false positives
_ = BeSoccerClient.fetch_matches