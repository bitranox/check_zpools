#!/usr/bin/env python3
"""Analyze recent code changes for complexity and duplication."""

import re
from pathlib import Path


def count_function_lines(file_path, start_pattern=r"^\s*def "):
    """Count lines in each function/method."""
    with open(file_path) as f:
        lines = f.readlines()

    functions = []
    current_func = None
    current_lines = []
    base_indent = None

    for i, line in enumerate(lines, 1):
        # Check for function/method definition
        if re.match(start_pattern, line):
            # Save previous function
            if current_func:
                functions.append((current_func, len(current_lines), current_lines))

            # Start new function
            func_match = re.search(r"def\s+(\w+)", line)
            if func_match:
                current_func = (func_match.group(1), i)
                current_lines = [line]
                base_indent = len(line) - len(line.lstrip())
        elif current_func and line.strip():
            # Check if we're still in the function (indentation check)
            indent = len(line) - len(line.lstrip())
            if indent > base_indent or line.strip().startswith(('"""', "'''")):
                current_lines.append(line)
            elif indent == base_indent and not line.strip():
                # Empty line at base indent - might still be in function
                current_lines.append(line)
            else:
                # We've left the function
                if current_func:
                    functions.append((current_func, len(current_lines), current_lines))
                current_func = None
                current_lines = []
                base_indent = None
        elif current_func:
            current_lines.append(line)

    # Don't forget last function
    if current_func:
        functions.append((current_func, len(current_lines), current_lines))

    return functions


def analyze_file(file_path):
    """Analyze a Python file for complexity issues."""
    print(f"\n{'=' * 70}")
    print(f"ANALYZING: {file_path}")
    print(f"{'=' * 70}")

    functions = count_function_lines(file_path)

    # Report functions by size
    long_functions = [(name, line, count) for (name, line), count, _ in functions if count > 50]

    if long_functions:
        print("\n⚠️  LONG FUNCTIONS (>50 lines):")
        for name, line_no, count in sorted(long_functions, key=lambda x: x[2], reverse=True):
            print(f"  - {name}() at line {line_no}: {count} lines")
    else:
        print("\n✓ No functions exceed 50 lines")

    # Report all functions
    print("\nAll functions:")
    for (name, line_no), count, _ in sorted(functions, key=lambda x: x[1], reverse=True):
        status = "⚠️ " if count > 50 else "  "
        print(f"{status} {name}() at line {line_no}: {count} lines")

    return functions, long_functions


# Analyze changed files
files_to_analyze = [
    "src/check_zpools/zfs_client.py",
    "src/check_zpools/alerting.py",
    "src/check_zpools/behaviors.py",
]

all_results = {}
for file_path in files_to_analyze:
    if Path(file_path).exists():
        funcs, long_funcs = analyze_file(file_path)
        all_results[file_path] = (funcs, long_funcs)

# Summary
print(f"\n\n{'=' * 70}")
print("SUMMARY")
print(f"{'=' * 70}")
total_long = sum(len(long) for _, long in all_results.values())
print(f"\nTotal files analyzed: {len(all_results)}")
print(f"Total long functions (>50 lines): {total_long}")

if total_long > 0:
    print(f"\n⚠️  ACTION REQUIRED: {total_long} function(s) need refactoring")
else:
    print("\n✓ All functions are appropriately sized")
