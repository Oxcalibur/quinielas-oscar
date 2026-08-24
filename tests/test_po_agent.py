import os
import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Añadir el raíz del proyecto al path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import po_agent

@pytest.fixture
def mock_get_git_info():
    with patch('po_agent.get_git_info') as mock:
        yield mock

@pytest.fixture
def mock_subprocess():
    with patch('po_agent.subprocess.check_output') as mock:
        yield mock

class TestPOAgentBehavioral:
    
    def test_b1_pydantic_response_validation(self, mock_get_git_info, mock_subprocess, tmp_path):
        """B1: Pydantic rejects malformed JSON missing mandatory fields before render/write."""
        config = {"workspace": str(tmp_path), "repo": "Oxcalibur/bookai-engine", "branch": "main"}
        args = MagicMock(requirements="docs/PRODUCT_SPEC.md", dry_run=True)
        
        with patch("po_agent.verify_target_identity", return_value={"req_path": "fake.md", "workspace": str(tmp_path), "target_repo": "Oxcalibur/bookai-engine"}):
            with patch("builtins.open", MagicMock()):
                with patch("po_agent.CodebaseScanner.get_existing_vocabulary", return_value=""):
                    with patch("po_agent.ai_client.models.generate_content") as mock_generate:
                        # Malformed missing 'proposed_issues'
                        mock_generate.return_value = MagicMock(text='{"epic_title": "Fake Epic", "epic_justification": "Just", "adversarial_self_audit": []}')
                        with pytest.raises(SystemExit) as exc_info:
                            po_agent.propose_backlog(args)
                        assert exc_info.value.code == 1

    def test_b2_audit_fail_blocks_publication(self, tmp_path):
        """B2: Audit contract gate (a: one required check missing, b: FAIL verdict) blocks publication."""
        args = MagicMock(requirements="docs/PRODUCT_SPEC.md", dry_run=False)
        
        # Test A: Missing check
        valid_audit_missing_check = [{"check": c, "verdict": "PASS", "evidence": "E", "affected_issue": "N/A"} for c in po_agent.REQUIRED_AUDIT_CHECKS[:-1]]
        json_a = json.dumps({
            "epic_title": "Epic", "epic_justification": "Just", "proposed_issues": [],
            "adversarial_self_audit": valid_audit_missing_check
        })
        
        # Test B: One check FAIL
        valid_audit_with_fail = [{"check": c, "verdict": "PASS", "evidence": "E", "affected_issue": "N/A"} for c in po_agent.REQUIRED_AUDIT_CHECKS]
        valid_audit_with_fail[0]["verdict"] = "FAIL"
        json_b = json.dumps({
            "epic_title": "Epic", "epic_justification": "Just", "proposed_issues": [],
            "adversarial_self_audit": valid_audit_with_fail
        })
        
        for payload in [json_a, json_b]:
            with patch("po_agent.verify_target_identity", return_value={"req_path": "fake.md", "workspace": str(tmp_path), "target_repo": "fake"}):
                with patch("builtins.open", MagicMock()):
                    with patch("po_agent.CodebaseScanner.get_existing_vocabulary", return_value=""):
                        with patch("po_agent.ai_client.models.generate_content", return_value=MagicMock(text=payload)):
                            with patch("po_agent.get_github_repo") as mock_repo:
                                with pytest.raises(SystemExit) as exc_info:
                                    po_agent.propose_backlog(args)
                                assert exc_info.value.code == 1
                                mock_repo.assert_not_called()

    def test_b3_and_b14_complete_round_trip_fidelity(self, tmp_path):
        """B3 & B14: Complete production round trip."""
        issue_data = {
            "title": "Sentinel Title",
            "purpose": "Sentinel Purpose",
            "scope": "Sentinel Scope",
            "out_of_scope": "Sentinel Out",
            "expected_behavior": "Sentinel Behavior",
            "acceptance_criteria": "Sentinel AC",
            "constraints": "Sentinel Constraints",
            "preservation_requirements": "Sentinel Preservation",
            "relevant_context": "Sentinel Context",
            "unresolved_product_decisions": "Sentinel Ambiguity",
            "source_inconsistencies": "Sentinel Inconsistencies",
            "implementation_open_choices": "Sentinel Choices",
            "source_requirements": "Sentinel Reqs",
            "depends_on": "NONE",
            "priority": "high",
            "estimated_files": ["sentinel.py"]
        }
        
        proposal = po_agent.BacklogProposal(
            epic_title="Epic",
            epic_justification="Just",
            proposed_issues=[po_agent.ProposedSubIssue(**issue_data)],
            adversarial_self_audit=[po_agent.AdversarialAuditFinding(check=c, verdict="PASS", evidence="E", affected_issue="N/A") for c in po_agent.REQUIRED_AUDIT_CHECKS]
        )
        rendered = po_agent.render_epic_body(proposal)
        
        args = MagicMock(approve_epic=1, dry_run=False)
        with patch("po_agent.resolve_target_config", return_value={"repo": "fake/repo", "workspace": str(tmp_path), "branch": "main"}):
            with patch("po_agent.verify_target_identity"):
                repo = MagicMock()
                with patch("po_agent.get_github_repo", return_value=repo):
                    epic_issue = MagicMock()
                    label_mock = MagicMock(name="gate:approved")
                    label_mock.name = "gate:approved" # name gets overridden in constructor
                    epic_issue.labels = [label_mock]
                    epic_issue.body = rendered
                    repo.get_issue.return_value = epic_issue
                    repo.get_issues.return_value = [] # no children
                    
                    po_agent.approve_and_deploy_backlog(args)
                    
                    assert repo.create_issue.call_count == 1
                    created_body = repo.create_issue.call_args[1]["body"]
                    created_title = repo.create_issue.call_args[1]["title"]
                    created_labels = repo.create_issue.call_args[1]["labels"]
                    for key, val in issue_data.items():
                        if key == "title":
                            assert val in created_title
                        elif key == "priority":
                            assert f"priority:{val}" in created_labels
                        elif isinstance(val, list):
                            assert val[0] in created_body
                        else:
                            assert val in created_body

    def test_b4_requirements_containment(self, mock_get_git_info, mock_subprocess, tmp_path):
        """B4: Reject absolute, escaping, prefix-collision, or symlink requirement paths."""
        config = {"workspace": str(tmp_path), "repo": "fake/repo", "branch": "main"}
        mock_get_git_info.side_effect = lambda p: {"root": str(tmp_path) if p == str(tmp_path) else "/platform", "origin": "fake/repo", "head": "head", "branch": "main"}
        mock_subprocess.return_value = ""
    
        # valid internal path
        req_file = tmp_path / "docs" / "SPEC.md"
        req_file.parent.mkdir(parents=True, exist_ok=True)
        req_file.write_text("fake")
        ret = po_agent.verify_target_identity(config, "docs/SPEC.md")
        assert ret["req_path"] == str(req_file.resolve())
        
        # Test escaping
        with pytest.raises(SystemExit) as exc_info:
            po_agent.verify_target_identity(config, "../outside.md")
        assert exc_info.value.code == 1

        # Test absolute outside
        with pytest.raises(SystemExit) as exc_info:
            po_agent.verify_target_identity(config, "/etc/passwd" if os.name != 'nt' else "C:\\Windows\\System32\\cmd.exe")
        assert exc_info.value.code == 1
        
        # Test prefix collision
        collision_path = str(tmp_path) + "-other"
        with pytest.raises(SystemExit) as exc_info:
            po_agent.verify_target_identity(config, os.path.join(collision_path, "req.md"))
        assert exc_info.value.code == 1

        # Test symlink escape
        try:
            sym_dir = tmp_path / "sym_target"
            sym_dir.mkdir(parents=True, exist_ok=True)
            outside_file = sym_dir / "outside.md"
            outside_file.write_text("out")
            
            link_path = tmp_path / "docs" / "link.md"
            os.symlink(str(outside_file), str(link_path))
            
            with pytest.raises(SystemExit) as exc_info:
                po_agent.verify_target_identity(config, "docs/link.md")
            assert exc_info.value.code == 1
        except OSError:
            pytest.skip("Symlink creation not supported in this test environment without admin privileges.")

    def test_b5_wrong_target_branch_fails(self, mock_get_git_info, tmp_path):
        """B5: Fails if current branch is not the declared base branch."""
        config = {"workspace": str(tmp_path), "repo": "fake/repo", "branch": "main"}
        mock_get_git_info.side_effect = lambda p: {"root": str(tmp_path) if p == str(tmp_path) else "/platform", "origin": "fake/repo", "head": "head", "branch": "feature/wrong"}
        
        with pytest.raises(SystemExit) as exc_info:
            po_agent.verify_target_identity(config)
        assert exc_info.value.code == 1

    def test_b6_dirty_target_fails(self, mock_get_git_info, mock_subprocess, tmp_path):
        """B6: Fails if target working tree is dirty or cannot be verified (fail-closed)."""
        config = {"workspace": str(tmp_path), "repo": "fake/repo", "branch": "main"}
        mock_get_git_info.side_effect = lambda p: {"root": str(tmp_path) if p == str(tmp_path) else "/platform", "origin": "fake/repo", "head": "head", "branch": "main"}
        
        # Test dirty
        def subprocess_mock_dirty(*args, **kwargs):
            if "status" in args[0]:
                return " M modified.py\n"
            return ""
        mock_subprocess.side_effect = subprocess_mock_dirty
        with pytest.raises(SystemExit) as exc_info:
            po_agent.verify_target_identity(config)
        assert exc_info.value.code == 1

        # Test error/timeout
        def subprocess_mock_error(*args, **kwargs):
            if "status" in args[0]:
                import subprocess
                raise subprocess.CalledProcessError(1, "git status")
            return ""
        mock_subprocess.side_effect = subprocess_mock_error
        with pytest.raises(SystemExit) as exc_info:
            po_agent.verify_target_identity(config)
        assert exc_info.value.code == 1

    def test_b7_mutating_path_strong_target_validation(self, tmp_path):
        """B7: All mutating paths execute strong target verification before mutation."""
        # Refine issue
        args_refine = MagicMock(authorize_refinement=True, dry_run=False, refine_issue=1, pm_report="Bad")
        with patch("po_agent.resolve_target_config", return_value={"repo": "fake", "workspace": str(tmp_path), "branch": "main"}):
            with patch("po_agent.verify_target_identity") as mock_verify:
                mock_verify.side_effect = SystemExit(1)
                with patch("po_agent.get_github_repo") as repo_mock:
                    with pytest.raises(SystemExit):
                        po_agent.refine_issue(args_refine)
                    repo_mock.assert_not_called()

        # Approve epic
        args_approve = MagicMock(approve_epic=1, dry_run=False)
        with patch("po_agent.resolve_target_config", return_value={"repo": "fake", "workspace": str(tmp_path), "branch": "main"}):
            with patch("po_agent.verify_target_identity") as mock_verify:
                mock_verify.side_effect = SystemExit(1)
                with patch("po_agent.get_github_repo") as repo_mock:
                    with pytest.raises(SystemExit):
                        po_agent.approve_and_deploy_backlog(args_approve)
                    repo_mock.assert_not_called()

    def test_b8_label_provisioning(self):
        """B8: Label creation failure stops before Issue creation."""
        repo = MagicMock()
        repo.get_label.side_effect = Exception("Not found")
        repo.create_label.side_effect = Exception("API Error")
        
        with pytest.raises(SystemExit) as exc_info:
            po_agent.create_labels_if_not_exist(repo, False)
        assert exc_info.value.code == 1

    def test_idempotency_scenarios(self, tmp_path):
        """I1-I6: Full idempotency testing (Match, count mismatch, duplicate)."""
        args = MagicMock(approve_epic=1, dry_run=False)
        with patch("po_agent.resolve_target_config", return_value={"repo": "fake", "workspace": str(tmp_path), "branch": "main"}):
            with patch("po_agent.verify_target_identity"):
                repo = MagicMock()
                with patch("po_agent.get_github_repo", return_value=repo):
                    epic_issue = MagicMock()
                    label_mock = MagicMock()
                    label_mock.name = "gate:approved"
                    epic_issue.labels = [label_mock]
                    
                    s1 = po_agent.ProposedSubIssue(title="A", purpose="P", scope="S", expected_behavior="E", acceptance_criteria="AC", source_requirements="R", depends_on="NONE", priority="high")
                    s2 = po_agent.ProposedSubIssue(title="B", purpose="P", scope="S", expected_behavior="E", acceptance_criteria="AC", source_requirements="R", depends_on="NONE", priority="high")
                    s3 = po_agent.ProposedSubIssue(title="C", purpose="P", scope="S", expected_behavior="E", acceptance_criteria="AC", source_requirements="R", depends_on="NONE", priority="high")
                    
                    fp1 = po_agent.get_issue_fingerprint(s1)
                    fp2 = po_agent.get_issue_fingerprint(s2)
                    fp3 = po_agent.get_issue_fingerprint(s3)
                    
                    epic_issue.body = f"<!-- BACKLOG_METADATA_START\n[{s1.model_dump_json()}, {s2.model_dump_json()}, {s3.model_dump_json()}]\nBACKLOG_METADATA_END -->"
                    repo.get_issue.return_value = epic_issue

                    # I1 MATCHING FULL DEPLOY
                    c1 = MagicMock(body=f"<!-- PO_PARENT_EPIC=1 PO_CHILD_INDEX=1 FINGERPRINT={fp1} -->")
                    c2 = MagicMock(body=f"<!-- PO_PARENT_EPIC=1 PO_CHILD_INDEX=2 FINGERPRINT={fp2} -->")
                    c3 = MagicMock(body=f"<!-- PO_PARENT_EPIC=1 PO_CHILD_INDEX=3 FINGERPRINT={fp3} -->")
                    repo.get_issues.return_value = [c1, c2, c3]
                    po_agent.approve_and_deploy_backlog(args)
                    repo.create_issue.assert_not_called()
                    
                    # I2 FULL COUNT BUT ONE FINGERPRINT MISMATCH
                    c2_bad = MagicMock(body=f"<!-- PO_PARENT_EPIC=1 PO_CHILD_INDEX=2 FINGERPRINT=badfp -->")
                    repo.get_issues.return_value = [c1, c2_bad, c3]
                    with pytest.raises(SystemExit):
                        po_agent.approve_and_deploy_backlog(args)
                        
                    # I3 PARTIAL MATCH
                    repo.get_issues.return_value = [c1, c3]
                    repo.create_issue.reset_mock()
                    po_agent.approve_and_deploy_backlog(args)
                    assert repo.create_issue.call_count == 1
                    assert "Task 2: B" in repo.create_issue.call_args[1]["title"]
                    
                    # I4 PARTIAL MISMATCH
                    repo.get_issues.return_value = [c1, c2_bad]
                    with pytest.raises(SystemExit):
                        po_agent.approve_and_deploy_backlog(args)
                        
                    # I5 DUPLICATE CHILD INDEX
                    repo.get_issues.return_value = [c1, c1]
                    with pytest.raises(SystemExit):
                        po_agent.approve_and_deploy_backlog(args)

    def test_i6_contract_field_change_invalidates_fingerprint(self):
        """I6: Fingerprint changes when semantic fields change."""
        base = {"title":"A", "purpose":"P", "scope":"S", "expected_behavior":"E", "acceptance_criteria":"AC", "source_requirements":"R", "depends_on":"NONE", "priority":"high"}
        sub1 = po_agent.ProposedSubIssue(**base)
        fp1 = po_agent.get_issue_fingerprint(sub1)
        
        # Priority
        sub2 = po_agent.ProposedSubIssue(**{**base, "priority": "low"})
        assert fp1 != po_agent.get_issue_fingerprint(sub2)
        
        # Unresolved product decisions
        sub3 = po_agent.ProposedSubIssue(**{**base, "unresolved_product_decisions": "ambiguity"})
        assert fp1 != po_agent.get_issue_fingerprint(sub3)
        
        # Estimated files shouldn't affect
        sub4 = po_agent.ProposedSubIssue(**{**base, "estimated_files": ["ignored.py"]})
        assert fp1 == po_agent.get_issue_fingerprint(sub4)

    def test_b11_malformed_approved_metadata(self, tmp_path):
        """B11: Malformed metadata fails deploy."""
        args = MagicMock(approve_epic=1, dry_run=False)
        with patch("po_agent.resolve_target_config", return_value={"repo": "fake", "workspace": str(tmp_path), "branch": "main"}):
            with patch("po_agent.verify_target_identity"):
                repo = MagicMock()
                with patch("po_agent.get_github_repo", return_value=repo):
                    epic_issue = MagicMock()
                    label_mock = MagicMock()
                    label_mock.name = "gate:approved"
                    epic_issue.labels = [label_mock]
                    epic_issue.body = "<!-- BACKLOG_METADATA_START\n[{\"title\": \"A\"}]\nBACKLOG_METADATA_END -->"
                    repo.get_issue.return_value = epic_issue
                    
                    with pytest.raises(SystemExit):
                        po_agent.approve_and_deploy_backlog(args)

    def test_b12_dependency_resolution(self):
        """B12: Structural dependency validation."""
        base = {"purpose": "P", "scope": "S", "expected_behavior": "E", "acceptance_criteria": "A", "source_requirements": "R", "priority": "high"}
        
        # Unknown dep
        with pytest.raises(ValueError, match="does not resolve"):
            po_agent.validate_proposed_issues_deterministic([po_agent.ProposedSubIssue(title="A", depends_on="UNKNOWN", **base)])
        
        # Self dep
        with pytest.raises(ValueError, match="Self-dependency"):
            po_agent.validate_proposed_issues_deterministic([po_agent.ProposedSubIssue(title="A", depends_on="A", **base)])
            
        # Wildcard dep
        with pytest.raises(ValueError, match="Wildcard dependency"):
            po_agent.validate_proposed_issues_deterministic([po_agent.ProposedSubIssue(title="A", depends_on="ALL AGENTS", **base)])
            
        # Cycle dep
        with pytest.raises(ValueError, match="Dependency cycle"):
            po_agent.validate_proposed_issues_deterministic([
                po_agent.ProposedSubIssue(title="A", depends_on="B", **base),
                po_agent.ProposedSubIssue(title="B", depends_on="A", **base)
            ])

    def test_b13_dry_run_end_to_end_zero_write(self, tmp_path):
        """B13: DRY RUN performs zero writes."""
        args = MagicMock(requirements="docs/PRODUCT_SPEC.md", dry_run=True)
        valid_audit = [{"check": c, "verdict": "PASS", "evidence": "E", "affected_issue": "N/A"} for c in po_agent.REQUIRED_AUDIT_CHECKS]
        valid_json = json.dumps({
            "epic_title": "Fake", "epic_justification": "Fake",
            "proposed_issues": [{"title": "A", "purpose": "P", "scope": "S", "expected_behavior": "E", "acceptance_criteria": "A", "source_requirements": "R", "depends_on": "NONE", "priority": "high"}],
            "adversarial_self_audit": valid_audit
        })
        
        with patch("po_agent.resolve_target_config", return_value={"repo": "fake/repo", "workspace": str(tmp_path), "branch": "main"}):
            with patch("po_agent.verify_target_identity", return_value={"req_path": "fake.md", "workspace": str(tmp_path), "target_repo": "fake/repo"}):
                with patch("builtins.open", MagicMock()):
                    with patch("po_agent.CodebaseScanner.get_existing_vocabulary", return_value=""):
                        with patch("po_agent.ai_client.models.generate_content", return_value=MagicMock(text=valid_json)):
                            with patch("po_agent.get_github_repo") as mock_repo:
                                po_agent.propose_backlog(args)
                                mock_repo.assert_not_called()

    def test_b15_refine_governance(self):
        """B15: Autonomous refine blocked by default."""
        args = MagicMock(authorize_refinement=False)
        with pytest.raises(SystemExit) as exc_info:
            po_agent.refine_issue(args)
        assert exc_info.value.code == 1

    def test_g1_generic_existing_repository_context(self, tmp_path):
        """G1 & F2: Codebase scanner extracts funcs, classes, tests, configs, and arch/design docs."""
        (tmp_path / "src").mkdir()
        (tmp_path / "tests").mkdir()
        (tmp_path / "docs").mkdir()
        
        code_file = tmp_path / "src" / "billing.py"
        code_file.write_text("class InvoiceService:\n    pass\n\ndef calculate_tax(amount):\n    pass", encoding="utf-8")
        
        test_file = tmp_path / "tests" / "test_billing.py"
        test_file.write_text("def test_tax(): pass", encoding="utf-8")
        
        req_file = tmp_path / "pyproject.toml"
        req_file.write_text("[tool]", encoding="utf-8")
        
        readme = tmp_path / "README.md"
        readme.write_text("# Test", encoding="utf-8")
        
        arch = tmp_path / "docs" / "ARCHITECTURE.md"
        arch.write_text("Arch", encoding="utf-8")
        
        scanner = po_agent.CodebaseScanner(str(tmp_path))
        vocab = scanner.get_existing_vocabulary()
        
        assert "Class: InvoiceService (in" in vocab
        assert "Func: calculate_tax(amount) (in" in vocab
        assert "Project files: pyproject.toml" in vocab
        assert "Docs: README.md" in vocab
        assert "ARCHITECTURE.md" in vocab
        assert "Test files: 1 files found" in vocab
        assert "BookAI" not in vocab

    def test_f1_production_prompt_is_domain_generic(self):
        """F1: Ensure prompt instructions are generic and not hardcoded to BookAI."""
        import inspect
        source = inspect.getsource(po_agent.propose_backlog)
        
        forbidden_literals = [
            "StoryBible",
            "BookAI",
            "RF-02",
            "RF-03",
            "Reader Score",
            "Editor Score",
            "Google Docs"
        ]
        
        for literal in forbidden_literals:
            assert literal not in source, f"Production prompt contains domain-specific literal: {literal}"

    def test_t1_enumeration_fidelity(self):
        """T1: Assert prompt forbids losing mandatory enumerated dimensions and replacing with etc."""
        import inspect
        source = inspect.getsource(po_agent.propose_backlog)
        assert "ENUMERATED SOURCE FIDELITY" in source
        assert "EVERY enumerated dimension must remain explicit" in source
        assert "etc." in source
        assert "shortened, summarized or replaced with" in source

    def test_t2_dependency_consumption(self):
        """T2: Assert prompt requires comparing Issue capability consumption against depends_on."""
        import inspect
        source = inspect.getsource(po_agent.propose_backlog)
        assert "DEPENDENCY CONSUMPTION AUDIT" in source
        assert "consumes capability X AND another proposed Issue provides X AND the provider is absent from depends_on" in source

    def test_t3_acceptance_vs_transition(self):
        """T3: Assert prompt explicitly states that an acceptance condition does not itself define a failure workflow transition."""
        import inspect
        source = inspect.getsource(po_agent.propose_backlog)
        assert "ACCEPTANCE CONDITION DOES NOT IMPLY FAILURE TRANSITION" in source
        assert "does NOT automatically define what the workflow must do when that condition is not satisfied" in source
        assert "record the missing transition in unresolved_product_decisions" in source

    def test_t4_milestone_completeness(self):
        """T4: Assert prompt requires every explicitly enumerated mandatory human gate/checkpoint to remain individually observable."""
        import inspect
        source = inspect.getsource(po_agent.propose_backlog)
        assert "EXPLICIT MILESTONE COMPLETENESS" in source
        assert "mandatory human gates, approvals, checkpoints, milestones, or confirmation points" in source
        assert "remain individually observable" in source
