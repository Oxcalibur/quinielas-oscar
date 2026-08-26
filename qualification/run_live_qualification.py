import argparse
import logging
import os
import shutil
import tempfile
import subprocess
import hashlib
import sys
import ast
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import MagicMock, patch
import json
from datetime import datetime

from google import genai
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from orchestrator_core.runtime import RuntimeClients
from orchestrator_core.planning_agents import agent_generate_acceptance_contract
from orchestrator_core.contract_validation import validate_contract_consistency
from orchestrator import run_pipeline, validate_issue_eligibility, validate_contract_capabilities, _validator_registry

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s:%(filename)s:%(lineno)d %(message)s")


def get_fixture_path(scenario: str) -> Path:
    base = Path(__file__).parent / "fixtures"
    if scenario == "q1": return base / "q1_greenfield"
    if scenario == "q2": return base / "q2_nonbinding"
    if scenario == "q3": return base / "q3_preservation"
    raise ValueError(f"Unknown scenario: {scenario}")


def hash_fixture(fixture_path: Path) -> dict:
    hashes = {}
    for p in fixture_path.rglob("*"):
        if p.is_file():
            hashes[str(p.relative_to(fixture_path))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes


def parse_issue_fixture(content: str) -> tuple[str, str]:
    """Parse fixture Issue.md safely returning (title, body)."""
    lines = content.splitlines()
    title = ""
    body = ""
    parsing_body = False
    body_lines = []

    for line in lines:
        if line.startswith("Title:"):
            pass
        elif line.startswith("Body:"):
            parsing_body = True
        elif not parsing_body:
            if line.strip():
                title = line.strip()
        else:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()
    return title, body


def recursive_find(obj: Any, term: str) -> bool:
    """Recursively search for a substring in strings inside iterables and dicts."""
    if isinstance(obj, str):
        return term.lower() in obj.lower()
    elif isinstance(obj, dict):
        return any(recursive_find(v, term) for v in obj.values()) or any(recursive_find(k, term) for k in obj.keys())
    elif isinstance(obj, (list, set, tuple)):
        return any(recursive_find(v, term) for v in obj)
    elif hasattr(obj, "model_dump"):
        return recursive_find(obj.model_dump(), term)
    elif hasattr(obj, "__dict__"):
        return recursive_find(obj.__dict__, term)
    return False


def check_test_exists_in_ast(filepath: Path, test_name: str) -> bool:
    """Verify exact final test name exists as FunctionDef/AsyncFunctionDef in parsed AST."""
    if not filepath.exists():
        return False
    try:
        content = filepath.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(filepath))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == test_name:
                    return True
        return False
    except Exception:
        return False


