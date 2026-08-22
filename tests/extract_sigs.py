import ast
import sys
import pprint

sys.path.append('g:/Mi unidad/Olivia/sdlc_agent_prototype/quinielas-oscar')
import orchestrator

with open('orchestrator.py', 'r', encoding='utf-8') as f:
    tree = ast.parse(f.read())
sigs = orchestrator.extract_ast_signatures(tree)

funcs_to_track = [
    'run_mypy',
    'run_static_analysis',
    'agent_implement_code',
    'agent_generate_tests',
    'agent_generate_execution_report',
    'agent_update_architecture_doc',
    'agent_update_user_manual',
    'agent_analyze_pipeline_failure',
    'agent_code_reviewer',
    'agent_security_audit',
    'run_pipeline'
]

print('expected_signatures = {')
for name in funcs_to_track:
    if name in sigs:
        print(f'    "{name}": "{sigs[name]}",')
    else:
        print(f'    # WARNING: {name} not found in sigs!')
print('}')
