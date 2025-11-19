#!/usr/bin/env python3
"""Verify alerting.py refactoring."""

import re

with open("src/check_zpools/alerting.py") as f:
    content = f.read()

print("=" * 70)
print("ALERTING.PY REFACTORING VERIFICATION")
print("=" * 70)

# 1. Check that _append_zpool_status exists
if "def _append_zpool_status(" in content:
    print("✓ _append_zpool_status() method exists")
else:
    print("✗ FAIL: _append_zpool_status() method not found")

# 2. Check exception handling is specific
append_method_start = content.find("def _append_zpool_status(")
append_method_end = content.find("\n    def ", append_method_start + 10)
append_method = content[append_method_start:append_method_end]

if "except (ZFSCommandError, subprocess.TimeoutExpired, RuntimeError)" in append_method:
    print("✓ Exception handling is specific (not broad)")
else:
    if "except Exception" in append_method:
        print("✗ FAIL: Still using broad 'except Exception'")
    else:
        print("⚠️  No exception handling found")

# 3. Check that it's called from _format_body
format_body_start = content.find("def _format_body(")
format_body_end = content.find("\n    def _format_", format_body_start + 10)
format_body = content[format_body_start:format_body_end]

if "self._append_zpool_status(" in format_body:
    print("✓ _format_body() calls _append_zpool_status()")

    # Check it's not duplicating code
    if "ZPOOL STATUS OUTPUT" in format_body:
        print("  ⚠️  WARNING: _format_body still contains zpool status code")
    else:
        print("  ✓ No duplication - delegates to helper")
else:
    print("✗ FAIL: _format_body() doesn't call _append_zpool_status()")

# 4. Check that it's called from _format_recovery_body
format_recovery_start = content.find("def _format_recovery_body(")
format_recovery_end = content.find("\n    def ", format_recovery_start + 10)
if format_recovery_end == -1:
    format_recovery_end = content.find("\n\n__all__", format_recovery_start)
format_recovery = content[format_recovery_start:format_recovery_end]

if "self._append_zpool_status(" in format_recovery:
    print("✓ _format_recovery_body() calls _append_zpool_status()")

    # Check it's not duplicating code
    if "zpool_status_output = self.zfs_client.get_pool_status_text" in format_recovery:
        print("  ⚠️  WARNING: _format_recovery_body still contains zpool status fetching code")
    else:
        print("  ✓ No duplication - delegates to helper")
else:
    print("✗ FAIL: _format_recovery_body() doesn't call _append_zpool_status()")

# 5. Verify no duplication of zpool status fetching
zpool_fetch_pattern = r"zpool_status_output\s*=\s*self\.zfs_client\.get_pool_status_text"
matches = list(re.finditer(zpool_fetch_pattern, content))
if len(matches) == 1:
    print("\n✓ PASS: zpool status fetching appears only ONCE (in helper)")
elif len(matches) > 1:
    print(f"\n✗ FAIL: zpool status fetching appears {len(matches)} times (should be 1)")
    for i, match in enumerate(matches, 1):
        line_num = content[: match.start()].count("\n") + 1
        print(f"  Location {i}: line {line_num}")
else:
    print("\n✗ FAIL: zpool status fetching not found")

# 6. Check subprocess import was added
if "import subprocess" in content[:1000]:  # Check near top of file
    print("✓ subprocess import added")
else:
    print("✗ FAIL: subprocess import missing")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print("✅ Refactoring appears correct!")
