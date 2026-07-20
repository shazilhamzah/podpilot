"""
compare_security.py
Podpilot - compares the "security" check results attached to two saved
sanitized snapshots (see security.py's run_all_checks, and where it's
plugged into the save pipeline).
"""


def compare_security(snap_a: dict, snap_b: dict) -> dict:
    """snap_a / snap_b are two saved sanitized snapshot dicts, each expected
    to have a "security" key (a list of {name, passed, affected} dicts,
    produced by security.run_all_checks)."""
    checks_a = {c["name"]: c for c in snap_a.get("security", [])}
    checks_b = {c["name"]: c for c in snap_b.get("security", [])}

    resolved = []       # was failing at A, passing at B
    new_issues = []      # was passing (or absent) at A, failing at B
    still_failing = []   # failing at both

    for name, check_b in checks_b.items():
        check_a = checks_a.get(name)
        if not check_b["passed"]:
            if check_a is None or check_a["passed"]:
                new_issues.append({"name": name, "affected": check_b.get("affected", [])})
            else:
                still_failing.append({"name": name, "affected": check_b.get("affected", [])})
        elif check_a and not check_a["passed"]:
            resolved.append({"name": name})

    failing_now = sum(1 for c in checks_b.values() if not c["passed"])

    return {
        "total_checks": len(checks_b),
        "failing_now": failing_now,
        "passing_now": len(checks_b) - failing_now,
        "resolved_since_last": resolved,
        "new_since_last": new_issues,
        "still_failing": still_failing,
    }