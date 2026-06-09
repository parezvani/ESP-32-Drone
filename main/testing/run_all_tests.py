"""
run_all_tests.py
Master runner for the FireFly extended test suite.
Usage:  python run_all_tests.py
        python run_all_tests.py --verbose   (show each sub-test's stdout live)

Returns exit code 0 if all suites pass, 1 otherwise.
"""

import subprocess
import sys
import os
import time
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))

SUITES = [
    ("Triangulator (original)",         "main/testing/test_triangulator.py",          False),
    ("Triangulator (extended)",          "test_triangulator_extended.py",              True),
    ("Single-drone triangulator",        "test_single_drone_triangulator.py",          True),
    ("Fire merge logic",                 "test_fire_merge_logic.py",                   True),
    ("Geo utilities",                    "test_geo_utils.py",                          True),
    ("Telemetry packet validation",      "test_telemetry_packet.py",                   True),
]

def run_suite(label, rel_path, is_local, verbose):
    if is_local:
        script = os.path.join(HERE, rel_path)
    else:
        # Original test lives one level up in the repo
        script = os.path.join(HERE, "..", rel_path)
    script = os.path.normpath(script)

    if not os.path.exists(script):
        return None, f"script not found: {script}"

    t0 = time.time()
    result = subprocess.run(
        [sys.executable, script],
        capture_output=not verbose,
        text=True,
        cwd=HERE,
    )
    elapsed = time.time() - t0

    if verbose:
        return result.returncode == 0, elapsed

    # Extract pass/fail summary line
    output = result.stdout + result.stderr
    summary = ""
    for line in output.splitlines():
        if "passed" in line or "FAILED" in line or "Passed:" in line:
            summary = line.strip()
            break

    if result.returncode != 0:
        detail = "\n".join("    " + l for l in output.splitlines()[-12:])
        return False, f"{summary}\n{detail}"
    return True, f"{summary}  ({elapsed:.2f}s)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", "-v", action="store_true", help="show sub-test output live")
    args = ap.parse_args()

    print("\n" + "=" * 60)
    print("  FireFly Extended Test Suite")
    print("=" * 60)

    passed_suites = 0
    failed_suites = []

    for label, rel_path, is_local in SUITES:
        print(f"\n▶  {label}")
        ok, detail = run_suite(label, rel_path, is_local, args.verbose)
        if ok is None:
            print(f"   SKIP — {detail}")
        elif ok:
            print(f"   PASS — {detail}")
            passed_suites += 1
        else:
            print(f"   FAIL")
            print(detail)
            failed_suites.append(label)

    print("\n" + "=" * 60)
    total = len(SUITES)
    skipped = total - passed_suites - len(failed_suites)
    print(f"  Results: {passed_suites}/{total} suites passed"
          + (f"  |  {skipped} skipped" if skipped else ""))
    if failed_suites:
        print(f"  Failed suites:")
        for s in failed_suites:
            print(f"    ✗  {s}")
        print("=" * 60)
        sys.exit(1)
    else:
        print("  All suites passed ✓")
        print("=" * 60)
        sys.exit(0)

if __name__ == "__main__":
    main()
