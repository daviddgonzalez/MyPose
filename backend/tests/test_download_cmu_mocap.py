"""
Tests for the CMU Mocap download script.

We mock subprocess.run so the tests never touch the network. The integrity
warning is verified via the logging capture fixture.
"""

import logging
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from scripts import download_cmu_mocap as dlmod


def test_default_dest_uses_env_var_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv("CMU_MOCAP_DIR", str(tmp_path / "custom"))
    assert dlmod.default_dest() == tmp_path / "custom"


def test_default_dest_falls_back_to_home(monkeypatch):
    monkeypatch.delenv("CMU_MOCAP_DIR", raising=False)
    expected = Path.home() / "datasets" / "cmu-mocap"
    assert dlmod.default_dest() == expected


def test_download_skips_when_already_populated(tmp_path, caplog):
    # Pre-populate target dir with a fake BVH file.
    target = tmp_path / "cmu-mocap"
    target.mkdir()
    (target / "fake_subject").mkdir()
    (target / "fake_subject" / "01.bvh").write_text("HIERARCHY\n")

    with patch.object(dlmod.subprocess, "run") as mock_run:
        with caplog.at_level(logging.INFO):
            dlmod.download(target, force=False)
        mock_run.assert_not_called()
    assert any("skipping clone" in rec.message for rec in caplog.records)


def test_download_runs_git_clone_when_empty(tmp_path, caplog):
    target = tmp_path / "cmu-mocap"

    def fake_run(cmd, capture_output, text):
        # Simulate a successful clone by creating one fake BVH file.
        target.mkdir(parents=True, exist_ok=True)
        (target / "01.bvh").write_text("HIERARCHY\n")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(dlmod.subprocess, "run", side_effect=fake_run) as mock_run:
        with caplog.at_level(logging.INFO):
            dlmod.download(target, force=False)
        mock_run.assert_called_once()
        cmd = mock_run.call_args.args[0]
        assert cmd[:3] == ["git", "clone", "--depth"]
        assert cmd[3] == "1"
        assert dlmod.REPO_URL in cmd


def test_download_force_wipes_existing_dir(tmp_path):
    target = tmp_path / "cmu-mocap"
    target.mkdir()
    (target / "old.bvh").write_text("HIERARCHY\n")

    def fake_run(cmd, capture_output, text):
        target.mkdir(parents=True, exist_ok=True)
        (target / "new.bvh").write_text("HIERARCHY\n")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.object(dlmod.subprocess, "run", side_effect=fake_run):
        dlmod.download(target, force=True)

    # Old file should be gone, new one present.
    assert not (target / "old.bvh").exists()
    assert (target / "new.bvh").exists()


def test_download_raises_on_git_failure(tmp_path):
    target = tmp_path / "cmu-mocap"
    fail = MagicMock(returncode=128, stdout="", stderr="fatal: ...")
    with patch.object(dlmod.subprocess, "run", return_value=fail):
        with pytest.raises(RuntimeError, match="git clone failed"):
            dlmod.download(target, force=False)


def test_integrity_check_warns_on_low_count(caplog):
    with caplog.at_level(logging.WARNING):
        dlmod._integrity_check(n_bvh=100)  # way off the ~2548 expected
    assert any("upstream layout may have changed" in rec.message for rec in caplog.records)


def test_integrity_check_silent_when_in_tolerance(caplog):
    with caplog.at_level(logging.WARNING):
        dlmod._integrity_check(n_bvh=dlmod.EXPECTED_BVH_COUNT)
    assert not any("upstream layout may have changed" in rec.message for rec in caplog.records)
