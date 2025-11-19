#!/usr/bin/env python3.13
"""Check function lengths for high-complexity functions."""

from pathlib import Path

# High complexity functions from radon
high_complexity = [
    # C complexity (critical)
    ("src/check_zpools/zfs_parser.py", "_parse_scrub_time", 483),
    ("src/check_zpools/config_show.py", "display_config", 141),
    ("src/check_zpools/service_install.py", "_detect_uvx_from_process_tree", 69),
    # B complexity (high)
    ("src/check_zpools/formatters.py", "display_check_result_text", 109),
    ("src/check_zpools/formatters.py", "_format_last_scrub", 186),
    ("src/check_zpools/monitor.py", "_check_errors", 327),
    ("src/check_zpools/monitor.py", "_check_scrub", 392),
    ("src/check_zpools/cli.py", "cli_send_email", 661),
    ("src/check_zpools/alerting.py", "_format_notes_section", 628),
    ("src/check_zpools/config.py", "_build_monitor_config", 354),
    ("src/check_zpools/zfs_parser.py", "_extract_error_counts", 433),
    ("src/check_zpools/alert_state.py", "load_state", 259),
    ("src/check_zpools/config_show.py", "_display_value_with_source", 91),
    ("src/check_zpools/service_install.py", "install_service", 353),
    ("src/check_zpools/service_install.py", "uninstall_service", 458),
    ("src/check_zpools/daemon.py", "start", 102),
    ("src/check_zpools/daemon.py", "_detect_recoveries", 526),
    ("src/check_zpools/daemon.py", "_run_check_cycle", 232),
    ("src/check_zpools/mail.py", "load_email_config_from_dict", 354),
    ("src/check_zpools/mail.py", "__post_init__", 88),
    ("src/check_zpools/mail.py", "send_email", 169),
]


def count_function_lines(file_path, func_name, start_line):
    """Count lines from function start to its end."""
    path = Path(file_path)
    if not path.exists():
        return None

    lines = path.read_text().splitlines()
    if start_line >= len(lines):
        return None

    # Find the indentation level of the function definition
    func_line = lines[start_line - 1]  # -1 because line numbers are 1-indexed
    base_indent = len(func_line) - len(func_line.lstrip())

    # Count lines until we hit something at same or lower indentation
    count = 1
    for i in range(start_line, len(lines)):
        line = lines[i]
        if not line.strip():  # Empty line
            count += 1
            continue

        indent = len(line) - len(line.lstrip())
        if indent <= base_indent and line.strip():
            # Found end of function
            break
        count += 1

    return count


print("=== HIGH-COMPLEXITY FUNCTIONS - LINE COUNT ANALYSIS ===\n")
print(f"{'File':<45} {'Function':<30} {'Start':<7} {'Lines':<7} {'Complexity'}")
print("=" * 120)

for file_path, func_name, start_line in high_complexity:
    line_count = count_function_lines(file_path, func_name, start_line)
    if line_count:
        # Determine complexity level
        if start_line in [483, 141, 69]:
            complexity = "C (12-15)"
        else:
            complexity = "B (6-10)"

        # Flag if >50 lines
        flag = " ⚠️  TOO LONG!" if line_count > 50 else ""
        print(f"{file_path:<45} {func_name:<30} {start_line:<7} {line_count:<7} {complexity}{flag}")
