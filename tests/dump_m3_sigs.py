import inspect
import ast
import orchestrator

M3_SYMBOLS = ['serialize_ast_signature', 'extract_ast_signatures', 'is_test_file', 'parse_pyproject', 'parse_requirements', 'parse_pipfile', 'parse_poetry_lock', 'parse_setup_cfg', 'parse_setup_py', 'resolve_safe_path']

for s in M3_SYMBOLS:
    func = getattr(orchestrator, s)
    source = inspect.getsource(func)
    tree = ast.parse(source)
    sigs = orchestrator.extract_ast_signatures(tree)
    print(f'        "{s}": "{sigs[s]}",')
