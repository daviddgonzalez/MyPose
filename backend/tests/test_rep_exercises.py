"""
Tests for the non-squat graders: curl, overhead press, push-up, lunge,
deadlift and plank.

Bodies are built from joint angles with a simple 2D stick figure, keyframed
and linearly interpolated, so every rep's true depth / lean / lockout is
known. Side view unless noted; the figure faces +x.
"""

import numpy as np
import pytest

from app.services.reps import grade_reps

ASPECT = 4 / 3
FPS = 30.0
SHIN, THIGH, TORSO, HEAD = 0.20, 0.20, 0.25, 0.08
UPPER, FORE = 0.13, 0.13

STAND = dict(
    thigh=0.0, shin=0.0, lean=0.0,      # leg/torso angles from vertical (deg)
    back_thigh=0.0, back_shin=0.0,      # second leg (lunge back leg)
    arm=5.0, elbow=170.0,               # upper arm from hanging down; elbow angle
)


def _sequence(keyframes: list[tuple[float, dict]], start: dict = STAND) -> list[dict]:
    """Linearly interpolate pose params through (seconds, params) keyframes."""
    frames = [dict(start)]
    current = dict(start)
    for seconds, params in keyframes:
        target = {**current, **params}
        n = max(1, int(round(seconds * FPS)))
        for i in range(1, n + 1):
            f = i / n
            frames.append({k: current[k] + (target[k] - current[k]) * f for k in current})
        current = target
    return frames


def _dir(deg: float) -> np.ndarray:
    """Unit vector at `deg` from straight down, rotating toward +x (forward)."""
    r = np.radians(deg)
    return np.array([np.sin(r), np.cos(r)])


def _standing_body(frames: list[dict], view: str = "side") -> tuple[np.ndarray, np.ndarray]:
    """(T, 33, 4) landmarks for an upright-ish figure (curl/press/lunge/deadlift)."""
    lm = np.zeros((len(frames), 33, 4))
    lm[:, :, 3] = 1.0
    for t, p in enumerate(frames):
        ankle = np.array([0.5 * ASPECT, 0.95])
        knee = ankle - SHIN * _dir(-p["shin"])           # shin leans forward
        hip = knee - THIGH * _dir(p["thigh"])            # hips go back
        shoulder = hip - TORSO * _dir(-p["lean"])        # positive lean = forward
        nose = shoulder - HEAD * _dir(-p["lean"]) + np.array([0.03, 0.0])
        ear = nose - np.array([0.04, 0.0])
        elbow = shoulder + UPPER * _dir(p["arm"])
        wrist = elbow + FORE * _dir(p["arm"] + 180 - p["elbow"])
        back_knee = hip + THIGH * _dir(-p["back_thigh"])
        back_ankle = back_knee + SHIN * _dir(-p["back_shin"])

        pts = {0: nose, 7: ear, 8: ear,
               11: shoulder, 12: shoulder, 13: elbow, 14: elbow, 15: wrist, 16: wrist,
               23: hip, 24: hip, 25: knee, 26: back_knee, 27: ankle, 28: back_ankle}
        if view == "front":
            # Collapse depth, spread sides apart; arms move in the frontal plane.
            cx = 0.5 * ASPECT
            for idx, (pt, w) in {11: (shoulder, 0.09), 12: (shoulder, -0.09),
                                 23: (hip, 0.05), 24: (hip, -0.05),
                                 25: (knee, 0.05), 26: (knee, -0.05),
                                 27: (ankle, 0.05), 28: (ankle, -0.05)}.items():
                pts[idx] = np.array([cx + w, pt[1]])
            for sh, el, wr, sign in ((11, 13, 15, 1), (12, 14, 16, -1)):
                side_elbow = pts[sh] + UPPER * _dir(p["arm"]) * [sign, 1]
                side_wrist = side_elbow + FORE * _dir(p["arm"] + 180 - p["elbow"]) * [sign, 1]
                pts[el], pts[wr] = side_elbow, side_wrist
            pts[0] = np.array([cx, pts[11][1] - HEAD])
            pts[7], pts[8] = pts[0] + [0.03, 0], pts[0] - [0.03, 0]
        for idx, pt in pts.items():
            lm[t, idx, :2] = pt
    lm[:, :, 0] /= ASPECT
    return lm, np.arange(len(frames)) / FPS


def _grade(exercise, frames, view="side", **kw):
    lm, times = _standing_body(frames, view) if not isinstance(frames, tuple) else frames
    return grade_reps(lm, times, exercise, aspect_ratio=ASPECT, **kw)


def _reps(n: int, down: dict, down_s=1.0, up_s=1.0, rest_s=0.8, up: dict | None = None):
    keys = [(rest_s, {})]
    for _ in range(n):
        keys += [(down_s, down), (up_s, up or STAND), (rest_s, {})]
    return _sequence(keys)


def _failed(result, name):
    return [r.index for r in result.reps if any(c.name == name and not c.passed for c in r.checks)]