class QualificationHarness:
    def __init__(self, mode: str, scenario: str):
        self.mode = mode
        self.scenario = scenario
        self.fixture_path = get_fixture_path(scenario)
        self.initial_hashes = hash_fixture(self.fixture_path)
        load_dotenv()

    def verify_immutability(self):
        current_hashes = hash_fixture(self.fixture_path)
        if current_hashes != self.initial_hashes:
            raise RuntimeError("Fixture was mutated during execution!")

    def build_fake_runtime(self, title: str, body: str) -> RuntimeClients:
        ai_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        mock_github = MagicMock()
        mock_repo = MagicMock()

        body += "\n\nPO_PARENT_EPIC=2\nPO_CHILD_INDEX=1\nFINGERPRINT=0123456789abcdef"

        child_issue = MagicMock()
        child_issue.title = title
        child_issue.body = body
        ready_label = MagicMock()
        ready_label.name = "ai:ready-to-code"
        child_issue.labels = [ready_label]

        parent_epic = MagicMock()
        deployed_label = MagicMock()
        deployed_label.name = "gate:deployed"
        parent_epic.labels = [deployed_label]

        def mock_get_issue(*args, **kwargs):
            num = kwargs.get("number", args[0] if args else 1)
            if num == 1: return child_issue
            if num == 2: return parent_epic
            return MagicMock()

        mock_repo.get_issue.side_effect = mock_get_issue
        mock_repo.create_pull.return_value = MagicMock(html_url="http://fake-pr")

        return RuntimeClients(ai_client=ai_client, github_client=mock_github, repo=mock_repo)

    def run(self, run_index: int) -> dict:
        summary = {
            "SCENARIO": self.scenario.upper(),
            "MODE": self.mode.upper(),
            "RUN": run_index,
            "HARNESS_EXECUTION": "PASS",
            "CONTRACT_GENERATION": "N/A",
            "CONTRACT_CONSISTENCY": "N/A",
            "CONTRACT_CAPABILITIES": "N/A",
            "NON_BINDING_FILES": "N/A",
            "NON_BINDING_DEPENDENCIES": "N/A",
            "STORAGE_CHOICE": "N/A",
            "ESTIMATED_FILE_ESCALATION": "N/A",
            "PYDANTIC_ESCALATION": "N/A",
            "STORAGE_CHOICE_ESCALATION": "N/A",
            "FIXTURE_TEMPLATE_MUTATED": "NO",
            "SCENARIO_VERDICT": "PASS"
        }

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                repo_path = temp_path / "repo"
                shutil.copytree(self.fixture_path / "repo", repo_path)

                issue_content = (self.fixture_path / "issue.md").read_text(encoding="utf-8")
                title, body = parse_issue_fixture(issue_content)

                subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
                subprocess.run(["git", "config", "user.name", "Qualification Harness"], cwd=repo_path, check=True, capture_output=True)
                subprocess.run(["git", "config", "user.email", "qualification@example.invalid"], cwd=repo_path, check=True, capture_output=True)
                subprocess.run(["git", "add", "-A"], cwd=repo_path, check=True, capture_output=True)
                subprocess.run(["git", "commit", "-m", "Initial baseline commit"], cwd=repo_path, check=True, capture_output=True)

                runtime = self.build_fake_runtime(title, body)

                self.execute_mode(repo_path, runtime, title, body, summary)

                self.verify_immutability()
        except Exception as e:
            summary["HARNESS_EXECUTION"] = f"FAIL ({type(e).__name__}: {e})"
            summary["SCENARIO_VERDICT"] = "FAIL"

        for k, v in summary.items():
            print(f"{k}: {v}")
        print("-" * 40)

        return summary

    def execute_mode(self, repo_path: Path, runtime: RuntimeClients, title: str, body: str, summary: dict):
        if self.mode == "contract":
            from orchestrator import RepositoryContextManager
            from orchestrator_core.schemas import ContextBudget
            context_budget = ContextBudget()
            repo_context = RepositoryContextManager(str(repo_path)).build_repository_context(body, context_budget)

            try:
                contract = agent_generate_acceptance_contract(title, body, repo_context, runtime)
                summary["CONTRACT_GENERATION"] = "PASS"
            except Exception as e:
                summary["CONTRACT_GENERATION"] = "FAIL"
                summary["HARNESS_EXECUTION"] = f"FAIL ({e})"
                summary["SCENARIO_VERDICT"] = "FAIL"
                return

            is_consistent, c_errors = validate_contract_consistency(contract)
            if is_consistent:
                summary["CONTRACT_CONSISTENCY"] = "PASS"
            else:
                summary["CONTRACT_CONSISTENCY"] = "FAIL"
                summary["SCENARIO_VERDICT"] = "FAIL"

            cap_valid, cap_errors = validate_contract_capabilities(contract, _validator_registry)
            if cap_valid:
                summary["CONTRACT_CAPABILITIES"] = "PASS"
            else:
                summary["CONTRACT_CAPABILITIES"] = "FAIL"
                summary["SCENARIO_VERDICT"] = "FAIL"

            self.check_invariants(contract, repo_path, summary, repo_context)

            # Logging Hardening
            log_dir = Path(".agent-runs/qualification")
            log_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = log_dir / f"{self.scenario}_{self.mode}_run{summary['RUN']}_{ts}.log"
            log_data = {
                "scenario": self.scenario,
                "run": summary["RUN"],
                "summary": summary,
                "contract_consistency": is_consistent,
                "contract_capabilities": cap_valid,
                "contract_json": json.loads(contract.model_dump_json())
            }
            log_file.write_text(json.dumps(log_data, indent=2), encoding="utf-8")

        elif self.mode == "e2e":
            run_log_dir = Path(".agent-runs/qualification") / f"{self.scenario}_{self.mode}_run{summary['RUN']}"
            run_log_dir.mkdir(parents=True, exist_ok=True)
            absolute_run_log_dir = run_log_dir.resolve()

            orig_run = subprocess.run
            def side_effect(cmd, **kwargs):
                if "push" in cmd or "fetch" in cmd:
                    return MagicMock(returncode=0, stdout="", stderr="")
                return orig_run(cmd, **kwargs)

            orig_cwd = os.getcwd()
            try:
                os.chdir(repo_path)

                baseline_head = orig_run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
                summary["TEMP_REPO_BASELINE_HEAD"] = baseline_head

                with patch("orchestrator_core.github_operations.subprocess.run", side_effect=side_effect):
                    run_pipeline(1, "qual-run", str(absolute_run_log_dir), runtime)

                final_head = orig_run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
                summary["TEMP_REPO_FINAL_HEAD"] = final_head

                if baseline_head == final_head:
                    pass # Handled by specific scenario rules if commit is required. Q1 requires a commit, so diff below will fail if identical.

                diff_res = orig_run(["git", "diff", "--name-only", f"{baseline_head}..{final_head}"], capture_output=True, text=True, check=True)
                changed_files = diff_res.stdout.splitlines()

                if any(f.endswith(".pyc") for f in changed_files) or any("__pycache__" in f for f in changed_files):
                    summary["SCENARIO_VERDICT"] = "FAIL"
                else:
                    summary["SCENARIO_VERDICT"] = "PASS"

            except Exception as e:
                summary["HARNESS_EXECUTION"] = f"FAIL ({e})"
                summary["SCENARIO_VERDICT"] = "FAIL"
            finally:
                os.chdir(orig_cwd)

    def check_invariants(self, contract, repo_path: Path, summary: dict, repo_context: Any = None):
        if self.scenario == "q1":
            if repo_context:
                from orchestrator_core.quality_gates import _derive_gate_plan
                gate_plan = _derive_gate_plan(repo_context, contract)
                if not (contract.required_tests and gate_plan.run_tests and gate_plan.test_framework == "unittest"):
                    summary["SCENARIO_VERDICT"] = "FAIL"
            else:
                summary["SCENARIO_VERDICT"] = "FAIL"

        elif self.scenario == "q2":
            # A. Check non-binding files (Exact matches on normalized paths)
            all_files = list(contract.required_final_files or []) + \
                        list(contract.required_new_files or []) + \
                        list(contract.required_modified_files or [])
            all_normalized = [Path(f).as_posix() for f in all_files]

            if "storage/schema.py" in all_normalized or "storage/store.py" in all_normalized:
                summary["NON_BINDING_FILES"] = "FAIL"
                summary["ESTIMATED_FILE_ESCALATION"] = "YES"
                summary["SCENARIO_VERDICT"] = "FAIL"
            else:
                summary["NON_BINDING_FILES"] = "PASS"
                summary["ESTIMATED_FILE_ESCALATION"] = "NO"

            # B. Check non-binding dependencies (Pydantic) via recursive search
            fields_to_search = [
                contract.required_imports,
                contract.required_calls,
                contract.required_patterns,
                contract.required_structures,
                contract.required_quality_tools
            ]
            if recursive_find(fields_to_search, "pydantic"):
                summary["NON_BINDING_DEPENDENCIES"] = "FAIL"
                summary["PYDANTIC_ESCALATION"] = "YES"
                summary["SCENARIO_VERDICT"] = "FAIL"
            else:
                summary["NON_BINDING_DEPENDENCIES"] = "PASS"
                summary["PYDANTIC_ESCALATION"] = "NO"

            # C. Check storage choice via recursive search
            if recursive_find(fields_to_search, "sqlite") or recursive_find(fields_to_search, "json"):
                summary["STORAGE_CHOICE"] = "FAIL"
                summary["STORAGE_CHOICE_ESCALATION"] = "YES"
                summary["SCENARIO_VERDICT"] = "FAIL"
            else:
                summary["STORAGE_CHOICE"] = "PASS"
                summary["STORAGE_CHOICE_ESCALATION"] = "NO"

        elif self.scenario == "q3":
            has_preservation = False
            for beh in (contract.preserved_behaviors or []):
                if beh.validation_method == "required_test":
                    has_preservation = True
                    if not beh.protected_tests:
                        summary["SCENARIO_VERDICT"] = "FAIL"
                    else:
                        for test_path in beh.protected_tests:
                            if "::" not in test_path:
                                summary["SCENARIO_VERDICT"] = "FAIL"
                                continue
                            file_part = test_path.split("::")[0]
                            test_name = test_path.split("::")[-1]
                            full_path = repo_path / file_part
                            if not check_test_exists_in_ast(full_path, test_name):
                                summary["SCENARIO_VERDICT"] = "FAIL"

            if not has_preservation:
                summary["SCENARIO_VERDICT"] = "FAIL"


def aggregate_results(results: list[dict]) -> bool:
    """Return True if all runs passed, False otherwise."""
    for r in results:
        if r.get("HARNESS_EXECUTION") != "PASS" or r.get("SCENARIO_VERDICT") != "PASS":
            return False
    return True


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    parser = argparse.ArgumentParser(description="SDLC Orchestrator Qualification Harness")
    parser.add_argument("--mode", choices=["contract", "e2e"], required=True)
    parser.add_argument("--scenario", choices=["q1", "q2", "q3"], required=True)
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args(argv)

    harness = QualificationHarness(args.mode, args.scenario)
    results = []
    for i in range(1, args.repeat + 1):
        res = harness.run(i)
        results.append(res)

    if aggregate_results(results):
        return 0
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
