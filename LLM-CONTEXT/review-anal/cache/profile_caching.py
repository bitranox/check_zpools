#!/usr/bin/env python3
"""Profile caching opportunities in check_zpools.

This script identifies functions that could benefit from caching by:
1. Analyzing function call patterns in tests
2. Measuring actual execution times
3. Identifying repeated computations
4. Quantifying potential performance gains
"""

import cProfile
import io
import pstats
import sys
import time
from pathlib import Path
from typing import Any

# Add src to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

import pytest  # noqa: E402


def profile_test_suite() -> pstats.Stats:
    """Run test suite with profiling enabled.

    Returns:
        pstats.Stats: Profiling statistics from test execution
    """
    profiler = cProfile.Profile()

    print("Profiling test suite execution...")
    profiler.enable()

    # Run pytest programmatically (excluding problematic test_scripts.py)
    pytest.main(
        [
            str(project_root / "tests"),
            "--ignore=tests/test_scripts.py",
            "-v",
            "--tb=short",
            "-q",  # Quiet mode for cleaner output
        ]
    )

    profiler.disable()

    return pstats.Stats(profiler)


def analyze_hot_functions(stats: pstats.Stats) -> dict[str, Any]:
    """Analyze profiling stats to identify caching candidates.

    Parameters:
        stats: Profiling statistics

    Returns:
        Dictionary with analysis results
    """
    # Redirect stdout to capture stats
    stream = io.StringIO()
    stats.stream = stream

    # Sort by cumulative time
    stats.sort_stats("cumulative")
    stats.print_stats(100)  # Top 100 functions

    cumulative_output = stream.getvalue()

    # Sort by number of calls
    stream = io.StringIO()
    stats.stream = stream
    stats.sort_stats("ncalls")
    stats.print_stats(100)

    ncalls_output = stream.getvalue()

    # Sort by time per call
    stream = io.StringIO()
    stats.stream = stream
    stats.sort_stats("tottime")
    stats.print_stats(100)

    tottime_output = stream.getvalue()

    return {
        "cumulative": cumulative_output,
        "ncalls": ncalls_output,
        "tottime": tottime_output,
    }


def identify_caching_candidates(stats: pstats.Stats) -> list[dict[str, Any]]:
    """Identify specific functions that would benefit from caching.

    Criteria:
    - Called multiple times (ncalls > 10)
    - Significant cumulative time
    - Likely to have repeated inputs (parsing, config loading, etc.)

    Parameters:
        stats: Profiling statistics

    Returns:
        List of candidate functions with metrics
    """
    candidates = []

    # Get raw stats
    raw_stats = stats.stats

    # Focus on check_zpools module functions
    for func_key, (cc, nc, tt, ct, callers) in raw_stats.items():
        filename, lineno, funcname = func_key

        # Filter for check_zpools module functions
        if "check_zpools" not in filename:
            continue

        # Skip test files
        if "test_" in filename:
            continue

        # Filter by criteria
        if nc > 5 and ct > 0.001:  # Called >5 times, >1ms cumulative
            candidates.append(
                {
                    "function": funcname,
                    "module": filename.split("/")[-1],
                    "ncalls": nc,
                    "tottime": tt,
                    "cumtime": ct,
                    "percall_tot": tt / nc if nc > 0 else 0,
                    "percall_cum": ct / nc if nc > 0 else 0,
                    "filename": filename,
                    "lineno": lineno,
                }
            )

    # Sort by potential impact (ncalls * cumtime)
    candidates.sort(key=lambda x: x["ncalls"] * x["cumtime"], reverse=True)

    return candidates


