"""
Tests for per-rep segmentation and squat grading.

Synthetic skeletons are built from a simple 2D squat model so the expected
depth, lean and knee tracking of every rep are known exactly.
"""

import numpy as np
import pytest

from app.services.analysis import analyze_session
from app.services.reps import grade_reps, segment_reps, supports

ASPECT = 4 / 3
FPS = 30.0
THIGH = 0.2
SHIN = 0.2
TORSO = 0.25


def _squat_frames(
    depths_deg: list[float],
    view: str = "side",
    lean_deg: float = 30.0,
    knee_cave: float = 0.0,
    rep_seconds: float = 2.0,
    rest_seconds: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Build (T, 33, 4) landmarks for a sequence of squats.

    depths_deg: max thigh angle from vertical per rep (90 = parallel).
    lean_deg: torso lean from vertical at the bottom (scales with depth).
    knee_cave: fraction the knees move inward at the bottom (front view).
    """
    thetas: list[float] = []
    rest = [0.0] * int(rest_seconds * FPS)
    thetas += rest
    for depth in depths_deg:
        n = int(rep_seconds * FPS)
        phase = np.linspace(0, 2 * np.pi, n)
        thetas += list(depth * (1 - np.cos(phase)) / 2)
        thetas += rest
    theta = np.radians(np.array(thetas))
    t = len(theta)
    frac = theta / max(np.radians(max(depths_deg)), 1e-6) if depths_deg else theta

    lm = np.zeros((t, 33, 4))
    lm[:, :, 3] = 1.0
    ankle = np.array([0.5 * ASPECT, 0.9])
    phi = theta / 2  # shin tilts half as much as the thigh

    if view == "side":
        knee = ankle + SHIN * np.stack([np.sin(phi), -np.cos(phi)], axis=1)
        hip = knee + THIGH * np.stack([-np.sin(theta), -np.cos(theta)], axis=1)
        lean = np.radians(lean_deg) * frac
        shoulder = hip + TORSO * np.stack([np.sin(lean), -np.cos(lean)], axis=1)
        for idx, point in [(23, hip), (24, hip), (25, knee), (26, knee),
                           (27, ankle), (28, ankle), (11, shoulder), (12, shoulder)]:
            lm[:, idx, :2] = point
    else:
        # Front view: vertical positions match the side model; x spread apart.
        knee_y = ankle[1] - SHIN * np.cos(phi)
        hip_y = knee_y - THIGH * np.cos(theta)
        shoulder_y = hip_y - TORSO
        cx = ankle[0]
        hip_w, ankle_w = 0.08, 0.10
        knee_w = ankle_w * (1 - knee_cave * frac)
        for side, sign in [("l", 1), ("r", -1)]:
            lm[:, 23 if side == "l" else 24, 0] = cx + sign * hip_w
            lm[:, 23 if side == "l" else 24, 1] = hip_y
            lm[:, 25 if side == "l" else 26, 0] = cx + sign * knee_w
            lm[:, 25 if side == "l" else 26, 1] = knee_y
            lm[:, 27 if side == "l" else 28, 0] = cx + sign * ankle_w
            lm[:, 27 if side == "l" else 28, 1] = ankle[1]
            lm[:, 11 if side == "l" else 12, 0] = cx + sign * 0.1
            lm[:, 11 if side == "l" else 12, 1] = shoulder_y

    lm[:, :, 0] /= ASPECT  # back to normalized image x
    times = np.arange(t) / FPS
    return lm, times


def _grade(lm, times, **kw):
    return grade_reps(lm, times, "squat", aspect_ratio=ASPECT, **kw)


def test_supports():
    assert supports("squat")
    assert supports("Squat")
    assert not supports("plank")
    assert grade_reps(np.zeros((10, 33, 4)), np.arange(10.0), "plank") is None


def test_segment_counts_dips_and_ignores_partial_edges():
    times = np.arange(400) / FPS
    # Starts mid-rep (low), then three full dips, then ends mid-dip.
    sig = np.ones(400)
    sig[:20] = 0.3
    for start in (60, 160, 260):
        sig[start:start + 60] = 1 - 0.8 * np.sin(np.linspace(0, np.pi, 60))
    sig[370:] = 0.2
    reps = segment_reps(sig, times, enter_drop=0.25, exit_drop=0.12,
                        min_duration=0.5, max_duration=10)
    assert len(reps) == 3
    for (s, b, e), start in zip(reps, (60, 160, 260)):
        assert start - 1 <= s < b < e <= start + 60
        assert abs(b - (start + 30)) <= 1


def test_segment_ignores_short_noise():
    times = np.arange(200) / FPS
    sig = np.ones(200)
    sig[100:105] = 0.5  # 5 frames — too short to be a rep
    assert segment_reps(sig, times, 0.25, 0.12, 0.5, 10) == []


def test_good_side_squats_pass():
    lm, times = _squat_frames([100, 100, 100], view="side", lean_deg=35)
    result = _grade(lm, times)
    assert result.camera_view == "side"
    assert len(result.reps) == 3
    assert all(r.passed for r in result.reps), [r.checks for r in result.reps]
    assert all(r.score == 100.0 for r in result.reps)


def test_shallow_rep_fails_depth_only_that_rep():
    lm, times = _squat_frames([100, 50, 100], view="side")
    result = _grade(lm, times)
    assert [r.passed for r in result.reps] == [True, False, True]
    shallow = result.reps[1]
    assert shallow.cue.startswith("Squat deeper")
    assert shallow.metrics["hip_height"] == pytest.approx(np.cos(np.radians(50)), abs=0.03)
    assert "rep 2" in result.message


def test_quarter_squat_still_counted():
    # 40° thigh angle: hip drops ~0.23 thigh lengths — counted, then failed.
    lm, times = _squat_frames([45], view="side")
    result = _grade(lm, times)
    assert len(result.reps) == 1
    assert not result.reps[0].passed


def test_excess_lean_fails_side_view():
    lm, times = _squat_frames([100, 100], view="side", lean_deg=70)
    result = _grade(lm, times)
    assert all(not r.passed for r in result.reps)
    lean = next(c for c in result.reps[0].checks if c.name == "torso_lean")
    assert lean.value == pytest.approx(70, abs=2)
    assert result.reps[0].cue.startswith("Keep your chest up")


def test_strictness_changes_verdict():
    # ~10° above parallel: hip height ≈ cos(80°) ≈ 0.17.
    lm, times = _squat_frames([80], view="side")
    assert _grade(lm, times, strictness="lenient").reps[0].passed
    assert not _grade(lm, times, strictness="strict").reps[0].passed


def test_front_view_knee_cave():
    lm, times = _squat_frames([100, 100], view="front", knee_cave=0.0)
    good = _grade(lm, times)
    assert good.camera_view == "front"
    assert all(r.passed for r in good.reps)
    assert not any(c.name == "torso_lean" for c in good.reps[0].checks)

    lm, times = _squat_frames([100, 100], view="front", knee_cave=0.4)
    bad = _grade(lm, times)
    assert len(bad.reps) == 2
    assert all(not r.passed for r in bad.reps)
    assert bad.reps[0].cue.startswith("Push your knees out")


def test_fast_descent_fails_only_with_real_timing():
    lm, times = _squat_frames([100], view="side", rep_seconds=0.6)
    fast = _grade(lm, times, timing_reliable=True)
    assert not fast.reps[0].passed
    assert fast.reps[0].cue.startswith("Control the way down")
    untimed = _grade(lm, times, timing_reliable=False)
    assert untimed.reps[0].passed
    assert not any(c.name == "descent_control" for c in untimed.reps[0].checks)


def test_no_reps_when_standing_still():
    lm, times = _squat_frames([], view="side", rest_seconds=3)
    result = _grade(lm, times)
    assert result.reps == []
    assert "No complete squat reps" in result.message


def test_noise_does_not_create_or_break_reps():
    lm, times = _squat_frames([100, 100, 100, 100], view="side")
    rng = np.random.default_rng(0)
    lm[:, :, :2] += rng.normal(0, 0.004, lm[:, :, :2].shape)
    result = _grade(lm, times)
    assert len(result.reps) == 4
    assert all(r.passed for r in result.reps)


def test_low_visibility_reports_framing_problem():
    lm, times = _squat_frames([100], view="side")
    lm[:, 23:27, 3] = 0.1
    result = _grade(lm, times)
    assert result.reps == []
    assert "in frame" in result.message


def test_analyze_session_uses_rep_grading_with_timestamps():
    lm, _ = _squat_frames([100, 50], view="side")
    frames = [
        {"landmarks": lm[i].tolist(), "t": 1000.0 + i * (1000 / FPS), "aspect": ASPECT}
        for i in range(len(lm))
    ]
    fb = analyze_session(frames, strictness="moderate", exercise_name="squat")
    assert fb.grading_mode == "reps"
    assert fb.rep_count == 2
    assert (fb.passed_reps, fb.failed_reps) == (1, 1)
    assert fb.overall_score == pytest.approx(np.mean([r.score for r in fb.reps]), abs=0.1)
    assert fb.camera_view == "side"
    assert fb.duration_seconds == pytest.approx(len(lm) / FPS, abs=0.1)
    assert any(c.name == "descent_control" for c in fb.reps[0].checks)


def test_analyze_session_other_exercises_keep_session_mode():
    lm, _ = _squat_frames([100], view="side")
    frames = [{"landmarks": lm[i].tolist()} for i in range(len(lm))]
    fb = analyze_session(frames, exercise_name="plank")
    assert fb.grading_mode == "session"
    assert fb.reps == []