# ─── Curl ──────────────────────────────────────────────────────────

def test_curl_good_reps_pass():
    result = _grade("barbell_biceps_curl", _reps(3, dict(elbow=45, arm=15)))
    assert len(result.reps) == 3
    assert all(r.passed for r in result.reps), [r.checks for r in result.reps]


def test_curl_faults():
    half = _grade("barbell_biceps_curl", _reps(2, dict(elbow=95, arm=10)))
    assert len(half.reps) == 2 and _failed(half, "full_curl") == [1, 2]

    swing = _grade("barbell_biceps_curl", _reps(2, dict(elbow=45, arm=50)))
    assert _failed(swing, "elbows_pinned") == [1, 2]
    assert swing.reps[0].cue == "Keep your elbows pinned to your sides."

    body = _grade("barbell_biceps_curl", _reps(2, dict(elbow=45, arm=15, lean=-20)))
    assert _failed(body, "no_swing") == [1, 2]


def test_curl_ignores_walking_around():
    # Arms swing a little and the torso turns, but the elbows never bend.
    frames = _sequence([(1, dict(arm=20, elbow=160)), (1, dict(arm=-10)), (1, {})] * 3)
    assert _grade("barbell_biceps_curl", frames).reps == []


# ─── Overhead press ────────────────────────────────────────────────

RACKED = dict(arm=40, elbow=50)
OVERHEAD = dict(arm=180, elbow=178)


def _press(n, top=OVERHEAD, view="side"):
    keys = [(1.0, {}), (1.0, RACKED), (0.5, {})]  # arms down → rack
    for _ in range(n):
        keys += [(0.8, top), (1.0, RACKED), (0.5, {})]
    keys += [(1.0, STAND)]
    return _grade("overhead_press", _sequence(keys), view)


def test_press_good_reps_pass():
    result = _press(3)
    assert len(result.reps) == 3
    assert all(r.passed for r in result.reps), [r.checks for r in result.reps]


def test_press_faults():
    soft = _press(2, top=dict(arm=160, elbow=140))
    assert _failed(soft, "lockout") == [1, 2]

    arch = _press(2, top={**OVERHEAD, "lean": -22})
    assert _failed(arch, "no_lean_back") == [1, 2]


def test_press_front_view_checks_even_arms():
    result = _press(2, view="front")
    assert result.camera_view == "front"
    assert len(result.reps) == 2
    assert all(any(c.name == "even_arms" and c.passed for c in r.checks) for r in result.reps)


# ─── Lunge ─────────────────────────────────────────────────────────

LUNGE_BOTTOM = dict(thigh=85, shin=15, back_thigh=15, back_shin=80, lean=10)


def test_lunge_good_reps_pass_and_report_front_leg():
    result = _grade("lunge", _reps(3, LUNGE_BOTTOM))
    assert len(result.reps) == 3
    assert all(r.passed for r in result.reps), [r.checks for r in result.reps]
    assert {r.side for r in result.reps} == {"left"}


def test_lunge_faults():
    shallow = _grade("lunge", _reps(2, {**LUNGE_BOTTOM, "thigh": 50}))
    assert _failed(shallow, "depth") == [1, 2]

    knee_forward = _grade("lunge", _reps(2, {**LUNGE_BOTTOM, "shin": 50, "thigh": 80}))
    assert _failed(knee_forward, "front_shin") == [1, 2]

    leaning = _grade("lunge", _reps(2, {**LUNGE_BOTTOM, "lean": 45}))
    assert _failed(leaning, "torso_upright") == [1, 2]


# ─── Deadlift ──────────────────────────────────────────────────────

DL_BOTTOM = dict(thigh=70, shin=25, lean=60, arm=-60, elbow=178)


def test_deadlift_good_reps_pass():
    result = _grade("deadlift", _reps(3, DL_BOTTOM, down_s=1.2, up_s=1.2))
    assert len(result.reps) == 3
    assert all(r.passed for r in result.reps), [r.checks for r in result.reps]


def test_deadlift_hips_shooting_up():
    keys = [(0.8, {})]
    for _ in range(2):
        keys += [(1.2, DL_BOTTOM),
                 (0.6, dict(thigh=20, shin=5, lean=75)),  # legs straighten first
                 (0.8, STAND), (0.8, {})]
    result = _grade("deadlift", _sequence(keys))
    assert len(result.reps) == 2
    assert _failed(result, "hips_first") == [1, 2]


def test_deadlift_lean_back_at_lockout():
    result = _grade("deadlift", _reps(2, DL_BOTTOM, up={**STAND, "lean": -20}))
    assert _failed(result, "no_lean_back") == [1, 2]


def test_deadlift_romanian_style_skips_hips_first():
    rdl = dict(thigh=55, shin=5, lean=75, arm=-70, elbow=178)
    result = _grade("deadlift", _reps(2, rdl))
    assert len(result.reps) == 2
    assert not any(c.name == "hips_first" for r in result.reps for c in r.checks)


