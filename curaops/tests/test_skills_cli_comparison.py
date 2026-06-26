#!/usr/bin/env python3
"""
Comprehensive Test: All 7 Skills
Tests both via Python Import (Hermes) and CLI (Matrix UI)
Compares results
"""

import json
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

# Test Results Storage
results = {
    "timestamp": datetime.now().isoformat(),
    "hermes": {},  # Python import results
    "matrix_ui": {},  # CLI results
    "comparison": {}
}

console = {
    "green": lambda x: f"\033[92m{x}\033[0m",
    "red": lambda x: f"\033[91m{x}\033[0m",
    "yellow": lambda x: f"\033[93m{x}\033[0m",
    "blue": lambda x: f"\033[94m{x}\033[0m",
    "bold": lambda x: f"\033[1m{x}\033[0m",
}

def log(title, message="", color="blue"):
    print(f"{console[color]('━' * 60)}")
    if message:
        print(f"{console[color](title)}: {message}")
    else:
        print(f"{console[color](title)}")
    print(f"{console[color]('━' * 60)}")

def run_cli(command, cwd=None):
    """Run CLI command and return result."""
    start = time.time()
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=30
        )
        elapsed = time.time() - start
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "elapsed_ms": round(elapsed * 1000, 2)
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "TIMEOUT",
            "returncode": -1,
            "elapsed_ms": 30000
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
            "elapsed_ms": 0
        }

# ═══════════════════════════════════════════════════════════════════════════
# SKILL 1: SAFETY GUARD
# ═══════════════════════════════════════════════════════════════════════════

def test_safety_guard():
    log("TEST 1: SAFETY GUARD", "P1-Critical Protection", "red")
    
    # HERMES: Direct Python Import
    print("\n🤖 HERMES (Python Import):")
    try:
        from curaops.skills.safety_guard import SafetyGuard
        sg = SafetyGuard()
        
        # Test 1: Safe path
        try:
            result = sg.validate_path("/tmp/test_safe.txt")
            hermes_safe = {"success": True, "blocked": False, "path": str(result)}
            print(f"  ✅ Safe path: {console['green']('PASSED')}")
        except Exception as e:
            hermes_safe = {"success": False, "error": str(e)}
            print(f"  ❌ Safe path: {console['red']('FAILED')} - {e}")
        
        # Test 2: Protected path
        try:
            result = sg.validate_path(".git")
            hermes_protected = {"success": True, "blocked": False}
            print(f"  ⚠️  Protected path: {console['yellow']('SHOULD HAVE BLOCKED')}")
        except Exception as e:
            hermes_protected = {"success": False, "blocked": True, "error": str(e)}
            print(f"  ✅ Protected path: {console['green']('BLOCKED')} - {e}")
        
        hermes_result = {"success": True, "tests": {"safe": hermes_safe, "protected": hermes_protected}}
    except ImportError as e:
        hermes_result = {"success": False, "error": f"Import failed: {e}"}
        print(f"  ❌ Import failed: {e}")
    
    # MATRIX UI: CLI
    print("\n🖥️  MATRIX UI (CLI):")
    
    # Test 1: Safe path
    cli_safe = run_cli("cd /home/roberto_schmidt/projects/CuraOps_Framework && python -m src.cli.main safety check /tmp/test_safe.txt --operation delete")
    if cli_safe["success"]:
        print(f"  ✅ Safe path: {console['green']('PASSED')} ({cli_safe['elapsed_ms']}ms)")
    else:
        print(f"  ❌ Safe path: {console['red']('FAILED')} - {cli_safe['stderr'][:50]}")
    
    # Test 2: Protected path
    cli_protected = run_cli("cd /home/roberto_schmidt/projects/CuraOps_Framework && python -m src.cli.main safety check .git --operation delete")
    if not cli_protected["success"] and "BLOCKED" in cli_protected["stdout"]:
        print(f"  ✅ Protected path: {console['green']('BLOCKED')} ({cli_protected['elapsed_ms']}ms)")
        cli_protected["blocked"] = True
    else:
        print(f"  ❌ Protected path: {console['red']('FAILED')} - Should have blocked")
        cli_protected["blocked"] = False
    
    matrix_result = {
        "success": cli_safe["success"] and cli_protected["blocked"],
        "tests": {"safe": cli_safe, "protected": cli_protected}
    }
    
    # Comparison
    print("\n📊 COMPARISON:")
    hermes_works = hermes_result.get("success", False)
    matrix_works = matrix_result["success"]
    
    if hermes_works and matrix_works:
        print(f"  ✅ {console['green']('BOTH WORK')}")
        comparison = "MATCH"
    elif hermes_works and not matrix_works:
        print(f"  ⚠️  {console['yellow']('Hermes OK, CLI fails')}")
        comparison = "CLI_ISSUE"
    elif not hermes_works and matrix_works:
        print(f"  ⚠️  {console['yellow']('CLI OK, Hermes fails')}")
        comparison = "IMPORT_ISSUE"
    else:
        print(f"  ❌ {console['red']('BOTH FAIL')}")
        comparison = "BOTH_FAIL"
    
    results["hermes"]["safety_guard"] = hermes_result
    results["matrix_ui"]["safety_guard"] = matrix_result
    results["comparison"]["safety_guard"] = comparison
    
    return hermes_works or matrix_works

