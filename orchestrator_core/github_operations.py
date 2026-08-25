import os
import logging
import subprocess
from typing import Tuple, Dict
from orchestrator_core.schemas import GateResult
from orchestrator_core.runtime import RuntimeClients
from orchestrator_core.logging_metadata import write_transactional_metadata

def fetch_issue(issue_id: int, repo) -> tuple[str, str]:
    logging.info(f"Leyendo requisitos en el Issue #{issue_id}...")
    issue = repo.get_issue(number=issue_id)
    return issue.title, issue.body


def _sanitize_staging_area() -> None:
    """
    Remove newly created transient Python artifacts (*.pyc, __pycache__) from the staging area.
    This prevents test execution artifacts from polluting the generated PR,
    while preserving any such files that were already tracked in the baseline.
    """
    result = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=A"], capture_output=True, text=True, check=True, timeout=60)
    added_files = [f.strip() for f in result.stdout.split('\n') if f.strip()]
    for file_path in added_files:
        path_segments = file_path.replace('\\', '/').split('/')
        if "__pycache__" in path_segments or file_path.endswith(".pyc"):
            subprocess.run(["git", "reset", "HEAD", "--", file_path], check=True, timeout=60)

def deploy_to_github(design: dict, generated_files: dict[str, str], report_path: str, arch_path: str, user_manual_path: str, issue_id: int, run_id: str, runtime: RuntimeClients) -> None:
    logging.info("Inicializando PR de alta trazabilidad...")
    commit_title = f"feat(issue-{issue_id}): [{run_id}] refactorizacion y solucion modular evolutiva"
    commit_body = f"Trazabilidad: {run_id}\nJustificacion: {design.get('architecture_justification', '[no disponible]')}"
    
    try:
        # Stage all changes automatically: new files, modifications, and deletions.
        subprocess.run(["git", "add", "-A"], check=True, timeout=60)

        # D6: Sanitize the staging area before committing
        _sanitize_staging_area()

        subprocess.run(["git", "commit", "-m", commit_title, "-m", commit_body], check=True, timeout=60)

        # Obtener el hash del commit de implementación
        code_commit_hash = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=60).stdout.strip()

        # Escribir el registro de metadatos con el hash correcto
        write_transactional_metadata(run_id, issue_id, design.get("architecture_justification", "Refactor"), True, design, code_commit_hash)

        # Commit 2: Registro de auditoría
        subprocess.run(["git", "add", "docs/metadata/runs_registry.json"], check=True, timeout=60)
        subprocess.run(["git", "commit", "-m", "chore(audit): register run metadata"], check=True, timeout=60)

        logging.info("Empujando rama de refactorizacion a GitHub...")
        branch_name = f"agent/issue-{issue_id}/{run_id}"
        subprocess.run(["git", "push", "-u", "origin", branch_name], check=True, timeout=300)
        pr = runtime.repo.create_pull(title=f"[Agente SDLC] [{run_id}] Issue #{issue_id}", body=f"Cambio autónomo (Run {run_id}).\nCloses #{issue_id}", head=branch_name, base="main")
        logging.info(f"Pull Request creado: {pr.html_url}")
        try:
            issue = runtime.repo.get_issue(number=issue_id)
            for lbl in ["status:in-progress", "ai:ready-to-code"]:
                if lbl in [l.name for l in issue.labels]: issue.remove_from_labels(lbl)
            try: runtime.repo.get_label("status:pending-review")
            except: runtime.repo.create_label("status:pending-review", "d4c5f9")
            issue.add_to_labels("status:pending-review")
        except Exception: pass
    except Exception:
        logging.exception("Error crítico durante el despliegue.")
        raise
    finally:
        logging.info("Sincronizando entorno con origin...")
        subprocess.run(["git", "fetch", "origin"], capture_output=True, timeout=300)


def ensure_git_setup() -> None:
    logging.info("Verificando Git local...")
    if not os.path.exists(".git"):
        subprocess.run(["git", "init"], check=True, capture_output=True, timeout=60)
        subprocess.run(["git", "checkout", "-b", "main"], check=True, capture_output=True, timeout=60)
    remotes = subprocess.run(["git", "remote"], capture_output=True, text=True, timeout=60)
    if "origin" not in remotes.stdout:
        remote_url = f"https://github.com/{os.getenv('REPO_OWNER')}/{os.getenv('REPO_NAME')}.git"
        subprocess.run(["git", "remote", "add", "origin", remote_url], check=True, capture_output=True, timeout=60)
    if subprocess.run(["git", "log", "-1"], capture_output=True, timeout=60).returncode != 0:
        subprocess.run(["git", "fetch", "origin"], capture_output=True, timeout=300)
        subprocess.run(["git", "pull", "origin", "main", "--allow-unrelated-histories", "--no-rebase"], capture_output=True, timeout=300)
    else:
        subprocess.run(["git", "checkout", "main"], check=True, capture_output=True, timeout=60)
        subprocess.run(["git", "pull", "origin", "main"], check=True, capture_output=True, timeout=300)