def benchmark_existing_caches() -> dict[str, Any]:
    """Benchmark functions that already have caching to validate benefits.

    Returns:
        Dictionary with benchmark results
    """
    from check_zpools.zfs_parser import ZFSParser
    from check_zpools.models import PoolHealth
    from check_zpools.config import get_config

    results = {}

    # Test 1: _parse_size_to_bytes (already cached)
    parser = ZFSParser()
    test_sizes = ["1000000", "1.5T", "500G", "100M"] * 100  # Repeat for cache hits

    # Without cache (measure first call)
    start = time.perf_counter()
    for size_str in ["1000000", "1.5T", "500G", "100M"]:
        parser._parse_size_to_bytes(size_str)
    first_call_time = time.perf_counter() - start

    # With cache (measure subsequent calls)
    start = time.perf_counter()
    for size_str in test_sizes:
        parser._parse_size_to_bytes(size_str)
    cached_time = time.perf_counter() - start

    results["parse_size_to_bytes"] = {
        "first_4_calls": first_call_time,
        "400_calls_cached": cached_time,
        "speedup": first_call_time / (cached_time / 100) if cached_time > 0 else 0,
        "cache_hit_ratio": 396 / 400,  # 4 unique + 396 repeats
    }

    # Test 2: _parse_health_state (already cached)
    health_values = ["ONLINE", "DEGRADED", "FAULTED"] * 100
    pool_names = ["pool1", "pool2", "pool3"] * 100

    start = time.perf_counter()
    for health, pool in zip(["ONLINE", "DEGRADED", "FAULTED"], ["pool1", "pool2", "pool3"]):
        parser._parse_health_state(health, pool)
    first_call_time = time.perf_counter() - start

    start = time.perf_counter()
    for health, pool in zip(health_values, pool_names):
        parser._parse_health_state(health, pool)
    cached_time = time.perf_counter() - start

    results["parse_health_state"] = {
        "first_3_calls": first_call_time,
        "300_calls_cached": cached_time,
        "speedup": first_call_time / (cached_time / 100) if cached_time > 0 else 0,
        "cache_hit_ratio": 297 / 300,
    }

    # Test 3: get_config (already cached)
    start = time.perf_counter()
    _ = get_config()
    first_call_time = time.perf_counter() - start

    start = time.perf_counter()
    for _ in range(100):
        _ = get_config()
    cached_time = time.perf_counter() - start

    results["get_config"] = {
        "first_call": first_call_time,
        "100_calls_cached": cached_time,
        "speedup": first_call_time / (cached_time / 100) if cached_time > 0 else 0,
        "cache_hit_ratio": 99 / 100,
    }

    # Test 4: Enum method caching
    health_checks = [PoolHealth.ONLINE, PoolHealth.DEGRADED, PoolHealth.FAULTED] * 100

    start = time.perf_counter()
    for h in [PoolHealth.ONLINE, PoolHealth.DEGRADED, PoolHealth.FAULTED]:
        h.is_healthy()
        h.is_critical()
    first_call_time = time.perf_counter() - start

    start = time.perf_counter()
    for h in health_checks:
        h.is_healthy()
        h.is_critical()
    cached_time = time.perf_counter() - start

    results["health_enum_methods"] = {
        "first_calls": first_call_time,
        "cached_calls": cached_time,
        "speedup": first_call_time / (cached_time / 100) if cached_time > 0 else 0,
    }

    return results


def analyze_potential_cache_candidates() -> dict[str, Any]:
    """Analyze functions that don't have caching but might benefit.

    Returns:
        Dictionary with candidate analysis
    """
    candidates = {}

    # Candidate 1: _get_property_value - called many times with same keys
    candidates["_get_property_value"] = {
        "location": "zfs_parser.py:336",
        "current_status": "No caching",
        "call_pattern": 'Called repeatedly for "health", "capacity", "size", "allocated", "free"',
        "recommendation": "Could cache with @lru_cache(maxsize=16) on a per-parser basis",
        "expected_benefit": "Low - function is very simple (dict lookups)",
        "priority": "LOW",
    }

    # Candidate 2: _extract_capacity_metrics - called once per pool
    candidates["_extract_capacity_metrics"] = {
        "location": "zfs_parser.py:622",
        "current_status": "No caching",
        "call_pattern": "Called once per pool per check",
        "recommendation": "No caching - results vary per pool and check",
        "expected_benefit": "None - not a pure function (results change)",
        "priority": "N/A",
    }

    # Candidate 3: _build_monitor_config - called when starting daemon
    candidates["_build_monitor_config"] = {
        "location": "behaviors.py:354",
        "current_status": "No caching",
        "call_pattern": "Called 1-2 times per application run",
        "recommendation": "No caching - called infrequently",
        "expected_benefit": "None - infrequent calls",
        "priority": "N/A",
    }

    # Candidate 4: JSON parsing in ZFSClient
    candidates["json_loads_in_zfs_client"] = {
        "location": "zfs_client.py:412",
        "current_status": "No caching",
        "call_pattern": "Called every time pool data is fetched",
        "recommendation": "No caching - data changes on every call",
        "expected_benefit": "None - not repeatable data",
        "priority": "N/A",
    }

    return candidates


