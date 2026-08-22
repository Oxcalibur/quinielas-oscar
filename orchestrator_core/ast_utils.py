import ast

def serialize_ast_signature(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> str:
    """Serializa la firma completa de un nodo (clase o función) utilizando ast.unparse."""
    if isinstance(node, ast.ClassDef):
        bases = []
        for b in node.bases:
            try:
                bases.append(ast.unparse(b))
            except Exception:
                pass
        base_str = f"({', '.join(bases)})" if bases else ""
        return f"class {node.name}{base_str}"
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        keyword = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        try:
            args_str = ast.unparse(node.args)
        except Exception:
            args_str = ""
        returns_str = ""
        if node.returns:
            try:
                returns_str = f" -> {ast.unparse(node.returns)}"
            except Exception:
                pass
        return f"{keyword} {node.name}({args_str}){returns_str}"
    return ""

def extract_ast_signatures(tree: ast.AST) -> dict[str, str]:
    """Extracts top-level classes, their methods, and top-level functions."""
    signatures = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            signatures[node.name] = serialize_ast_signature(node)
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    signatures[f"{node.name}.{child.name}"] = serialize_ast_signature(child)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            signatures[node.name] = serialize_ast_signature(node)
    return signatures
