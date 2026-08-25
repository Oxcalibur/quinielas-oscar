import os
import logging
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from github import Auth, Github
from google import genai

from orchestrator_core.prompt_budget import PreflightError


@dataclass
class RuntimeClients:
    ai_client: genai.Client
    github_client: Github
    repo: Any  # github.Repository.Repository


def build_runtime_clients(target_repo: str = None) -> RuntimeClients:
    """Carga credenciales, aplica parches de red y construye los clientes de runtime.

    Llamar esta función es el único mecanismo que activa efectos laterales de red.
    ``import orchestrator`` debe ser siempre seguro y no requerir credenciales.
    """
    import truststore
    try:
        truststore.inject_into_ssl()
    except AttributeError:
        import urllib3
        truststore.inject_into_urllib3()
        
    load_dotenv()

    # Parche SSL opcional (solo si BYPASS_SSL_VERIFY=true)
    if os.getenv("BYPASS_SSL_VERIFY", "false").lower() == "true":
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        import requests as _req
        _original_request = _req.Session.request

        def _patched_request(self, method, url, *args, **kwargs):
            kwargs["verify"] = False
            return _original_request(self, method, url, *args, **kwargs)

        _req.Session.request = _patched_request
        logging.info("[Seguridad] Modo de compatibilidad activo: Verificacion SSL de GitHub omitida.")

    required_env = ["GITHUB_TOKEN", "REPO_OWNER", "REPO_NAME", "GEMINI_API_KEY"]
    missing = [name for name in required_env if not os.getenv(name)]
    if missing:
        raise PreflightError(
            f"Variables de entorno requeridas ausentes: {missing}. "
            "Configura el archivo .env antes de ejecutar el pipeline."
        )

    ai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    github_client = Github(
        auth=Auth.Token(os.getenv("GITHUB_TOKEN")),
        timeout=60,
    )
    repo_name = target_repo if target_repo else f"{os.getenv('REPO_OWNER')}/{os.getenv('REPO_NAME')}"
    repo = github_client.get_repo(repo_name)
    return RuntimeClients(
        ai_client=ai_client,
        github_client=github_client,
        repo=repo,
    )