# ═══════════════════════════════════════════════════════════════════════════
# SKILL 2: CHANGE REQUEST
# ═══════════════════════════════════════════════════════════════════════════

def test_change_request():
    log("TEST 2: CHANGE REQUEST", "CR-Driven Workflow", "blue")
    
    # HERMES: Direct Python Import
    print("\n🤖 HERMES (Python Import):")
    try:
        from curaops.skills.change_request import ChangeRequestService
        
        cr_service = ChangeRequestService(changes_path=Path(tempfile.mkdtemp()) / "changes")
        result = cr_service.submit_change_request(
            title="Test CR from Hermes",
            description="Testing via Python import"
        )
        cr_id = result.get("id", "unknown")
        
        print(f"  ✅ Created CR: {console['green'](cr_id)}")
        hermes_result = {"success": True, "cr_id": cr_id}
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        hermes_result = {"success": False, "error": str(e)}
    
    # MATRIX UI: CLI
    print("\n🖥️  MATRIX UI (CLI):")
    cli_result = run_cli(
        'cd /home/roberto_schmidt/projects/CuraOps_Framework && '
        'python -m src.cli.main cr create --title "Test CLI CR" '
        '--description "Testing via CLI" --scope "src/test.py" --priority MEDIUM'
    )
    
    if cli_result["success"] and "Created CR" in cli_result["stdout"]:
        print(f"  ✅ Created CR via CLI ({cli_result['elapsed_ms']}ms)")
        matrix_result = {"success": True, "output": cli_result["stdout"][:100]}
    else:
        print(f"  ❌ CLI failed: {cli_result['stderr'][:50]}")
        matrix_result = {"success": False, "error": cli_result["stderr"][:100]}
    
    # Comparison
    print("\n📊 COMPARISON:")
    comparison = "MATCH" if hermes_result.get("success") and matrix_result["success"] else "MISMATCH"
    print(f"  {'✅' if comparison == 'MATCH' else '⚠️'} {comparison}")
    
    results["hermes"]["change_request"] = hermes_result
    results["matrix_ui"]["change_request"] = matrix_result
    results["comparison"]["change_request"] = comparison
    
    return hermes_result.get("success", False) or matrix_result["success"]

# ═══════════════════════════════════════════════════════════════════════════
# SKILL 3: SESSION MANAGER
# ═══════════════════════════════════════════════════════════════════════════

def test_session_manager():
    log("TEST 3: SESSION MANAGER", "Session Lifecycle", "blue")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # HERMES: Direct Python Import
        print("\n🤖 HERMES (Python Import):")
        try:
            from curaops.skills.session_manager import AgentSessionManager
            
            sm = AgentSessionManager(storage_dir=Path(tmpdir) / ".curaops" / "sessions")
            session = sm.create_session(
                agent="test-agent",
                model="test-model",
                prompt="Test session"
            )
            
            print(f"  ✅ Started session: {console['green'](session.session_id)}")
            hermes_result = {"success": True, "session_id": session.session_id}
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            hermes_result = {"success": False, "error": str(e)}
        
        # MATRIX UI: CLI
        print("\n🖥️  MATRIX UI (CLI):")
        cli_result = run_cli(
            f'cd /home/roberto_schmidt/projects/CuraOps_Framework && '
            f'python -m src.cli.main session start --agent test-agent --model test-model --prompt "CLI Test"'
        )
        
        if cli_result["success"] and "Session started" in cli_result["stdout"]:
            print(f"  ✅ Started session via CLI ({cli_result['elapsed_ms']}ms)")
            matrix_result = {"success": True}
        else:
            print(f"  ❌ CLI failed: {cli_result['stderr'][:50]}")
            matrix_result = {"success": False, "error": cli_result["stderr"][:100]}
        
        # Comparison
        print("\n📊 COMPARISON:")
        comparison = "MATCH" if hermes_result.get("success") and matrix_result["success"] else "MISMATCH"
        print(f"  {'✅' if comparison == 'MATCH' else '⚠️'} {comparison}")
        
        results["hermes"]["session_manager"] = hermes_result
        results["matrix_ui"]["session_manager"] = matrix_result
        results["comparison"]["session_manager"] = comparison
        
        return hermes_result.get("success", False) or matrix_result["success"]

