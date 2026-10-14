"""
Download the una-dinosauria/cmu-mocap BVH dataset.

This is a mirror of cgspeed's Motionbuilder-friendly BVH conversion of the
CMU Graphics Lab Motion Capture Database (~2,548 motions, ~144 subjects,
~1.2 GB). We shallow-clone the upstream repo into a directory OUTSIDE the
project tree so the BVH files never end up in version control here. Default
destination is ~/datasets/cmu-mocap (override with --dest or CMU_MOCAP_DIR).

Idempotent: skips clone if a populated dataset directory already exists;
use --force to re-clone from scratch.

Usage:
    python -m scripts.download_cmu_mocap
    python -m scripts.download_cmu_mocap --dest /data/cmu-mocap
    CMU_MOCAP_DIR=/data/cmu-mocap python -m scripts.download_cmu_mocap
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_URL = "https://github.com/una-dinosauria/cmu-mocap"
EXPECTED_BVH_COUNT = 2548
INTEGRITY_TOLERANCE = 0.05  # warn if file count is off by more than 5%

logger = logging.getLogger(__name__)


def default_dest() -> Path:
    env = os.environ.get("CMU_MOCAP_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / "datasets" / "cmu-mocap"


def count_bvh_files(root: Path) -> int:
    return sum(1 for _ in root.rglob("*.bvh"))


def is_populated(dest: Path) -> bool:
    if not dest.exists():
        return False
    return count_bvh_files(dest) > 0


def download(dest: Path, force: bool = False) -> None:
    dest = dest.expanduser().resolve()

    if dest.exists() and force:
        logger.info("Removing existing %s (--force)", dest)
        shutil.rmtree(dest)

    if is_populated(dest):
        n = count_bvh_files(dest)
        logger.info("Dataset already present at %s (%d BVH files); skipping clone", dest, n)
        _integrity_check(n)
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Cloning %s into %s (--depth 1, ~1.2 GB)...", REPO_URL, dest)

    cmd = ["git", "clone", "--depth", "1", REPO_URL, str(dest)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("git clone failed: %s", result.stderr)
        raise RuntimeError(f"git clone failed with code {result.returncode}")

    n = count_bvh_files(dest)
    logger.info("Clone complete: %d BVH files at %s", n, dest)
    _integrity_check(n)


def _integrity_check(n_bvh: int) -> None:
    delta = abs(n_bvh - EXPECTED_BVH_COUNT) / EXPECTED_BVH_COUNT
    if delta > INTEGRITY_TOLERANCE:
        logger.warning(
            "BVH file count %d is %.0f%% off expected %d — upstream layout may have changed",
            n_bvh, delta * 100, EXPECTED_BVH_COUNT,
        )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s — %(message)s",
    )
    parser = argparse.ArgumentParser(description="Download CMU Mocap BVH dataset")
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Target directory (default: $CMU_MOCAP_DIR or ~/datasets/cmu-mocap)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-clone even if target already exists",
    )
    args = parser.parse_args(argv)

    dest = args.dest if args.dest is not None else default_dest()
    download(dest, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
