import os

def resolve_safe_path(root: str, relative_path: str) -> str:
    root_abs = os.path.abspath(root)
    target_abs = os.path.abspath(os.path.join(root_abs, relative_path))

    if os.path.commonpath([root_abs, target_abs]) != root_abs:
        raise ValueError(f"Ruta fuera del repositorio: {relative_path}")

    return target_abs
