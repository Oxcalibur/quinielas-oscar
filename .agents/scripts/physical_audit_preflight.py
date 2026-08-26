import os
import sys
import subprocess
import hashlib

def run_cmd(cmd, env=None, cwd=None):
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd)
    return result.stdout, result.stderr, result.returncode

def get_repo_root():
    out, err, code = run_cmd(["git", "rev-parse", "--show-toplevel"])
    if code != 0:
        print(f"Failed to get repo root: {err}")
        sys.exit(1)
    return out.strip()

def capture_git_evidence(repo_root):
    evidence = {}
    cmds = [
        ("status", ["git", "status", "--short"]),
        ("diff_name_status", ["git", "diff", "--name-status"]),
        ("diff_stat", ["git", "diff", "--stat"]),
        ("diff_cached_name_status", ["git", "diff", "--cached", "--name-status"]),
        ("diff_cached_stat", ["git", "diff", "--cached", "--stat"]),
        ("diff_check", ["git", "diff", "--check"]),
        ("diff_cached_check", ["git", "diff", "--cached", "--check"]),
        ("head", ["git", "rev-parse", "HEAD"]),
        ("diff", ["git", "diff"]),
        ("diff_cached", ["git", "diff", "--cached"]),
    ]
    for cmd_name, cmd in cmds:
        out, _, code = run_cmd(cmd, cwd=repo_root)
        evidence[cmd_name] = out
        if cmd_name == "diff_check":
            evidence["diff_check_code"] = code
        if cmd_name == "diff_cached_check":
            evidence["diff_cached_check_code"] = code
    return evidence

def get_diff_hashes(evidence):
    unstaged_hash = hashlib.sha256(evidence["diff"].encode('utf-8')).hexdigest()
    staged_hash = hashlib.sha256(evidence["diff_cached"].encode('utf-8')).hexdigest()
    return unstaged_hash, staged_hash

def capture_filesystem_fingerprint(repo_root):
    fingerprint = {}
    for root, dirs, files in os.walk(repo_root):
        if '.git' in dirs:
            dirs.remove('.git')
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, repo_root)
            try:
                with open(full_path, 'rb') as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()
                fingerprint[rel_path] = file_hash
            except Exception as e:
                fingerprint[rel_path] = f"ERROR: {str(e)}"
    return fingerprint

def get_changed_python_files(evidence):
    files = set()
    for status_out in [evidence["diff_name_status"], evidence["diff_cached_name_status"]]:
        for line in status_out.splitlines():
            if not line.strip():
                continue
            parts = line.split('\t')
            if len(parts) >= 2:
                status = parts[0]
                filepath = parts[-1]
                if filepath.endswith('.py') and status != 'D':
                    files.add(filepath)
    return list(files)

def validate_syntax_in_memory(repo_root, changed_python_files):
    all_passed = True
    for file in changed_python_files:
        full_path = os.path.join(repo_root, file)
        if not os.path.exists(full_path):
            continue
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                source = f.read()
            compile(source, filename=full_path, mode='exec')
        except SyntaxError as e:
            all_passed = False
            print(f"Syntax error in {file}: {e}")
        except Exception as e:
            all_passed = False
            print(f"Error reading/compiling {file}: {e}")
    return all_passed

def main():
    repo_root = get_repo_root()
    before_evidence = capture_git_evidence(repo_root)
    before_unstaged_hash, before_staged_hash = get_diff_hashes(before_evidence)
    before_fingerprint = capture_filesystem_fingerprint(repo_root)

    diff_hygiene_pass = (before_evidence["diff_check_code"] == 0 and before_evidence["diff_cached_check_code"] == 0)

    changed_python_files = get_changed_python_files(before_evidence)
    syntax_validation_pass = validate_syntax_in_memory(repo_root, changed_python_files)

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    test_cmd = [sys.executable, "-B", "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"]
    test_out, test_err, test_code = run_cmd(test_cmd, env=env, cwd=repo_root)
    authoritative_test_gate_pass = (test_code == 0)

    tests_passed = "UNKNOWN"
    tests_failed = "UNKNOWN"

    import re
    last_lines = test_out.strip().splitlines()[-5:] if test_out else []
    for line in reversed(last_lines):
        passed_match = re.search(r'(\d+)\s+passed', line)
        failed_match = re.search(r'(\d+)\s+failed', line)
        if passed_match or failed_match:
            if passed_match:
                tests_passed = passed_match.group(1)
            if failed_match:
                tests_failed = failed_match.group(1)
            elif test_code == 0 and passed_match:
                tests_failed = "0"
            break

    after_evidence = capture_git_evidence(repo_root)
    after_unstaged_hash, after_staged_hash = get_diff_hashes(after_evidence)
    after_fingerprint = capture_filesystem_fingerprint(repo_root)

    head_unchanged = (before_evidence["head"] == after_evidence["head"])
    git_status_unchanged = (before_evidence["status"] == after_evidence["status"])
    staged_diff_unchanged = (before_staged_hash == after_staged_hash)
    unstaged_diff_unchanged = (before_unstaged_hash == after_unstaged_hash)
    filesystem_unchanged = (before_fingerprint == after_fingerprint)

    audit_workspace_mutated = not (head_unchanged and git_status_unchanged and
                                   staged_diff_unchanged and unstaged_diff_unchanged and
                                   filesystem_unchanged)

    cache_artifacts_created = False
    new_files = set(after_fingerprint.keys()) - set(before_fingerprint.keys())
    for f in new_files:
        if '__pycache__' in f or '.pytest_cache' in f or f.endswith('.pyc'):
            cache_artifacts_created = True
            audit_workspace_mutated = True
            break

    preflight_verdict = (
        not audit_workspace_mutated and
        diff_hygiene_pass and
        syntax_validation_pass and
        authoritative_test_gate_pass
    )

    print("PHYSICAL_PREFLIGHT_EXECUTION: PASS")
    print("DIFF_HYGIENE: " + ("PASS" if diff_hygiene_pass else "FAIL"))
    print("SYNTAX_VALIDATION: " + ("PASS" if syntax_validation_pass else "FAIL"))
    print("AUTHORITATIVE_TEST_GATE: " + ("PASS" if authoritative_test_gate_pass else "FAIL"))
    print("AUTHORITATIVE_TEST_COMMAND: " + " ".join(test_cmd))
    print(f"TESTS_PASSED: {tests_passed}")
    print(f"TESTS_FAILED: {tests_failed}")
    print("FILESYSTEM_FINGERPRINT_UNCHANGED: " + ("YES" if filesystem_unchanged else "NO"))
    print("GIT_STATUS_UNCHANGED: " + ("YES" if git_status_unchanged else "NO"))
    print("STAGED_DIFF_UNCHANGED: " + ("YES" if staged_diff_unchanged else "NO"))
    print("UNSTAGED_DIFF_UNCHANGED: " + ("YES" if unstaged_diff_unchanged else "NO"))
    print("HEAD_UNCHANGED: " + ("YES" if head_unchanged else "NO"))
    print("CACHE_ARTIFACTS_CREATED: " + ("YES" if cache_artifacts_created else "NO"))
    print("AUDIT_WORKSPACE_MUTATED: " + ("YES" if audit_workspace_mutated else "NO"))
    print("PREFLIGHT_VERDICT: " + ("PASS" if preflight_verdict else "FAIL"))

    if preflight_verdict:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