# ─── Push-up and plank (horizontal body) ───────────────────────────

def _horizontal_body(shoulder_heights, hip_offsets) -> tuple[np.ndarray, np.ndarray]:
    """
    Side-view push-up/plank. Hands fixed under the shoulders; elbows solved
    by two-link IK. hip_offset > 0 drops the hips below the straight line
    (sag), < 0 raises them (pike).
    """
    t = len(shoulder_heights)
    lm = np.zeros((t, 33, 4))
    lm[:, :, 3] = 1.0
    floor = 0.85
    for i, (h, sag) in enumerate(zip(shoulder_heights, hip_offsets)):
        wrist = np.array([0.75 * ASPECT, floor])
        shoulder = np.array([wrist[0], floor - h])
        d = min(h, UPPER + FORE - 1e-6)
        # Angle at the wrist between "up" and the forearm, elbow toward the feet.
        a = np.arccos(np.clip((FORE**2 + d**2 - UPPER**2) / (2 * FORE * d), -1, 1))
        elbow = wrist + FORE * np.array([-np.sin(a), -np.cos(a)])
        ankle = np.array([0.15 * ASPECT, floor - 0.02])
        hip = shoulder + 0.55 * (ankle - shoulder) + np.array([0.0, sag])
        knee = hip + 0.5 * (ankle - hip)
        nose = shoulder + np.array([0.06, 0.0])
        ear = shoulder + np.array([0.03, -0.01])
        for idx, pt in {0: nose, 7: ear, 8: ear, 11: shoulder, 12: shoulder,
                        13: elbow, 14: elbow, 15: wrist, 16: wrist, 23: hip, 24: hip,
                        25: knee, 26: knee, 27: ankle, 28: ankle}.items():
            lm[i, idx, :2] = pt
    lm[:, :, 0] /= ASPECT
    return lm, np.arange(t) / FPS


def _pushups(n, bottom_elbow=75.0, sag=0.0):
    top = UPPER + FORE - 0.005
    bottom = np.sqrt(UPPER**2 + FORE**2 - 2 * UPPER * FORE * np.cos(np.radians(bottom_elbow)))
    heights = [top] * int(FPS)
    for _ in range(n):
        heights += list(np.linspace(top, bottom, int(FPS)))
        heights += list(np.linspace(bottom, top, int(FPS)))
        heights += [top] * int(0.5 * FPS)
    return _horizontal_body(heights, [sag] * len(heights))


def test_pushup_good_reps_pass():
    result = _grade("push_up", _pushups(3))
    assert result.camera_view == "side"
    assert len(result.reps) == 3
    assert all(r.passed for r in result.reps), [r.checks for r in result.reps]


def test_pushup_faults():
    shallow = _grade("push_up", _pushups(2, bottom_elbow=120))
    assert _failed(shallow, "depth") == [1, 2]

    sag = _grade("push_up", _pushups(2, sag=0.08))
    assert _failed(sag, "body_line") == [1, 2]
    assert "sagging" in sag.reps[0].cue

    pike = _grade("push_up", _pushups(2, sag=-0.08))
    assert _failed(pike, "body_line") == [1, 2]
    assert "Lower your hips" in pike.reps[0].cue


def test_pushup_ignores_standing_arm_bends():
    # Curling while standing bends the elbows the same way, but isn't a push-up.
    assert _grade("push_up", _reps(3, dict(elbow=45, arm=15))).reps == []


def test_plank_hold():
    top = UPPER + FORE - 0.005
    n = int(12 * FPS)
    good = _grade("plank", _horizontal_body([top] * n, [0.0] * n))
    assert good.mode == "hold"
    assert len(good.reps) == 1 and good.reps[0].passed
    assert good.reps[0].metrics["hold_s"] == pytest.approx(12, abs=0.1)
    assert good.message.startswith("Held a plank for 12s")

    sag = _grade("plank", _horizontal_body([top] * n, [0.08] * n))
    assert not sag.reps[0].passed
    assert "sagging" in sag.reps[0].cue


def test_plank_not_detected_while_standing():
    result = _grade("plank", _sequence([(5, {})]))
    assert result.mode == "hold"
    assert result.reps == []


@pytest.mark.parametrize("exercise, frames, count", [
    ("barbell_biceps_curl", lambda: _standing_body(_reps(4, dict(elbow=45, arm=15))), 4),
    ("lunge", lambda: _standing_body(_reps(4, LUNGE_BOTTOM)), 4),
    ("deadlift", lambda: _standing_body(_reps(4, DL_BOTTOM, down_s=1.2, up_s=1.2)), 4),
    ("push_up", lambda: _pushups(4), 4),
])
def test_landmark_jitter_keeps_rep_count(exercise, frames, count):
    lm, times = frames()
    rng = np.random.default_rng(1)
    lm[:, :, :2] += rng.normal(0, 0.004, lm[:, :, :2].shape)
    result = grade_reps(lm, times, exercise, aspect_ratio=ASPECT)
    assert len(result.reps) == count
