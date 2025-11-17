"""ZFS pool monitoring logic with threshold checking.

Purpose
-------
Check ZFS pools against configured thresholds and generate issues for problems.
Implements business logic for determining when pools require attention.

Contents
--------
* :class:`MonitorConfig` – Configuration for monitoring thresholds
* :class:`PoolMonitor` – Main monitoring logic coordinator

System Role
-----------
Bridge between data collection (parsers) and alerting (notifications).
Applies business rules to determine issue severity and generates actionable
alerts.

Architecture Notes
------------------
- Configuration injected via constructor (testable)
- Pure functions for threshold checking (deterministic)
- Each check returns issues or None (clear contract)
- Severity determination is centralized and consistent
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from .models import CheckResult, PoolHealth, PoolIssue, PoolStatus, Severity  # noqa: F401 - PoolHealth used in doctests  # pyright: ignore[reportUnusedImport]

logger = logging.getLogger(__name__)


@dataclass
class MonitorConfig:
    """Configuration for pool monitoring thresholds.

    Why
        Centralizes threshold configuration, making it easy to override
        via config files or environment variables.

    Attributes
    ----------
    capacity_warning_percent:
        Capacity percentage triggering WARNING (default: 80)
    capacity_critical_percent:
        Capacity percentage triggering CRITICAL (default: 90)
    scrub_max_age_days:
        Maximum days since last scrub before WARNING (default: 30)
    read_errors_warning:
        Read error count triggering WARNING (default: 1)
    write_errors_warning:
        Write error count triggering WARNING (default: 1)
    checksum_errors_warning:
        Checksum error count triggering WARNING (default: 1)

    Examples
    --------
    >>> config = MonitorConfig(
    ...     capacity_warning_percent=75,
    ...     capacity_critical_percent=85,
    ...     scrub_max_age_days=7,
    ... )
    >>> config.capacity_warning_percent
    75
    """

    capacity_warning_percent: int = 80
    capacity_critical_percent: int = 90
    scrub_max_age_days: int = 30
    read_errors_warning: int = 1
    write_errors_warning: int = 1
    checksum_errors_warning: int = 1

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.capacity_warning_percent >= self.capacity_critical_percent:
            raise ValueError("capacity_warning_percent must be less than capacity_critical_percent")

        if self.capacity_warning_percent < 0 or self.capacity_critical_percent > 100:
            raise ValueError("Capacity percentages must be between 0 and 100")


class PoolMonitor:
    """Monitor ZFS pools and detect issues based on thresholds.

    Why
        Centralizes monitoring logic, making it easy to test and maintain.
        Separates concern of threshold checking from data collection and
        alerting.

    Attributes
    ----------
    config:
        Monitoring threshold configuration

    Examples
    --------
    >>> config = MonitorConfig()
    >>> monitor = PoolMonitor(config)
    >>> pool = PoolStatus(...)  # doctest: +SKIP
    >>> issues = monitor.check_pool(pool)  # doctest: +SKIP
    """

    def __init__(self, config: MonitorConfig):
        """Initialize pool monitor with configuration.

        Parameters
        ----------
        config:
            Threshold configuration for monitoring
        """
        self.config = config
        logger.info(
            "PoolMonitor initialized",
            extra={
                "capacity_warning": config.capacity_warning_percent,
                "capacity_critical": config.capacity_critical_percent,
                "scrub_max_age_days": config.scrub_max_age_days,
            },
        )

    def check_pool(self, pool: PoolStatus) -> list[PoolIssue]:
        """Check single pool and return list of detected issues.

        Why
            Allows checking individual pools for testing and incremental
            processing.

        Parameters
        ----------
        pool:
            Pool status to check

        Returns
        -------
        list[PoolIssue]:
            List of detected issues (empty if pool is healthy)

        Examples
        --------
        >>> config = MonitorConfig(capacity_warning_percent=80)
        >>> monitor = PoolMonitor(config)
        >>> pool = PoolStatus(
        ...     name="rpool", health=PoolHealth.ONLINE, capacity_percent=85.0,
        ...     size_bytes=1000, allocated_bytes=850, free_bytes=150,
        ...     read_errors=0, write_errors=0, checksum_errors=0,
        ...     last_scrub=None, scrub_errors=0, scrub_in_progress=False
        ... )
        >>> issues = monitor.check_pool(pool)
        >>> len(issues) > 0  # Should have capacity warning
        True
        """
        issues: list[PoolIssue] = []

        logger.debug(f"Checking pool: {pool.name}")

        # Check health state
        health_issue = self._check_health(pool)
        if health_issue:
            issues.append(health_issue)

        # Check capacity
        capacity_issue = self._check_capacity(pool)
        if capacity_issue:
            issues.append(capacity_issue)

        # Check for errors
        error_issues = self._check_errors(pool)
        issues.extend(error_issues)

        # Check scrub status
        scrub_issue = self._check_scrub(pool)
        if scrub_issue:
            issues.append(scrub_issue)

        logger.debug(
            f"Pool check complete: {pool.name}",
            extra={"pool_name": pool.name, "issues_found": len(issues)},
        )

        return issues

    def check_all_pools(self, pools: dict[str, PoolStatus]) -> CheckResult:
        """Check all pools and return aggregated result.

        Why
            Main entry point for monitoring. Returns complete picture of
            all pool states.

        Parameters
        ----------
        pools:
            Dictionary of pool statuses from parser

        Returns
        -------
        CheckResult:
            Complete check result with all pools and issues

        Examples
        --------
        >>> config = MonitorConfig()
        >>> monitor = PoolMonitor(config)
        >>> pools = {"rpool": PoolStatus(...)}  # doctest: +SKIP
        >>> result = monitor.check_all_pools(pools)  # doctest: +SKIP
        >>> result.overall_severity  # doctest: +SKIP
        <Severity.OK: 'OK'>
        """
        timestamp = datetime.now(timezone.utc)
        all_issues: list[PoolIssue] = []
        pool_list: list[PoolStatus] = []

        logger.info(f"Checking {len(pools)} pools")

        for pool_status in pools.values():
            pool_list.append(pool_status)
            pool_issues = self.check_pool(pool_status)
            all_issues.extend(pool_issues)

        # Determine overall severity
        if not all_issues:
            overall_severity = Severity.OK
        else:
            overall_severity = max(issue.severity for issue in all_issues)

        result = CheckResult(
            timestamp=timestamp,
            pools=pool_list,
            issues=all_issues,
            overall_severity=overall_severity,
        )

        logger.info(
            "Pool check completed",
            extra={
                "pools_checked": len(pools),
                "issues_found": len(all_issues),
                "overall_severity": overall_severity.value,
            },
        )

        return result

    def _check_health(self, pool: PoolStatus) -> PoolIssue | None:
        """Check pool health status.

        Parameters
        ----------
        pool:
            Pool to check

        Returns
        -------
        PoolIssue | None:
            Issue if pool health is not ONLINE, None otherwise
        """
        if pool.health.is_healthy():
            return None

        # Determine severity based on health state
        if pool.health.is_critical():
            severity = Severity.CRITICAL
        else:
            severity = Severity.WARNING

        return PoolIssue(
            pool_name=pool.name,
            severity=severity,
            category="health",
            message=f"Pool is {pool.health.value} (expected: ONLINE)",
            details={
                "current_state": pool.health.value,
                "expected_state": "ONLINE",
            },
        )

    def _check_capacity(self, pool: PoolStatus) -> PoolIssue | None:
        """Check pool capacity against thresholds.

        Parameters
        ----------
        pool:
            Pool to check

        Returns
        -------
        PoolIssue | None:
            Issue if capacity exceeds thresholds, None otherwise
        """
        if pool.capacity_percent >= self.config.capacity_critical_percent:
            return PoolIssue(
                pool_name=pool.name,
                severity=Severity.CRITICAL,
                category="capacity",
                message=f"Pool at {pool.capacity_percent:.1f}% capacity (critical threshold: {self.config.capacity_critical_percent}%)",
                details={
                    "capacity_percent": pool.capacity_percent,
                    "threshold": self.config.capacity_critical_percent,
                    "size_bytes": pool.size_bytes,
                    "allocated_bytes": pool.allocated_bytes,
                    "free_bytes": pool.free_bytes,
                },
            )

        if pool.capacity_percent >= self.config.capacity_warning_percent:
            return PoolIssue(
                pool_name=pool.name,
                severity=Severity.WARNING,
                category="capacity",
                message=f"Pool at {pool.capacity_percent:.1f}% capacity (warning threshold: {self.config.capacity_warning_percent}%)",
                details={
                    "capacity_percent": pool.capacity_percent,
                    "threshold": self.config.capacity_warning_percent,
                    "size_bytes": pool.size_bytes,
                    "allocated_bytes": pool.allocated_bytes,
                    "free_bytes": pool.free_bytes,
                },
            )

        return None

    def _check_errors(self, pool: PoolStatus) -> list[PoolIssue]:
        """Check pool for I/O and checksum errors.

        Parameters
        ----------
        pool:
            Pool to check

        Returns
        -------
        list[PoolIssue]:
            List of error-related issues
        """
        issues: list[PoolIssue] = []

        # Check read errors
        # Only trigger warning if errors are present (> 0) AND meet threshold
        if pool.read_errors > 0 and pool.read_errors >= self.config.read_errors_warning:
            issues.append(
                PoolIssue(
                    pool_name=pool.name,
                    severity=Severity.WARNING,
                    category="errors",
                    message=f"Pool has {pool.read_errors} read errors",
                    details={
                        "read_errors": pool.read_errors,
                        "threshold": self.config.read_errors_warning,
                    },
                )
            )

        # Check write errors
        # Only trigger warning if errors are present (> 0) AND meet threshold
        if pool.write_errors > 0 and pool.write_errors >= self.config.write_errors_warning:
            issues.append(
                PoolIssue(
                    pool_name=pool.name,
                    severity=Severity.WARNING,
                    category="errors",
                    message=f"Pool has {pool.write_errors} write errors",
                    details={
                        "write_errors": pool.write_errors,
                        "threshold": self.config.write_errors_warning,
                    },
                )
            )

        # Check checksum errors (more serious)
        # Only trigger warning if errors are present (> 0) AND meet threshold
        if pool.checksum_errors > 0 and pool.checksum_errors >= self.config.checksum_errors_warning:
            issues.append(
                PoolIssue(
                    pool_name=pool.name,
                    severity=Severity.WARNING,
                    category="errors",
                    message=f"Pool has {pool.checksum_errors} checksum errors (possible data corruption)",
                    details={
                        "checksum_errors": pool.checksum_errors,
                        "threshold": self.config.checksum_errors_warning,
                    },
                )
            )

        return issues

    def _check_scrub(self, pool: PoolStatus) -> PoolIssue | None:
        """Check scrub status and age.

        Parameters
        ----------
        pool:
            Pool to check

        Returns
        -------
        PoolIssue | None:
            Issue if scrub is old or has errors, None otherwise
        """
        # Check for scrub errors
        if pool.scrub_errors > 0:
            return PoolIssue(
                pool_name=pool.name,
                severity=Severity.WARNING,
                category="scrub",
                message=f"Last scrub found {pool.scrub_errors} errors",
                details={
                    "scrub_errors": pool.scrub_errors,
                    "last_scrub": pool.last_scrub.isoformat() if pool.last_scrub else None,
                },
            )

        # Check scrub age (only if scrub_max_age_days > 0)
        if self.config.scrub_max_age_days > 0:
            if pool.last_scrub is None:
                return PoolIssue(
                    pool_name=pool.name,
                    severity=Severity.INFO,
                    category="scrub",
                    message="Pool has never been scrubbed",
                    details={"last_scrub": None},
                )

            # Calculate age
            now = datetime.now(timezone.utc)
            scrub_age = now - pool.last_scrub
            age_days = scrub_age.days

            if age_days > self.config.scrub_max_age_days:
                return PoolIssue(
                    pool_name=pool.name,
                    severity=Severity.INFO,
                    category="scrub",
                    message=f"Pool scrub is {age_days} days old (max age: {self.config.scrub_max_age_days} days)",
                    details={
                        "last_scrub": pool.last_scrub.isoformat(),
                        "age_days": age_days,
                        "max_age_days": self.config.scrub_max_age_days,
                    },
                )

        return None


__all__ = [
    "MonitorConfig",
    "PoolMonitor",
]
