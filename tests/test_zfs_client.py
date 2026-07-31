"""Tests for the ZFS command adapter.

Design Philosophy
-----------------
These drive the REAL client against a stand-in executable rather than patching
`subprocess.run`. `ZFSClient` already takes `zpool_path`, so a recording script
on disk is a genuine seam: what the test asserts on is the argv the operating
system would actually have received.

That matters most for `start_scrub`. It is the only mutating call in the
package - it starts a scrub on a live pool - and every other test in the suite
substitutes it with a double. Nothing else checks that the command line it
builds is the one intended.
"""

from __future__ import annotations

import json
import os
import stat
from typing import TYPE_CHECKING

import pytest

from check_zpools.models import ZpoolStatusPayload
from check_zpools.zfs_client import ZFSClient, ZFSCommandError, ZFSNotAvailableError

if TYPE_CHECKING:
    from pathlib import Path


def _recording_zpool(tmp_path: Path, *, exit_code: int = 0, stdout: str = "", stderr: str = "") -> tuple[Path, Path]:
    """Write a fake zpool that records its argv and returns a scripted result.

    Returns
    -------
    tuple[Path, Path]:
        The executable to point ZFSClient at, and the file it writes argv to.
    """
    argv_log = tmp_path / "argv.json"
    script = tmp_path / "zpool"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"open({str(argv_log)!r}, 'w').write(json.dumps(sys.argv[1:]))\n"
        f"sys.stdout.write({stdout!r})\n"
        f"sys.stderr.write({stderr!r})\n"
        f"sys.exit({exit_code})\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return script, argv_log


@pytest.mark.os_posix
class TestStartScrubBuildsTheRightCommand:
    """The mutating call: what argv actually reaches the system."""

    def test_issues_scrub_for_exactly_the_named_pool(self, tmp_path: Path) -> None:
        """When starting a scrub, the command is `zpool scrub <pool>` and nothing else.

        Given: A pool named rpool
        When: start_scrub is called
        Then: The recorded argv is exactly ["scrub", "rpool"]
        """
        script, argv_log = _recording_zpool(tmp_path)

        ZFSClient(zpool_path=script).start_scrub("rpool")

        assert json.loads(argv_log.read_text()) == ["scrub", "rpool"]

    def test_never_passes_the_stop_flag(self, tmp_path: Path) -> None:
        """When starting a scrub, no cancel flag is sent.

        `zpool scrub -s` CANCELS a running scrub. Sending it by accident would
        silently do the opposite of what this command exists to do, and the
        summary would then report a canceled scan as the outcome.
        """
        script, argv_log = _recording_zpool(tmp_path)

        ZFSClient(zpool_path=script).start_scrub("rpool")

        assert "-s" not in json.loads(argv_log.read_text())

    def test_a_refusing_zpool_raises_with_its_stderr(self, tmp_path: Path) -> None:
        """When zpool refuses, the error carries the exit code and stderr.

        Given: A zpool that exits 1 saying a scrub is already running
        When: start_scrub is called
        Then: ZFSCommandError carries both, so the runner can report the reason
        """
        script, _ = _recording_zpool(tmp_path, exit_code=1, stderr="currently scrubbing; use -s to cancel")

        with pytest.raises(ZFSCommandError) as exc:
            ZFSClient(zpool_path=script).start_scrub("rpool")

        assert exc.value.exit_code == 1
        assert "currently scrubbing" in exc.value.stderr

    def test_an_empty_pool_name_is_refused_before_running_anything(self, tmp_path: Path) -> None:
        """When the pool name is empty, nothing is executed.

        A bare `zpool scrub` with no pool is not a no-op to be discovered at
        runtime; it is refused here so no command is issued at all.
        """
        script, argv_log = _recording_zpool(tmp_path)

        with pytest.raises(ValueError, match="pool_name is required"):
            ZFSClient(zpool_path=script).start_scrub("")

        assert not argv_log.exists()


@pytest.mark.os_posix
class TestGetPoolStatusParsesRealOutput:
    """The read path, driven through a real subprocess."""

    def test_returns_the_validated_payload(self, tmp_path: Path) -> None:
        """When zpool emits status JSON, it comes back as the typed payload."""
        payload = {"pools": {"rpool": {"name": "rpool", "state": "ONLINE", "scan_stats": {"function": "SCRUB", "state": "FINISHED"}}}}
        script, argv_log = _recording_zpool(tmp_path, stdout=json.dumps(payload))

        result = ZFSClient(zpool_path=script).get_pool_status()

        assert isinstance(result, ZpoolStatusPayload)
        assert result.pools["rpool"].scan_block.state == "FINISHED"
        assert json.loads(argv_log.read_text()) == ["status", "-j", "--json-int"]

    def test_malformed_json_raises_rather_than_returning_empty(self, tmp_path: Path) -> None:
        """When zpool emits something that is not JSON, the caller hears about it."""
        script, _ = _recording_zpool(tmp_path, stdout="not json at all")

        with pytest.raises(json.JSONDecodeError):
            ZFSClient(zpool_path=script).get_pool_status()


@pytest.mark.os_agnostic
class TestClientConstruction:
    """Discovery of the zpool executable."""

    def test_missing_zpool_is_reported_at_construction(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When zpool is not on PATH, constructing the client says so."""

        def which_finds_nothing(_cmd: str) -> str | None:
            return None

        monkeypatch.setattr("shutil.which", which_finds_nothing)

        with pytest.raises(ZFSNotAvailableError, match="zpool command not found"):
            ZFSClient()

    def test_reports_availability_of_an_explicit_path(self, tmp_path: Path) -> None:
        """When given a path, availability reflects whether that file exists."""
        script, _ = _recording_zpool(tmp_path)

        assert ZFSClient(zpool_path=script).check_zpool_available() is True
        assert ZFSClient(zpool_path=tmp_path / "absent").check_zpool_available() is False


@pytest.mark.os_agnostic
def test_the_recording_stand_in_is_itself_trustworthy(tmp_path: Path) -> None:
    """The fake zpool records argv and honours its scripted exit code.

    Without this, a bug in the stand-in would make every test above pass for
    the wrong reason.
    """
    script, argv_log = _recording_zpool(tmp_path, exit_code=3, stdout="out", stderr="err")

    assert os.access(script, os.X_OK)
    with pytest.raises(ZFSCommandError) as exc:
        ZFSClient(zpool_path=script).start_scrub("tank")

    assert exc.value.exit_code == 3
    assert json.loads(argv_log.read_text()) == ["scrub", "tank"]