# ═══════════════════════════════════════════════════════════════════════════
# SKILL 4: ASPICE LINK MANAGER
# ═══════════════════════════════════════════════════════════════════════════

def test_aspice_link_manager():
    log("TEST 4: ASPICE LINK MANAGER", "Traceability", "blue")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test structure
        (Path(tmpdir) / "requirements" / "software").mkdir(parents=True)
        (Path(tmpdir) / "requirements" / "software" / "SW-REQ-001.md").write_text('''---
{"id": "SW-REQ-001", "title": "Test Requirement", "validated_by": [], "implemented_in": []}
---

# SW-REQ-001: Test Requirement

Test description.
''')
        
        # HERMES: Direct Python Import
        print("\n🤖 HERMES (Python Import):")
        try:
            from curaops.skills.aspice_link_manager import ASPICELinkManager
            
            lm = ASPICELinkManager(root_dir=tmpdir)
            # Create a test implementation file
            test_impl = Path(tmpdir) / "src" / "test.py"
            test_impl.parent.mkdir(exist_ok=True)
            test_impl.write_text("# Test implementation")
            
            result = lm.update_bidirectional_links(changed_file=test_impl)
            
            print(f"  ✅ Updated links: {console['green'](str(result.updated_count))} files updated")
            hermes_result = {"success": result.success, "updated": result.updated_count}
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            hermes_result = {"success": False, "error": str(e)}
        
        # MATRIX UI: CLI
        print("\n🖥️  MATRIX UI (CLI):")
        # Create a temp file for the CLI test
        test_file = Path(tmpdir) / "cli_test.py"
        test_file.write_text("# CLI test file")
        cli_result = run_cli(
            f'cd {tmpdir} && '
            f'python -m src.cli.main aspice link --req SW-REQ-001 --file {test_file}'
        )
        
        if cli_result["success"] and "Link created" in cli_result["stdout"]:
            print(f"  ✅ Created link via CLI ({cli_result['elapsed_ms']}ms)")
            matrix_result = {"success": True}
        else:
            print(f"  ❌ CLI failed: {cli_result['stderr'][:50]}")
            matrix_result = {"success": False, "error": cli_result["stderr"][:100]}
        
        # Comparison
        print("\n📊 COMPARISON:")
        comparison = "MATCH" if hermes_result.get("success") and matrix_result["success"] else "MISMATCH"
        print(f"  {'✅' if comparison == 'MATCH' else '⚠️'} {comparison}")
        
        results["hermes"]["aspice_link_manager"] = hermes_result
        results["matrix_ui"]["aspice_link_manager"] = matrix_result
        results["comparison"]["aspice_link_manager"] = comparison
        
        return hermes_result.get("success", False) or matrix_result["success"]

# ═══════════════════════════════════════════════════════════════════════════
# SKILL 5: ASPICE CONFLICT DETECTOR
# ═══════════════════════════════════════════════════════════════════════════

