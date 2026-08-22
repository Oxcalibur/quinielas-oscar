import os
import sys
import json
import logging
from unittest.mock import MagicMock, patch

sys.path.append('g:/Mi unidad/Olivia/sdlc_agent_prototype/quinielas-oscar')
import orchestrator
from orchestrator_core.prompt_budget import PreflightError

# Mock objects
action = {"filepath": "src/a.py", "operation": "MODIFY", "signatures": "", "instructions": "do it"}
file_contract = MagicMock()
file_contract.model_dump_json.return_value = '{"foo": "bar"}'
repo_context = MagicMock()
context_manager = MagicMock()
context_manager.get_file_content.return_value = "print('hello')"

runtime = MagicMock()
runtime.ai_client.models.generate_content.return_value = MagicMock(text="```python\nprint('done')\n```")

# C001
design = {"context": {"small": "context"}}
feedback = "small feedback"
runtime.ai_client.models.generate_content.reset_mock()
orchestrator.agent_implement_code(action, file_contract, design, {}, repo_context, runtime, context_manager, feedback)
print("C001 small optional: PASS")

# C002
design = {"context": {"huge": "x" * 500000}}
feedback = "y" * 500000
runtime.ai_client.models.generate_content.reset_mock()
orchestrator.agent_implement_code(action, file_contract, design, {}, repo_context, runtime, context_manager, feedback)
prompt_args = runtime.ai_client.models.generate_content.call_args[1]["contents"]
assert "Actuas como un Software Engineer" in prompt_args
assert "FileContract: {\"foo\": \"bar\"}" in prompt_args
assert "Action: filepath: src/a.py" in prompt_args
assert "Codigo Actual: print('hello')" in prompt_args
print("C002 huge optional: PASS")

# C003
file_contract.model_dump_json.return_value = '{"huge": "' + "z" * 500000 + '"}'
runtime.ai_client.models.generate_content.reset_mock()
try:
    orchestrator.agent_implement_code(action, file_contract, design, {}, repo_context, runtime, context_manager, feedback)
    print("C003 huge mandatory: FAIL (Did not raise PreflightError)")
except PreflightError:
    assert runtime.ai_client.models.generate_content.call_count == 0
    print("C003 huge mandatory: PASS")