def main():
    """Run complete caching analysis."""
    output_dir = Path(__file__).parent

    print("=" * 80)
    print("CACHING ANALYSIS FOR check_zpools")
    print("=" * 80)
    print()

    # 1. Benchmark existing caches
    print("1. Benchmarking existing @lru_cache decorators...")
    print("-" * 80)
    existing_results = benchmark_existing_caches()

    for func_name, results in existing_results.items():
        print(f"\n{func_name}:")
        for key, value in results.items():
            if isinstance(value, float):
                if "time" in key:
                    print(f"  {key}: {value * 1000:.4f} ms")
                else:
                    print(f"  {key}: {value:.2f}x")
            else:
                print(f"  {key}: {value}")

    # Save detailed results
    with open(output_dir / "existing_cache_benchmarks.txt", "w") as f:
        f.write("EXISTING CACHE PERFORMANCE BENCHMARKS\n")
        f.write("=" * 80 + "\n\n")
        for func_name, results in existing_results.items():
            f.write(f"{func_name}:\n")
            for key, value in results.items():
                if isinstance(value, float):
                    if "time" in key:
                        f.write(f"  {key}: {value * 1000:.4f} ms\n")
                    else:
                        f.write(f"  {key}: {value:.2f}x\n")
                else:
                    f.write(f"  {key}: {value}\n")
            f.write("\n")

    print("\n")
    print("2. Analyzing potential cache candidates...")
    print("-" * 80)
    candidates = analyze_potential_cache_candidates()

    for func_name, analysis in candidates.items():
        print(f"\n{func_name}:")
        for key, value in analysis.items():
            print(f"  {key}: {value}")

    # Save candidate analysis
    with open(output_dir / "cache_candidates.txt", "w") as f:
        f.write("POTENTIAL CACHING CANDIDATES\n")
        f.write("=" * 80 + "\n\n")
        for func_name, analysis in candidates.items():
            f.write(f"{func_name}:\n")
            for key, value in analysis.items():
                f.write(f"  {key}: {value}\n")
            f.write("\n")

    print("\n")
    print("3. Running profiler on test suite...")
    print("-" * 80)

    # Profile test suite
    try:
        stats = profile_test_suite()

        # Analyze results
        analysis = analyze_hot_functions(stats)

        # Save profiling reports
        for report_name, content in analysis.items():
            filename = output_dir / f"profile_{report_name}.txt"
            with open(filename, "w") as f:
                f.write(f"PROFILING REPORT - SORTED BY {report_name.upper()}\n")
                f.write("=" * 80 + "\n\n")
                f.write(content)
            print(f"Saved: {filename}")

        # Identify specific candidates from profiling
        profiled_candidates = identify_caching_candidates(stats)

        with open(output_dir / "profiled_candidates.txt", "w") as f:
            f.write("CACHING CANDIDATES FROM PROFILING\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Found {len(profiled_candidates)} candidates\n\n")

            for i, candidate in enumerate(profiled_candidates[:20], 1):  # Top 20
                f.write(f"{i}. {candidate['function']} ({candidate['module']})\n")
                f.write(f"   Location: {candidate['filename']}:{candidate['lineno']}\n")
                f.write(f"   Calls: {candidate['ncalls']}\n")
                f.write(f"   Total time: {candidate['tottime'] * 1000:.2f} ms\n")
                f.write(f"   Cumulative time: {candidate['cumtime'] * 1000:.2f} ms\n")
                f.write(f"   Per-call (tot): {candidate['percall_tot'] * 1000:.4f} ms\n")
                f.write(f"   Per-call (cum): {candidate['percall_cum'] * 1000:.4f} ms\n")
                f.write(f"   Impact score: {candidate['ncalls'] * candidate['cumtime']:.4f}\n")
                f.write("\n")

        print(f"\nSaved: {output_dir / 'profiled_candidates.txt'}")

    except Exception as e:
        print(f"Warning: Profiling failed: {e}")
        print("Continuing with static analysis only...")

    print("\n")
    print("=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)
    print(f"\nResults saved to: {output_dir}")
    print("\nFiles generated:")
    print("  - existing_cache_benchmarks.txt")
    print("  - cache_candidates.txt")
    print("  - profile_cumulative.txt")
    print("  - profile_ncalls.txt")
    print("  - profile_tottime.txt")
    print("  - profiled_candidates.txt")


if __name__ == "__main__":
    main()
