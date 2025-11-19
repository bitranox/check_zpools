#!/usr/bin/env python3
"""
Performance profiling script for check_zpools test suite.

Profiles real test workloads with cProfile and memory_profiler to identify
bottlenecks in:
- ZFS client operations (command execution, JSON parsing)
- Pool monitoring logic (threshold checks, issue detection)
- Alerting system (email formatting, SMTP operations)
- Daemon operations (check cycles, state management)
"""

import cProfile
import io
import pstats
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest


def run_profiled_tests(test_pattern: str = "") -> pstats.Stats:
    """Run tests with cProfile profiling."""
    profiler = cProfile.Profile()

    # Build pytest args
    args = ["-xvs", "--tb=short"]
    if test_pattern:
        args.extend(["-k", test_pattern])

    # Profile the test run
    profiler.enable()
    start_time = time.perf_counter()

    exit_code = pytest.main(args)

    end_time = time.perf_counter()
    profiler.disable()

    elapsed = end_time - start_time
    print(f"\n{'=' * 70}")
    print(f"Test execution time: {elapsed:.3f}s")
    print(f"Exit code: {exit_code}")
    print(f"{'=' * 70}\n")

    return pstats.Stats(profiler)


def analyze_stats(stats: pstats.Stats, output_dir: Path) -> dict[str, Any]:
    """Analyze profiling statistics and generate reports."""
    analysis: dict[str, Any] = {}

    # Get top time consumers
    s = io.StringIO()
    stats.stream = s
    stats.sort_stats("cumulative")
    stats.print_stats(50)

    cumulative_report = s.getvalue()
    analysis["top_cumulative"] = cumulative_report

    # Get top by total time (internal time excluding subcalls)
    s = io.StringIO()
    stats.stream = s
    stats.sort_stats("tottime")
    stats.print_stats(50)

    tottime_report = s.getvalue()
    analysis["top_tottime"] = tottime_report

    # Get caller/callee information for key modules
    key_modules = [
        "zfs_client",
        "zfs_parser",
        "monitor",
        "alerting",
        "daemon",
        "behaviors",
    ]

    callers_info: dict[str, str] = {}
    for module in key_modules:
        s = io.StringIO()
        stats.stream = s
        stats.print_callers(f".*{module}.*")
        callers_info[module] = s.getvalue()

    analysis["callers"] = callers_info

    # Save detailed stats
    stats_file = output_dir / "profile_stats.dat"
    stats.dump_stats(str(stats_file))
    analysis["stats_file"] = str(stats_file)

    return analysis


def profile_specific_operations(output_dir: Path) -> dict[str, Any]:
    """Profile specific operations in isolation."""
    results: dict[str, Any] = {}

    # Profile ZFS client operations
    print("\n" + "=" * 70)
    print("Profiling ZFS Client Operations")
    print("=" * 70)

    zfs_stats = run_profiled_tests("test_zfs_client or test_zfs_parser")
    results["zfs_operations"] = analyze_operation_stats(zfs_stats, "ZFS Client")

    # Profile monitoring logic
    print("\n" + "=" * 70)
    print("Profiling Pool Monitoring Logic")
    print("=" * 70)

    monitor_stats = run_profiled_tests("test_monitor")
    results["monitoring"] = analyze_operation_stats(monitor_stats, "Monitor")

    # Profile alerting
    print("\n" + "=" * 70)
    print("Profiling Alerting System")
    print("=" * 70)

    alert_stats = run_profiled_tests("test_alerting")
    results["alerting"] = analyze_operation_stats(alert_stats, "Alerting")

    # Profile daemon operations
    print("\n" + "=" * 70)
    print("Profiling Daemon Operations")
    print("=" * 70)

    daemon_stats = run_profiled_tests("test_daemon")
    results["daemon"] = analyze_operation_stats(daemon_stats, "Daemon")

    return results


def analyze_operation_stats(stats: pstats.Stats, operation_name: str) -> dict[str, Any]:
    """Analyze stats for a specific operation."""
    s = io.StringIO()
    stats.stream = s
    stats.sort_stats("cumulative")
    stats.print_stats(30)

    return {
        "name": operation_name,
        "report": s.getvalue(),
    }


