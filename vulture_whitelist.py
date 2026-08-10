"""
Este archivo se utiliza para marcar explícitamente el código que Vulture
podría identificar incorrectamente como 'código muerto' (falsos positivos).
"""
from src.data.besoccer_client import BeSoccerClient

# Se marca el método como 'usado' asignándolo a una variable dummy '_'.
# Esto sigue el estándar definido en docs/ARCHITECTURE.md.
_ = BeSoccerClient.fetch_matches