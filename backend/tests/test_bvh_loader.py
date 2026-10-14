"""
Tests for the BVH parser + forward kinematics.

Uses the hand-crafted fixture at tests/fixtures/mini.bvh, a 3-joint skeleton
(Hips → Spine → Head) with 4 motion frames designed so the FK output is
hand-computable and asserts both translation and rotation behavior.
"""

from pathlib import Path

import numpy as np
import pytest

from app.ml.bvh_loader import parse_bvh

FIXTURE = Path(__file__).parent / "fixtures" / "mini.bvh"


def test_parse_returns_joint_names_in_hierarchy_order():
    bvh = parse_bvh(FIXTURE, drop_first_frame=False)
    assert bvh.joint_names == ["Hips", "Spine", "Head"]


def test_fps_from_frame_time():
    bvh = parse_bvh(FIXTURE, drop_first_frame=False)
    # Frame Time 0.008333333 → 120 fps.
    assert bvh.fps == pytest.approx(120.0, rel=1e-3)


def test_fk_identity_frame_stacks_joints_along_y():
    bvh = parse_bvh(FIXTURE, drop_first_frame=False)
    # Frame 0: all channels zero → joints stack at the bind-pose offsets.
    assert bvh.positions[0].shape == (3, 3)
    np.testing.assert_allclose(bvh.positions[0, 0], [0, 0, 0], atol=1e-5)   # Hips
    np.testing.assert_allclose(bvh.positions[0, 1], [0, 10, 0], atol=1e-5)  # Spine
    np.testing.assert_allclose(bvh.positions[0, 2], [0, 15, 0], atol=1e-5)  # Head


def test_fk_root_translation_shifts_all_joints():
    bvh = parse_bvh(FIXTURE, drop_first_frame=False)
    # Frame 2: root translated to (1, 2, 3), no rotations.
    np.testing.assert_allclose(bvh.positions[2, 0], [1, 2, 3], atol=1e-5)
    np.testing.assert_allclose(bvh.positions[2, 1], [1, 12, 3], atol=1e-5)
    np.testing.assert_allclose(bvh.positions[2, 2], [1, 17, 3], atol=1e-5)


def test_fk_rotation_propagates_to_children():
    bvh = parse_bvh(FIXTURE, drop_first_frame=False)
    # Frame 3: Spine Z-rotation 90°. Spine stays at (0,10,0); Head's offset
    # (0,5,0) rotates with Spine into (-5, 0, 0) before adding Spine origin,
    # giving Head world position (-5, 10, 0).
    np.testing.assert_allclose(bvh.positions[3, 0], [0, 0, 0], atol=1e-5)
    np.testing.assert_allclose(bvh.positions[3, 1], [0, 10, 0], atol=1e-5)
    np.testing.assert_allclose(bvh.positions[3, 2], [-5, 10, 0], atol=1e-5)


def test_drop_first_frame_removes_one_frame():
    bvh_kept = parse_bvh(FIXTURE, drop_first_frame=False)
    bvh_dropped = parse_bvh(FIXTURE, drop_first_frame=True)
    assert bvh_kept.positions.shape[0] == 4
    assert bvh_dropped.positions.shape[0] == 3
    # First retained frame must equal frame 1 of the un-dropped version.
    np.testing.assert_allclose(bvh_dropped.positions[0], bvh_kept.positions[1])
