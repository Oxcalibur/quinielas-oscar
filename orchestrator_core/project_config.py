import ast
import fnmatch
import os
import re

from orchestrator_core.schemas import PythonProjectConfiguration

def is_test_file(filepath: str, content: str = None, project_config: "PythonProjectConfiguration" = None) -> bool:
    """Detecta de forma fiable si un archivo es un test usando heurísticas y configuración de pytest."""
    filepath = filepath.replace("\\", "/")
    filename = os.path.basename(filepath)
    
    if filename == "conftest.py":
        return True
        
    testpaths = ["tests", "test", "testing"]
    python_files = ["test_*.py", "*_test.py"]
    
    if project_config:
        if project_config.pytest_paths:
            testpaths = project_config.pytest_paths
        if project_config.pytest_patterns:
            python_files = project_config.pytest_patterns

    path_parts = filepath.split("/")
    in_test_dir = any(part in testpaths for part in path_parts)
    
    matches_pattern = any(fnmatch.fnmatch(filename, pattern) for pattern in python_files)
    
    if matches_pattern:
        return True
        
    if in_test_dir and filename.endswith(".py"):
        return True
        
    if content:
        if re.search(r"^\s*(?:import\s+(?:pytest|unittest)|from\s+(?:pytest|unittest)\s+import)", content, re.MULTILINE):
            return True
            
    return False

def parse_pyproject(content: str) -> dict:
    import tomllib
    result = {"python_version": None, "tools": {}, "dependencies": [], "dev_dependencies": []}
    try:
        data = tomllib.loads(content)
        # Python version
        req_py = data.get("project", {}).get("requires-python")
        if not req_py:
            req_py = data.get("tool", {}).get("poetry", {}).get("dependencies", {}).get("python")
        result["python_version"] = str(req_py) if req_py else None
        
        # Tools
        result["tools"] = data.get("tool", {})
        
        # PEP 621 dependencies
        for dep in data.get("project", {}).get("dependencies", []):
            dep_name = re.split(r'[=><~\[]', dep)[0].strip()
            if dep_name: result["dependencies"].append(dep_name)
        for group_deps in data.get("project", {}).get("optional-dependencies", {}).values():
            for dep in group_deps:
                dep_name = re.split(r'[=><~\[]', dep)[0].strip()
                if dep_name: result["dev_dependencies"].append(dep_name)
                
        # Poetry dependencies
        poetry = data.get("tool", {}).get("poetry", {})
        for dep in poetry.get("dependencies", {}).keys():
            if dep != "python": result["dependencies"].append(dep)
        for dep in poetry.get("dev-dependencies", {}).keys():
            result["dev_dependencies"].append(dep)
        for group in poetry.get("group", {}).values():
            for dep in group.get("dependencies", {}).keys():
                result["dev_dependencies"].append(dep)
    except Exception:
        pass
    return result

def parse_requirements(content: str) -> list[str]:
    deps = []
    for line in content.splitlines():
        line = line.split('#')[0].strip()
        if line and not line.startswith('-'):
            dep_name = re.split(r'[=><~\[]', line)[0].strip()
            if dep_name: deps.append(dep_name)
    return deps

def parse_pipfile(content: str) -> dict:
    import tomllib
    result = {"dependencies": [], "dev_dependencies": []}
    try:
        data = tomllib.loads(content)
        result["dependencies"] = list(data.get("packages", {}).keys())
        result["dev_dependencies"] = list(data.get("dev-packages", {}).keys())
    except Exception:
        pass
    return result

def parse_poetry_lock(content: str) -> list[str]:
    import tomllib
    deps = []
    try:
        data = tomllib.loads(content)
        for pkg in data.get("package", []):
            name = pkg.get("name")
            if name: deps.append(name)
    except Exception:
        pass
    return deps

def parse_setup_cfg(content: str) -> list[str]:
    import configparser
    deps = []
    try:
        config = configparser.ConfigParser()
        config.read_string(content)
        if config.has_option("options", "install_requires"):
            reqs = config.get("options", "install_requires").splitlines()
            for r in reqs:
                dep_name = re.split(r'[=><~\[]', r.strip())[0].strip()
                if dep_name: deps.append(dep_name)
    except Exception:
        pass
    return deps

def parse_setup_py(content: str) -> dict:
    """Extrae literales seguros de setup() usando AST sin ejecutar código."""
    result = {"install_requires": [], "extras_require": {}, "python_requires": None}
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "setup":
                for kw in getattr(node, "keywords", []):
                    if kw.arg == "python_requires" and isinstance(kw.value, ast.Constant):
                        result["python_requires"] = kw.value.value
                    elif kw.arg == "install_requires" and isinstance(kw.value, (ast.List, ast.Tuple)):
                        for elt in kw.value.elts:
                            if isinstance(elt, ast.Constant):
                                dep_name = re.split(r'[=><~\[]', str(elt.value).strip())[0].strip()
                                if dep_name:
                                    result["install_requires"].append(dep_name)
                    elif kw.arg == "extras_require" and isinstance(kw.value, ast.Dict):
                        for k, v in zip(kw.value.keys, kw.value.values):
                            if isinstance(k, ast.Constant) and isinstance(v, (ast.List, ast.Tuple)):
                                ex_deps = []
                                for elt in v.elts:
                                    if isinstance(elt, ast.Constant):
                                        dep_name = re.split(r'[=><~\[]', str(elt.value).strip())[0].strip()
                                        if dep_name:
                                            ex_deps.append(dep_name)
                                result["extras_require"][k.value] = ex_deps
    except Exception:
        pass
    return result
