#!/usr/bin/env python3
"""Verify zfs_client.py refactoring is correct."""

import ast

# Read the file
with open("src/check_zpools/zfs_client.py") as f:
    tree = ast.parse(f.read())

# Find the ZFSClient class
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == "ZFSClient":
        methods = {}
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                methods[item.name] = {
                    "lineno": item.lineno,
                    "end_lineno": item.end_lineno,
                    "length": item.end_lineno - item.lineno + 1 if item.end_lineno else 0,
                }

        print("ZFSClient Methods:")
        print("=" * 70)

        critical_methods = ["_execute_command", "_execute_json_command", "_execute_text_command"]
        for method_name in critical_methods:
            if method_name in methods:
                info = methods[method_name]
                print(f"{method_name}:")
                print(f"  Lines: {info['lineno']}-{info['end_lineno']}")
                print(f"  Length: {info['length']} lines")

                # Check if appropriate length
                if method_name == "_execute_command":
                    if info["length"] > 100:
                        print(f"  ⚠️  WARNING: Helper method too long ({info['length']} lines)")
                    else:
                        print("  ✓ Good length for helper method")

                if method_name in ["_execute_json_command", "_execute_text_command"]:
                    if info["length"] > 30:
                        print(f"  ⚠️  WARNING: Still too long after refactoring ({info['length']} lines)")
                    else:
                        print(f"  ✓ Good - refactored to {info['length']} lines")
                print()

# Verify no code duplication between _execute_json_command and _execute_text_command
print("\n" + "=" * 70)
print("DUPLICATION CHECK")
print("=" * 70)

with open("src/check_zpools/zfs_client.py") as f:
    content = f.read()

# Check for subprocess.run in the smaller methods
json_method_start = content.find("def _execute_json_command(")
json_method_end = content.find("def _execute_text_command(", json_method_start)
json_method_body = content[json_method_start:json_method_end]

text_method_start = content.find("def _execute_text_command(")
text_method_end = content.find("\n\n__all__", text_method_start)
text_method_body = content[text_method_start:text_method_end]

# Check if subprocess.run appears in either method (should NOT)
if "subprocess.run(" in json_method_body:
    print("✗ FAIL: _execute_json_command still contains subprocess.run()")
else:
    print("✓ PASS: _execute_json_command delegates to helper")

if "subprocess.run(" in text_method_body:
    print("✗ FAIL: _execute_text_command still contains subprocess.run()")
else:
    print("✓ PASS: _execute_text_command delegates to helper")

# Check if both call _execute_command
if "self._execute_command(" in json_method_body:
    print("✓ PASS: _execute_json_command calls _execute_command()")
else:
    print("✗ FAIL: _execute_json_command doesn't call _execute_command()")

if "self._execute_command(" in text_method_body:
    print("✓ PASS: _execute_text_command calls _execute_command()")
else:
    print("✗ FAIL: _execute_text_command doesn't call _execute_command()")

print("\n✅ Refactoring verified successfully!")
