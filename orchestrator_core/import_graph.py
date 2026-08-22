import ast

def extract_imported_modules(tree: ast.AST, module_name: str) -> list[str]:
    """Extrae los modulos reales importados usando AST, resolviendo imports relativos."""
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            level = node.level
            module = node.module or ""
            if level > 0:
                parts = module_name.split('.')
                if level <= len(parts):
                    base = ".".join(parts[:-level])
                    if base:
                        resolved_base = f"{base}.{module}" if module else base
                    else:
                        resolved_base = module
                else:
                    resolved_base = module
            else:
                resolved_base = module

            if resolved_base:
                imported_modules.add(resolved_base)
                
            for alias in node.names:
                if resolved_base:
                    imported_modules.add(f"{resolved_base}.{alias.name}")
                else:
                    imported_modules.add(alias.name)
                    
    return list(imported_modules)

def resolve_imported_files(imported_modules: list[str], root_path: str, all_py_files: list[str]) -> list[str]:
    """Resuelve los nombres de modulos a archivos exactos."""
    resolved = set()
    
    # Precompute module to file mapping
    module_to_file = {}
    for f in all_py_files:
        mod = f.replace("\\", "/").replace("/", ".").replace(".py", "")
        if mod.endswith(".__init__"):
            mod = mod[:-9]
        module_to_file[mod] = f
        
    for mod in imported_modules:
        if mod in module_to_file:
            resolved.add(module_to_file[mod])
    return list(resolved)