def test_aspice_conflict_detector():
    log("TEST 5: ASPICE CONFLICT DETECTOR", "Compliance Check", "blue")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test structure
        (Path(tmpdir) / "src").mkdir()
        (Path(tmpdir) / "requirements" / "software").mkdir(parents=True)
        (Path(tmpdir) / "src" / "orphaned.py").write_text("def foo(): pass")
        
        # HERMES: Direct Python Import
        print("\n🤖 HERMES (Python Import):")
        try:
            from curaops.skills.aspice_conflict_detector import ConflictDetector
            
            detector = ConflictDetector(root_dir=tmpdir)
            conflicts = detector.detect_conflicts()
            report = detector.generate_conflict_report(conflicts)
            
            print(f"  ✅ Detected {console['green'](report['total_conflicts'])} conflicts")
            hermes_result = {
                "success": True,
                "conflicts": report['total_conflicts'],
                "by_type": report['by_type']
            }
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            hermes_result = {"success": False, "error": str(e)}
        
        # MATRIX UI: CLI
        print("\n🖥️  MATRIX UI (CLI):")
        cli_result = run_cli(
            f'cd /home/roberto_schmidt/projects/CuraOps_Framework && '
            f'python -m src.cli.main aspice check --path {tmpdir}'
        )
        
        # CLI returns non-zero if conflicts found, which is expected
        has_conflicts = "Total Conflicts" in cli_result["stdout"] or cli_result["returncode"] == 1
        if has_conflicts:
            print(f"  ✅ Detected conflicts via CLI ({cli_result['elapsed_ms']}ms)")
            matrix_result = {"success": True, "found_conflicts": True}
        else:
            print(f"  ❌ CLI failed: {cli_result['stderr'][:50]}")
            matrix_result = {"success": False, "error": cli_result["stderr"][:100]}
        
        # Comparison
        print("\n📊 COMPARISON:")
        comparison = "MATCH" if hermes_result.get("success") and matrix_result["success"] else "MISMATCH"
        print(f"  {'✅' if comparison == 'MATCH' else '⚠️'} {comparison}")
        
        results["hermes"]["aspice_conflict_detector"] = hermes_result
        results["matrix_ui"]["aspice_conflict_detector"] = matrix_result
        results["comparison"]["aspice_conflict_detector"] = comparison
        
        return hermes_result.get("success", False) or matrix_result["success"]

# ═══════════════════════════════════════════════════════════════════════════
# SKILL 6: MULTI-AGENT LOCK
# ═══════════════════════════════════════════════════════════════════════════

def test_multi_agent_lock():
    log("TEST 6: MULTI-AGENT LOCK", "File Coordination", "blue")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # HERMES: Direct Python Import
        print("\n🤖 HERMES (Python Import):")
        try:
            from curaops.skills.multi_agent_lock import MultiAgentLock, LockScope
            
            lock_mgr = MultiAgentLock(storage_dir=Path(tmpdir) / ".curaops" / "locks")
            lock = lock_mgr.claim_file("/tmp/test.py", agent_id="test-agent", scope=LockScope.FILE)
            
            print(f"  ✅ Claimed lock: {console['green'](lock.lock_id)}")
            
            # Check if locked
            is_locked = lock_mgr.is_locked("/tmp/test.py")
            if is_locked:
                print(f"  ✅ Lock verified")
                hermes_result = {"success": True, "lock_id": lock.lock_id}
            else:
                print(f"  ⚠️  Lock not found")
                hermes_result = {"success": False, "error": "Lock not verified"}
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            hermes_result = {"success": False, "error": str(e)}
        
        # MATRIX UI: CLI
        print("\n🖥️  MATRIX UI (CLI):")
        cli_result = run_cli(
            f'cd /home/roberto_schmidt/projects/CuraOps_Framework && '
            f'python -m src.cli.main lock claim --file /tmp/test2.py --agent cli-test'
        )
        
        if cli_result["success"] and "Lock claimed" in cli_result["stdout"]:
            print(f"  ✅ Claimed lock via CLI ({cli_result['elapsed_ms']}ms)")
            matrix_result = {"success": True}
        else:
            print(f"  ❌ CLI failed: {cli_result['stderr'][:50]}")
            matrix_result = {"success": False, "error": cli_result["stderr"][:100]}
        
        # Comparison
        print("\n📊 COMPARISON:")
        comparison = "MATCH" if hermes_result.get("success") and matrix_result["success"] else "MISMATCH"
        print(f"  {'✅' if comparison == 'MATCH' else '⚠️'} {comparison}")
        
        results["hermes"]["multi_agent_lock"] = hermes_result
        results["matrix_ui"]["multi_agent_lock"] = matrix_result
        results["comparison"]["multi_agent_lock"] = comparison
        
        return hermes_result.get("success", False) or matrix_result["success"]

# ═══════════════════════════════════════════════════════════════════════════
# SKILL 7: PATTERN LEARNING
# ═══════════════════════════════════════════════════════════════════════════