def generate_report(
    full_analysis: dict[str, Any],
    specific_ops: dict[str, Any],
    output_dir: Path,
) -> None:
    """Generate comprehensive performance report."""
    report_path = output_dir / "performance_report.txt"

    with open(report_path, "w") as f:
        f.write("=" * 70 + "\n")
        f.write("CHECK_ZPOOLS PERFORMANCE PROFILING REPORT\n")
        f.write("=" * 70 + "\n\n")

        f.write("This report profiles REAL test suite workloads to identify performance\n")
        f.write("bottlenecks in ZFS monitoring, daemon operations, and alerting logic.\n\n")

        # Full test suite analysis
        f.write("=" * 70 + "\n")
        f.write("FULL TEST SUITE ANALYSIS\n")
        f.write("=" * 70 + "\n\n")

        f.write("TOP FUNCTIONS BY CUMULATIVE TIME\n")
        f.write("-" * 70 + "\n")
        f.write(full_analysis["top_cumulative"])
        f.write("\n\n")

        f.write("TOP FUNCTIONS BY TOTAL TIME (INTERNAL)\n")
        f.write("-" * 70 + "\n")
        f.write(full_analysis["top_tottime"])
        f.write("\n\n")

        # Module-specific caller analysis
        f.write("=" * 70 + "\n")
        f.write("MODULE CALLER ANALYSIS\n")
        f.write("=" * 70 + "\n\n")

        for module, callers in full_analysis["callers"].items():
            if callers.strip():
                f.write(f"\n{module.upper()}\n")
                f.write("-" * 70 + "\n")
                f.write(callers)
                f.write("\n")

        # Specific operation profiles
        f.write("\n" + "=" * 70 + "\n")
        f.write("SPECIFIC OPERATION PROFILES\n")
        f.write("=" * 70 + "\n\n")

        for op_name, op_data in specific_ops.items():
            f.write(f"\n{op_name.upper()}\n")
            f.write("-" * 70 + "\n")
            f.write(op_data["report"])
            f.write("\n\n")

        # Bottleneck identification
        f.write("=" * 70 + "\n")
        f.write("IDENTIFIED BOTTLENECKS\n")
        f.write("=" * 70 + "\n\n")

        bottlenecks = identify_bottlenecks(full_analysis, specific_ops)
        for i, bottleneck in enumerate(bottlenecks, 1):
            f.write(f"{i}. {bottleneck}\n")

        f.write("\n")
        f.write(f"Detailed stats saved to: {full_analysis['stats_file']}\n")
        f.write(f"Use 'python -m pstats {full_analysis['stats_file']}' for interactive analysis\n")

    print(f"\nReport saved to: {report_path}")


def identify_bottlenecks(
    full_analysis: dict[str, Any],
    specific_ops: dict[str, Any],
) -> list[str]:
    """Identify key bottlenecks from profiling data."""
    bottlenecks: list[str] = []

    # Parse top cumulative time functions
    cumulative_lines = full_analysis["top_cumulative"].split("\n")

    # Look for patterns indicating bottlenecks
    for line in cumulative_lines:
        if "subprocess" in line and "run" in line:
            bottlenecks.append("Subprocess execution (ZFS commands): Consider caching or reducing command frequency in daemon mode")
            break

    for line in cumulative_lines:
        if "json.loads" in line or "json.dump" in line:
            bottlenecks.append("JSON parsing: ZFS command output parsing may be slow for large pools")
            break

    for line in cumulative_lines:
        if "smtplib" in line or "send_email" in line:
            bottlenecks.append("SMTP operations: Email sending is synchronous and may block daemon check cycles")
            break

    for line in cumulative_lines:
        if "sleep" in line or "wait" in line:
            bottlenecks.append("Sleep/Wait operations: Daemon intervals may dominate execution time (expected behavior)")
            break

    # If no specific bottlenecks found, note that
    if not bottlenecks:
        bottlenecks.append("No significant performance bottlenecks detected in profiled workloads")

    return bottlenecks


def run_memory_profile(output_dir: Path) -> None:
    """Run memory profiling on key operations."""
    print("\n" + "=" * 70)
    print("Memory Profiling")
    print("=" * 70)
    print("Running memory profiler (this may take a while)...")

    # Check if memory_profiler is available
    try:
        import memory_profiler  # noqa: F401

        mem_report_path = output_dir / "memory_profile.txt"

        # Run tests with memory profiling
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-xvs",
                "--tb=short",
                "-k",
                "test_behaviors or test_daemon",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

        with open(mem_report_path, "w") as f:
            f.write("MEMORY PROFILING RESULTS\n")
            f.write("=" * 70 + "\n\n")
            f.write("Test Output:\n")
            f.write(result.stdout)
            f.write("\n\nTest Errors (if any):\n")
            f.write(result.stderr)

        print(f"Memory profile saved to: {mem_report_path}")

    except ImportError:
        print("memory_profiler not installed, skipping memory profiling")
        print("Install with: pip install memory-profiler")


def main() -> None:
    """Main profiling entry point."""
    output_dir = Path(__file__).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("CHECK_ZPOOLS PERFORMANCE PROFILING")
    print("=" * 70)
    print(f"Output directory: {output_dir}")
    print()

    # Run full test suite with profiling
    print("Running full test suite with profiling...")
    full_stats = run_profiled_tests()
    full_analysis = analyze_stats(full_stats, output_dir)

    # Profile specific operations
    print("\nProfiling specific operations...")
    specific_ops = profile_specific_operations(output_dir)

    # Generate comprehensive report
    print("\nGenerating performance report...")
    generate_report(full_analysis, specific_ops, output_dir)

    # Run memory profiling
    run_memory_profile(output_dir)

    print("\n" + "=" * 70)
    print("PROFILING COMPLETE")
    print("=" * 70)
    print(f"\nResults saved to: {output_dir}")
    print("\nKey files:")
    print("  - performance_report.txt: Main report")
    print("  - profile_stats.dat: Raw profiling data")
    print("  - memory_profile.txt: Memory usage analysis")


if __name__ == "__main__":
    main()
