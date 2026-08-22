import os
import sys
import pytest
import hashlib
from unittest.mock import patch, MagicMock

with patch('os.getenv', return_value=None):
    import orchestrator

@patch('orchestrator.load_dotenv')
def test_import_no_credentials(mock_load):
    with patch.dict(os.environ, clear=True):
        with pytest.raises(orchestrator.PreflightError):
            orchestrator.build_runtime_clients()

def test_modify_identical_content():
    contract = orchestrator.AcceptanceContract(required_modified_files={'test.py'})
    content = 'print("hello")'
    file_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    repo_context = MagicMock()
    repo_context.source_index = {'test.py': MagicMock(file_hash=file_hash)}
    repo_context.test_index = {}
    
    generated = {'test.py': content}
    valid, err = orchestrator.validate_generated_manifest(generated, contract, repo_context)
    assert not valid
    assert 'idéntico' in err or 'identico' in err

def test_modify_changed_content():
    contract = orchestrator.AcceptanceContract(required_modified_files={'test.py'})
    content = 'print("hello")'
    new_content = 'print("hello world")'
    file_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    repo_context = MagicMock()
    repo_context.source_index = {'test.py': MagicMock(file_hash=file_hash)}
    repo_context.test_index = {}
    
    generated = {'test.py': new_content}
    valid, err = orchestrator.validate_generated_manifest(generated, contract, repo_context)
    assert valid, err

def test_modify_inexistent_baseline():
    contract = orchestrator.AcceptanceContract(required_modified_files={'test.py'})
    repo_context = MagicMock()
    repo_context.source_index = {}
    repo_context.test_index = {}
    
    generated = {'test.py': 'print("hello")'}
    valid, err = orchestrator.validate_generated_manifest(generated, contract, repo_context)
    assert not valid
    assert 'no existía en el baseline' in err or 'no existia' in err

def test_create_over_existing_baseline():
    contract = orchestrator.AcceptanceContract(required_new_files={'test.py'})
    repo_context = MagicMock()
    repo_context.source_index = {'test.py': MagicMock()}
    repo_context.test_index = {}
    
    generated = {'test.py': 'print("hello")'}
    valid, err = orchestrator.validate_generated_manifest(generated, contract, repo_context)
    assert not valid
    assert 'ya existía en el estado inicial' in err or 'ya existia' in err

def test_setup_py_parsing():
    content = """
from setuptools import setup
setup(
    name='my_pkg',
    install_requires=['requests', 'pytest'],
    extras_require={'dev': ['black']},
    python_requires='>=3.10'
)
"""
    parsed = orchestrator.parse_setup_py(content)
    assert 'requests' in parsed['install_requires']
    assert 'pytest' in parsed['install_requires']
    assert 'black' in parsed['extras_require']['dev']
    assert parsed['python_requires'] == '>=3.10'

def test_build_mypy_scope_cluster():
    generated = {'test.py': ''}
    repo_context = MagicMock()
    repo_context.structured_config.mypy_targets = []
    
    repo_context.source_index = {
        'test.py': MagicMock(
            imported_by=['consumer.py'],
            imported_files=['dependency.py'],
            tested_by=['test_test.py'],
            tests_for=['unrelated.py']
        )
    }
    repo_context.test_index = {}
    
    scope = orchestrator.build_mypy_scope(generated, repo_context)
    for file in ['test.py', 'consumer.py', 'dependency.py', 'test_test.py', 'unrelated.py']:
        assert file in scope
        
    repo_context.source_index['test.py'].imported_by.extend(['vulture_whitelist.py', 'README.md'])
    scope2 = orchestrator.build_mypy_scope(generated, repo_context)
    assert 'vulture_whitelist.py' not in scope2
    assert 'README.md' not in scope2

def test_prompt_budget_reserve_fixed():
    budget = orchestrator.PromptBudget(max_input_tokens=1000, reserved_output_tokens=100)
    assert budget.remaining == 900
    assert budget.can_add(900)
    assert not budget.can_add(901)
    
    budget.add(500)
    assert budget.remaining == 400