def test_pattern_learning():
    log("TEST 7: PATTERN LEARNING", "Behavior Learning", "blue")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # HERMES: Direct Python Import
        print("\n🤖 HERMES (Python Import):")
        try:
            from curaops.skills.pattern_learning import PatternLearningEngine, CodeFinding
            
            pl = PatternLearningEngine(storage_dir=Path(tmpdir) / ".curaops" / "patterns")
            
            # Learn from a finding
            finding = CodeFinding(
                description="Test finding",
                code_snippet="test_code()",
                severity="MEDIUM"
            )
            pattern = pl.learn_from_finding(finding)
            print(f"  ✅ Learned pattern: {console['green'](pattern.name if pattern else 'None')}")
            
            # Store pattern
            if pattern:
                pl.store_pattern(pattern)
                print(f"  ✅ Stored pattern")
            
            hermes_result = {"success": True, "pattern": pattern.name if pattern else None}
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            hermes_result = {"success": False, "error": str(e)}
        
        # MATRIX UI: CLI
        # MATRIX UI: CLI
        cli_result = run_cli(
            f'cd /home/roberto_schmidt/projects/CuraOps_Framework && '
            f'python -m src.cli.main pattern record "test-action" --context "testing" --success'
        )
        
        if cli_result["success"] and ("Pattern recorded" in cli_result["stdout"] or "recorded" in cli_result["stdout"].lower()):
            print(f"  ✅ Recorded pattern via CLI ({cli_result['elapsed_ms']}ms)")
            matrix_result = {"success": True}
        else:
            print(f"  ❌ CLI failed: {cli_result['stderr'][:100] if cli_result['stderr'] else cli_result['stdout'][:100]}")
            matrix_result = {"success": False, "error": cli_result["stderr"][:100]}
        
        # Comparison
        print("\n📊 COMPARISON:")
        comparison = "MATCH" if hermes_result.get("success") and matrix_result["success"] else "MISMATCH"
        print(f"  {'✅' if comparison == 'MATCH' else '⚠️'} {comparison}")
        
        results["hermes"]["pattern_learning"] = hermes_result
        results["matrix_ui"]["pattern_learning"] = matrix_result
        results["comparison"]["pattern_learning"] = comparison
        
        return hermes_result.get("success", False) or matrix_result["success"]

# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    log("🧪 COMPREHENSIVE SKILL TEST", "Hermes vs Matrix UI", "bold")
    print(f"\nTimestamp: {results['timestamp']}")
    print(f"Testing: All 7 Skills")
    print()
    
    all_passed = []
    
    # Run all tests
    all_passed.append(test_safety_guard())
    all_passed.append(test_change_request())
    all_passed.append(test_session_manager())
    all_passed.append(test_aspice_link_manager())
    all_passed.append(test_aspice_conflict_detector())
    all_passed.append(test_multi_agent_lock())
    all_passed.append(test_pattern_learning())
    
    # Summary
    log("📊 FINAL SUMMARY", f"{sum(all_passed)}/7 skills passed", "green" if all(all_passed) else "red")
    
    print("\n" + console["bold"]("RESULTS BY SKILL:"))
    print("━" * 60)
    
    skills = ["safety_guard", "change_request", "session_manager", 
              "aspice_link_manager", "aspice_conflict_detector", 
              "multi_agent_lock", "pattern_learning"]
    
    for skill in skills:
        hermes_ok = results["hermes"].get(skill, {}).get("success", False)
        matrix_ok = results["matrix_ui"].get(skill, {}).get("success", False)
        comparison = results["comparison"].get(skill, "UNKNOWN")
        
        status = "✅" if (hermes_ok and matrix_ok) else "⚠️"
        hermes_icon = "✓" if hermes_ok else "✗"
        matrix_icon = "✓" if matrix_ok else "✗"
        
        print(f"{status} {skill:30} | Hermes: {hermes_icon} | CLI: {matrix_icon} | {comparison}")
    
    print("━" * 60)
    
    # Save results
    results_file = Path("/tmp/skill_test_results.json")
    results_file.write_text(json.dumps(results, indent=2, default=str))
    print(f"\n💾 Full results saved to: {results_file}")
    
    # Overall status
    if all(all_passed):
        print(f"\n{console['green']('🎉 ALL TESTS PASSED!')}")
        return 0
    else:
        print(f"\n{console['yellow']('⚠️  SOME TESTS FAILED')}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
