"""
Tests for the CMU → MediaPipe joint retargeting.

The retargeting is a pure index permutation + visibility flag, so these
tests just verify that mapped MediaPipe slots receive the right CMU joint
data and unmapped slots stay zero with visibility=0.
"""

import numpy as np

from app.ml.cmu_to_mediapipe import retarget, _CMU_TO_MEDIAPIPE


def _make_cmu_clip(joint_names: list[str]) -> np.ndarray:
    """Build a (2, N, 3) array where joint k has unique sentinel coords."""
    T, N = 2, len(joint_names)
    arr = np.zeros((T, N, 3), dtype=np.float32)
    for k in range(N):
        arr[:, k, 0] = float(k * 100 + 1)
        arr[:, k, 1] = float(k * 100 + 2)
        arr[:, k, 2] = float(k * 100 + 3)
    return arr


def test_retarget_returns_t_33_4_shape():
    joint_names = list(_CMU_TO_MEDIAPIPE.keys())
    cmu = _make_cmu_clip(joint_names)
    out = retarget(cmu, joint_names)
    assert out.shape == (2, 33, 4)
    assert out.dtype == np.float32


def test_mapped_joints_carry_data_with_visibility_one():
    joint_names = list(_CMU_TO_MEDIAPIPE.keys())
    cmu = _make_cmu_clip(joint_names)
    out = retarget(cmu, joint_names)

    for cmu_name, mp_idx in _CMU_TO_MEDIAPIPE.items():
        k = joint_names.index(cmu_name)
        np.testing.assert_allclose(out[:, mp_idx, :3], cmu[:, k, :])
        np.testing.assert_array_equal(out[:, mp_idx, 3], 1.0)


def test_unmapped_joints_stay_zero_with_visibility_zero():
    joint_names = list(_CMU_TO_MEDIAPIPE.keys())
    cmu = _make_cmu_clip(joint_names)
    out = retarget(cmu, joint_names)

    mapped_mp_indices = set(_CMU_TO_MEDIAPIPE.values())
    for mp_idx in range(33):
        if mp_idx in mapped_mp_indices:
            continue
        np.testing.assert_array_equal(out[:, mp_idx, :], 0.0)


def test_missing_cmu_joints_are_silently_skipped():
    # Real-world: BVH may have extra joints or omit some — retarget should
    # only fill MP slots whose CMU source is present, leaving the rest zero.
    partial = ["LeftUpLeg", "RightUpLeg"]  # only hips
    cmu = _make_cmu_clip(partial)
    out = retarget(cmu, partial)
    np.testing.assert_allclose(out[:, 23, :3], cmu[:, 0, :])  # left hip
    np.testing.assert_allclose(out[:, 24, :3], cmu[:, 1, :])  # right hip
    # No knees / shoulders should be filled.
    np.testing.assert_array_equal(out[:, 11, 3], 0.0)
    np.testing.assert_array_equal(out[:, 25, 3], 0.0)


def test_input_shape_validation():
    import pytest
    bad = np.zeros((5, 4), dtype=np.float32)
    with pytest.raises(ValueError):
        retarget(bad, ["a", "b", "c", "d"])  # type: ignore[arg-type]