@patch('orchestrator.RuntimeClients')
def test_arch_doc_updater_signature(mock_runtime):
    mock_runtime.ai_client.models.generate_content.return_value = MagicMock(text='test')
    try:
        orchestrator.agent_update_architecture_doc(
            issue_id=1,
            title='Test',
            description='Test',
            design={},
            generated_files={'test.py': ''},
            current_arch_doc='Test',
            gate_results=[],
            git_diff='+ test',
            runtime=mock_runtime
        )
    except TypeError as e:
        pytest.fail(f'Firma incorrecta: {e}')

def test_agent_implement_code_calls_generate():
    import orchestrator
    mock_runtime = MagicMock()
    mock_response = MagicMock()
    mock_response.text = '```python\nprint("test")\n```'
    mock_runtime.ai_client.models.generate_content.return_value = mock_response
    
    contract = orchestrator.FileContract(
        filepath='test.py',
        purpose='test',
        required_exports=set(),
        forbidden_imports=set()
    )
    
    action = {
        'filepath': 'test.py',
        'operation': 'CREATE',
        'signatures': {},
        'instructions': 'test'
    }
    
    repo_context = MagicMock()
    mock_context_manager = MagicMock()
    
    res = orchestrator.agent_implement_code(action, contract, {}, {}, repo_context, mock_runtime, mock_context_manager)
    
    assert res == 'print("test")'
    mock_runtime.ai_client.models.generate_content.assert_called_once()


def test_calls_receive_context_manager_and_feedback():
    import orchestrator
    mock_runtime = MagicMock()
    mock_response = MagicMock(text='{"test": "test"}')
    mock_runtime.ai_client.models.generate_content.return_value = mock_response
    mock_context_manager = MagicMock(spec=orchestrator.RepositoryContextManager)
    
    contract = orchestrator.FileContract(filepath='test.py', purpose='t', required_exports=set(), forbidden_imports=set())
    repo_context = MagicMock()
    
    # Should not raise TypeError and receive correct kwargs
    res1 = orchestrator.agent_analyze_and_design("T", "D", MagicMock(), repo_context, mock_runtime, context_manager=mock_context_manager, design_feedback="test feedback")
    res2 = orchestrator.agent_implement_code({'filepath': 'test.py', 'operation': 'MODIFY', 'signatures': {}, 'instructions': ''}, contract, {}, {}, repo_context, mock_runtime, context_manager=mock_context_manager, feedback="test feedback2")
    res3 = orchestrator.agent_generate_tests({'filepath': 'test.py', 'operation': 'MODIFY', 'signatures': {}, 'instructions': ''}, contract, {}, "D", repo_context, "pytest", mock_runtime, context_manager=mock_context_manager, feedback="test feedback3")
    
    # If it didn't throw TypeError, signature is correct
    assert True


def test_agent_security_audit_no_name_error():
    import orchestrator
    mock_runtime = MagicMock()
    mock_response = MagicMock(text='{"approved": true, "findings": []}')
    mock_runtime.ai_client.models.generate_content.return_value = mock_response
    
    contract = orchestrator.AcceptanceContract(required_modified_files={'test.py'})
    repo_context = MagicMock()
    repo_context.dependency_files = {'requirements.txt': 'pytest==7.0.0\nrequests'}
    repo_context.structured_config.dependencies = []
    repo_context.structured_config.dev_dependencies = []
    repo_context.structured_config.model_dump_json.return_value = "{}"
    repo_context.quality_policy.model_dump_json.return_value = "{}"
    
    # Run it
    res = orchestrator.agent_security_audit({}, {"test.py": "print(1)"}, contract, mock_runtime, repo_context)
    
    assert res.approved == True
    mock_runtime.ai_client.models.generate_content.assert_called_once()
