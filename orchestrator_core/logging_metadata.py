import os
import json
import logging
import datetime
from typing import Any, Dict

def write_local_log(issue_id, title, success, details="", run_log_dir="."):
    log_file = os.path.join(run_log_dir, "pipeline.log")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "SUCCESS" if success else "FAILED"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] Issue #{issue_id} - '{title}' | Estado: {status}\n")
        if details: f.write(f"Detalle: {details}\n")
        f.write("-" * 80 + "\n")
    logging.info(f"Historial guardado en '{log_file}'")


def write_transactional_metadata(run_id, issue_id, title, success, design, commit_hash="N/A"):
    registry_file = "docs/metadata/runs_registry.json"
    os.makedirs("docs/metadata", exist_ok=True)
    registry = {}
    if os.path.exists(registry_file):
        try:
            with open(registry_file, "r", encoding="utf-8") as f: registry = json.load(f)
        except Exception: registry = {}
    created_files, modified_files, deleted_files = [], [], []
    for action in design.get("actions", []):
        filepath = action.get("filepath")
        op = action.get("operation", "").upper()
        if op == "CREATE": created_files.append(filepath)
        elif op == "MODIFY": modified_files.append(filepath)
        elif op == "DELETE": deleted_files.append(filepath)
            
    registry[run_id] = {
        "issue_id": issue_id, "title": title,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "SUCCESS" if success else "FAILED",
        "commit_hash": commit_hash,
        "impact": {"created": created_files, "modified": modified_files, "deleted": deleted_files}
    }
    try:
        with open(registry_file, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=4, ensure_ascii=False)
            logging.info(f"Registro transaccional guardado en '{registry_file}'")
    except Exception as e:
            logging.warning(f"No se pudo actualizar el JSON de trazabilidad: {e}")


