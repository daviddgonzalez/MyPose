"""
Per-Rep Segmentation and Rule-Based Grading.

Splits a session into individual reps and grades each one against
exercise-specific form rules. No ML model is involved: every verdict is
traceable to a measured quantity (depth, torso lean, knee tracking, tempo),
so the feedback can say *why* a rep failed.

Pipeline:
    landmarks (T, 33, 4) → per-frame signals → smoothing →
    hysteresis rep segmentation → per-rep metrics at the bottom → checks

Coordinates are MediaPipe image landmarks (x, y in [0, 1], y pointing down).
x is multiplied by the frame aspect ratio so 2D angles are not distorted.
z is ignored — MediaPipe's image-space depth is too noisy for grading.

Adding an exercise means adding a grader with:
    - a 1D signal that sits near its maximum at the rep's rest position
      and dips during the rep,
    - segmentation thresholds in that signal's units,
    - a gate that rejects dips which aren't the exercise (walking in,
      stepping into place) — real footage is full of them,
    - checks evaluated on each rep.

Plank is graded as a single hold instead of reps (RepAnalysis.mode "hold").
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)

# MediaPipe Pose landmark indices
NOSE = 0
L_EAR, R_EAR = 7, 8
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW, R_ELBOW = 13, 14
L_WRIST, R_WRIST = 15, 16
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28

VISIBILITY_MIN = 0.5
SMOOTHING_SECONDS = 0.15


# ─── Result Contract ───────────────────────────────────────────────


@dataclass
class RepCheck:
    """One form rule evaluated on one rep."""
    name: str            # machine id, e.g. "depth"
    label: str           # display name, e.g. "Depth"
    passed: bool
    value: float         # measured value
    target: float        # threshold the value is compared against
    unit: str            # "deg", "s", "ratio", "thigh"
    score: float         # 0–1, 1 when passed, decays with how far it missed
    cue: str = ""        # coaching cue, set only when failed


@dataclass
class RepResult:
    """Grade for a single rep."""
    index: int           # 1-based
    start_time: float    # seconds from session start
    bottom_time: float
    end_time: float
    score: float         # 0–100
    passed: bool
    checks: list[RepCheck] = field(default_factory=list)
    cue: str | None = None  # the most important cue for this rep
    metrics: dict[str, float] = field(default_factory=dict)
    side: str | None = None  # "left" / "right" for one-sided reps (lunge)


@dataclass
class RepAnalysis:
    """Output of grade_reps()."""
    reps: list[RepResult]
    camera_view: str     # "side" | "front"
    message: str
    notes: list[str] = field(default_factory=list)
    mode: str = "reps"   # "reps", or "hold" for isometrics (one result per hold)


# ─── Signal helpers ────────────────────────────────────────────────


def _fill_nans(x: np.ndarray) -> np.ndarray:
    """Linearly interpolate NaNs; edges take the nearest valid value."""
    x = x.astype(np.float64).copy()
    nans = np.isnan(x)
    if nans.all() or not nans.any():
        return x
    idx = np.arange(len(x))
    x[nans] = np.interp(idx[nans], idx[~nans], x[~nans])
    return x


def _smooth(x: np.ndarray, window: int) -> np.ndarray:
    """Centered moving average with edge padding (NaNs filled first)."""
    x = _fill_nans(x)
    if window <= 1 or len(x) < 3:
        return x
    window = min(window, len(x))
    pad = window // 2
    padded = np.pad(x, (pad, window - 1 - pad), mode="edge")
    return np.convolve(padded, np.ones(window) / window, mode="valid")


def _angle_deg(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Angle at b (degrees) for 2D point series a-b-c of shape (T, 2)."""
    v1 = a - b
    v2 = c - b
    cos = np.sum(v1 * v2, axis=1) / (
        np.linalg.norm(v1, axis=1) * np.linalg.norm(v2, axis=1) + 1e-8
    )
    return np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))


def _side_mean(left: np.ndarray, right: np.ndarray,
               left_ok: np.ndarray, right_ok: np.ndarray) -> np.ndarray:
    """Per-frame mean of the visible sides; both sides if neither is visible."""
    lw = left_ok.astype(np.float64)
    rw = right_ok.astype(np.float64)
    neither = (lw + rw) == 0
    lw[neither] = 1.0
    rw[neither] = 1.0
    return (left * lw + right * rw) / (lw + rw)


def _rolling_reference(
    values: np.ndarray,
    ok: np.ndarray,
    times: np.ndarray,
    half_window: float,
    q: float = 90,
) -> np.ndarray:
    """
    Per-frame q-th percentile of `values` over frames within ±half_window
    seconds where `ok` is set. NaN where no frame in the window qualifies.

    A rolling reference adapts when the user moves closer to or further from
    the camera (walking in to start or stop the recording), which a single
    session-wide reference doesn't.
    """
    out = np.full(len(values), np.nan)
    lo = hi = 0
    for i, t in enumerate(times):
        while times[lo] < t - half_window:
            lo += 1
        while hi < len(times) and times[hi] <= t + half_window:
            hi += 1
        window = values[lo:hi][ok[lo:hi]]
        if len(window):
            out[i] = np.percentile(window, q)
    return out


def segment_reps(
    signal: np.ndarray,
    times: np.ndarray,
    enter_drop: float,
    exit_drop: float,
    min_duration: float,
    max_duration: float,
    top: float | None = None,
) -> list[tuple[int, int, int]]:
    """
    Find reps in a smoothed signal that rests high and dips during each rep.

    Hysteresis against the rest level `top` (default: the session's 95th
    percentile): a rep starts when the signal drops more than `enter_drop`
    below rest and ends when it climbs back within `exit_drop` of rest. Reps
    cut off by the start or end of the recording are dropped.

    Returns:
        List of (start_idx, bottom_idx, end_idx).
    """
    if len(signal) < 3:
        return []

    if top is None:
        top = float(np.percentile(signal, 95))
    enter_level = top - enter_drop
    exit_level = top - exit_drop

    reps: list[tuple[int, int, int]] = []
    # "waiting" until the user is first seen at rest, so a session that
    # starts mid-rep doesn't produce a half rep.
    state = "top" if signal[0] >= exit_level else "waiting"
    last_top_idx = 0
    start = bottom = 0

    for i, s in enumerate(signal):
        if state == "waiting":
            if s >= exit_level:
                state = "top"
                last_top_idx = i
        elif state == "top":
            if s >= exit_level:
                last_top_idx = i
            elif s < enter_level:
                state = "down"
                start = last_top_idx
                bottom = i
        else:  # down
            if s < signal[bottom]:
                bottom = i
            if s >= exit_level:
                duration = times[i] - times[start]
                if min_duration <= duration <= max_duration:
                    reps.append((start, bottom, i))
                state = "top"
                last_top_idx = i

    return reps


def _graded(passed: bool, miss: float, tolerance: float) -> float:
    """1.0 when passed, otherwise decays linearly to 0 over `tolerance`."""
    if passed:
        return 1.0
    return float(np.clip(1.0 - miss / tolerance, 0.0, 1.0))


def _check(
    name: str,
    label: str,
    value: float,
    limit: float,
    *,
    at_most: bool,
    tolerance: float,
    unit: str,
    cue: str,
    weight: float = 1.0,
) -> tuple[RepCheck, float]:
    """A pass/fail rule: value ≤ limit (at_most) or value ≥ limit."""
    ok = value <= limit if at_most else value >= limit
    miss = value - limit if at_most else limit - value
    check = RepCheck(
        name=name, label=label, passed=ok,
        value=round(float(value), 2), target=limit, unit=unit,
        score=_graded(ok, miss, tolerance),
        cue="" if ok else cue,
    )
    return check, weight


def _make_rep(
    n: int,
    segment: tuple[int, int, int],
    times: np.ndarray,
    checks: list[tuple[RepCheck, float]],
    metrics: dict[str, float],
    side: str | None = None,
) -> RepResult:
    """Score a rep from its weighted checks."""
    start, bottom, end = segment
    total_weight = sum(w for _, w in checks)
    score = 100.0 * sum(c.score * w for c, w in checks) / total_weight if checks else 100.0
    failed = [c for c, _ in checks if not c.passed]
    # Most important cue: the failed check with the lowest score.
    cue = min(failed, key=lambda c: c.score).cue if failed else None
    return RepResult(
        index=n,
        start_time=round(float(times[start] - times[0]), 2),
        bottom_time=round(float(times[bottom] - times[0]), 2),
        end_time=round(float(times[end] - times[0]), 2),
        score=round(score, 1),
        passed=not failed,
        checks=[c for c, _ in checks],
        cue=cue,
        metrics={k: round(float(v), 2) for k, v in metrics.items()},
        side=side,
    )


def _limits(table: dict[str, dict], strictness: str) -> dict:
    return table.get(strictness, table["moderate"])


# Shoulder width / torso length above this means the camera faces the user.
_FRONT_VIEW_SHOULDER_RATIO = 0.35
# Rolling window for body-size references (see _rolling_reference).
_REF_HALF_WINDOW_S = 2.5


class _Pose:
    """Aspect-corrected 2D landmarks plus the per-frame signals graders share."""

    def __init__(self, landmarks: np.ndarray, times: np.ndarray, aspect_ratio: float):
        self.times = times
        self.xy = landmarks[:, :, :2].astype(np.float64).copy()
        self.xy[:, :, 0] *= aspect_ratio
        self.vis = landmarks[:, :, 3]
        dt = float(np.median(np.diff(times))) if len(times) > 1 else 1 / 30
        self.window = max(1, int(round(SMOOTHING_SECONDS / max(dt, 1e-3))))

    def pt(self, i: int) -> np.ndarray:
        return self.xy[:, i, :]

    def seen(self, *idx: int) -> np.ndarray:
        """Frames where every listed landmark is visible."""
        return np.all(self.vis[:, list(idx)] >= VISIBILITY_MIN, axis=1)

    def smooth(self, x: np.ndarray) -> np.ndarray:
        return _smooth(x, self.window)

    def mid(self, a: int, b: int) -> np.ndarray:
        return (self.pt(a) + self.pt(b)) / 2

    def sided_angle(
        self, left: tuple[int, int, int], right: tuple[int, int, int]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Joint angle (degrees) per side. Returns (left, right, left_seen,
        right_seen), angles unsmoothed.
        """
        la = _angle_deg(*(self.pt(i) for i in left))
        ra = _angle_deg(*(self.pt(i) for i in right))
        return la, ra, self.seen(*left), self.seen(*right)

    def mean_angle(
        self, left: tuple[int, int, int], right: tuple[int, int, int]
    ) -> tuple[np.ndarray, np.ndarray]:
        """Smoothed mean angle over visible sides, and frames with any side seen."""
        la, ra, lok, rok = self.sided_angle(left, right)
        return self.smooth(_side_mean(la, ra, lok, rok)), lok | rok

    def torso_lean(self) -> np.ndarray:
        """Smoothed torso angle from vertical (degrees, unsigned)."""
        torso = self.mid(L_SHOULDER, R_SHOULDER) - self.mid(L_HIP, R_HIP)
        return self.smooth(np.degrees(np.arctan2(np.abs(torso[:, 0]), -torso[:, 1])))

    def facing(self) -> float:
        """+1 if the user faces +x in the image, -1 if -x (from nose vs ears)."""
        offset = self.pt(NOSE)[:, 0] - self.mid(L_EAR, R_EAR)[:, 0]
        return 1.0 if float(np.median(offset)) >= 0 else -1.0

    def upper_body_view(self) -> str:
        """'front' or 'side', from shoulder width relative to torso length."""
        shoulder_w = np.abs(self.pt(L_SHOULDER)[:, 0] - self.pt(R_SHOULDER)[:, 0])
        torso = np.linalg.norm(
            self.mid(L_SHOULDER, R_SHOULDER) - self.mid(L_HIP, R_HIP), axis=1
        )
        ratio = float(np.median(shoulder_w / np.maximum(torso, 1e-6)))
        return "front" if ratio >= _FRONT_VIEW_SHOULDER_RATIO else "side"

    def rolling_length(self, a: int, b: int, ok: np.ndarray) -> np.ndarray:
        """Per-frame standing-length reference of segment a→b (NaN if never seen)."""
        lengths = np.linalg.norm(self.pt(a) - self.pt(b), axis=1)
        return _rolling_reference(lengths, ok, self.times, _REF_HALF_WINDOW_S)

    def hip_heights(self) -> dict | None:
        """
        Hip height above the knee per side, in standing thigh lengths:
        ~1 standing, 0 with the thigh horizontal. Uses only the vertical
        axis, so it reads the same from front or side. None if the legs
        were never seen.
        """
        left_ok = self.seen(L_HIP, L_KNEE)
        right_ok = self.seen(R_HIP, R_KNEE)
        ref_l = self.rolling_length(L_HIP, L_KNEE, left_ok)
        ref_r = self.rolling_length(R_HIP, R_KNEE, right_ok)
        both = np.stack([ref_l, ref_r])
        has_ref = ~np.isnan(both).all(axis=0)
        if not has_ref.any() or np.nanmax(both) < 1e-4:
            return None
        thigh = np.full(len(self.times), np.nan)
        thigh[has_ref] = np.nanmean(both[:, has_ref], axis=0)
        thigh = np.maximum(_fill_nans(thigh), 1e-4)
        ref_l = np.where(np.isnan(ref_l), thigh, ref_l)
        ref_r = np.where(np.isnan(ref_r), thigh, ref_r)
        return {
            "left": (self.pt(L_KNEE)[:, 1] - self.pt(L_HIP)[:, 1]) / ref_l,
            "right": (self.pt(R_KNEE)[:, 1] - self.pt(R_HIP)[:, 1]) / ref_r,
            "left_ok": left_ok,
            "right_ok": right_ok,
            "thigh": thigh,
        }

    def body_line(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Shoulder→hip→ankle straightness for push-ups and planks.

        Returns (angle at the hip in degrees, smoothed; hip offset from the
        shoulder–ankle line, positive = hips below it (sagging); frames with
        a full side seen).
        """
        la, ra, lok, rok = self.sided_angle(
            (L_SHOULDER, L_HIP, L_ANKLE), (R_SHOULDER, R_HIP, R_ANKLE)
        )
        angle = self.smooth(_side_mean(la, ra, lok, rok))
        shoulder = self.mid(L_SHOULDER, R_SHOULDER)
        hip = self.mid(L_HIP, R_HIP)
        ankle = self.mid(L_ANKLE, R_ANKLE)
        dx = ankle[:, 0] - shoulder[:, 0]
        frac = np.clip((hip[:, 0] - shoulder[:, 0]) / np.where(np.abs(dx) < 1e-6, 1e-6, dx), 0, 1)
        line_y = shoulder[:, 1] + frac * (ankle[:, 1] - shoulder[:, 1])
        return angle, self.smooth(hip[:, 1] - line_y), lok | rok


def _rest_window(
    segments: list[tuple[int, int, int]], k: int, times: np.ndarray, after: bool,
    span_s: float = 2.0,
) -> slice:
    """Frames of rest just before (or after) rep k, up to the neighbouring rep."""
    start, _, end = segments[k]
    if after:
        stop = segments[k + 1][0] if k + 1 < len(segments) else len(times) - 1
        stop = min(stop, int(np.searchsorted(times, times[end] + span_s)))
        return slice(end, max(stop, end) + 1)
    first = segments[k - 1][2] if k > 0 else 0
    first = max(first, int(np.searchsorted(times, times[start] - span_s)))
    return slice(min(first, start), start + 1)


def _finish(
    reps: list[RepResult], view: str, noun: str, notes: list[str], empty_hint: str,
) -> RepAnalysis:
    return RepAnalysis(
        reps=reps, camera_view=view,
        message=_summary(reps, noun, empty_hint), notes=notes,
    )


_NOT_IN_FRAME = RepAnalysis(
    reps=[], camera_view="unknown",
    message="Couldn't see you clearly. Step back so your whole body is in frame.",
)


def _timing_note(timing_reliable: bool, notes: list[str], what: str) -> None:
    if not timing_reliable:
        notes.append(f"Frame timing unavailable: {what} isn't checked.")


# ─── Squat ─────────────────────────────────────────────────────────

# Per strictness level:
#   depth_max     hip height above knee at the bottom, in thigh lengths
#                 (0 = parallel, negative = below parallel)
#   lean_max      torso angle from vertical at the bottom (side view)
#   knee_min      knee width / ankle width at the bottom (front view)
#   hip_tilt_max  left/right hip height difference, in thigh lengths
#   descent_min   seconds from the top to the bottom
_SQUAT_LIMITS = {
    "lenient": dict(
        depth_max=0.35, lean_max=65.0, knee_min=0.75, hip_tilt_max=0.20, descent_min=0.25,
    ),
    "moderate": dict(
        depth_max=0.25, lean_max=55.0, knee_min=0.85, hip_tilt_max=0.12, descent_min=0.40,
    ),
    "strict": dict(
        depth_max=0.00, lean_max=50.0, knee_min=0.90, hip_tilt_max=0.08, descent_min=0.60,
    ),
    "drill_sergeant": dict(
        depth_max=-0.10, lean_max=45.0, knee_min=0.95, hip_tilt_max=0.05, descent_min=0.80,
    ),
}

# Rep segmentation in thigh lengths of hip height above the knee, which is
# ~1.0 when standing because the thigh reference is the standing thigh.
_SQUAT_ENTER_DROP = 0.25
_SQUAT_EXIT_DROP = 0.12
_SQUAT_MIN_REP_S = 0.3
_SQUAT_MAX_REP_S = 10.0
# A dip whose bottom keeps the knee straighter than this is the user walking
# or turning while setting up, not a squat.
_SQUAT_MAX_BOTTOM_KNEE_DEG = 150.0

# Hip width / thigh length above this means the camera faces the user.
_FRONT_VIEW_HIP_RATIO = 0.3


def _grade_squat(
    landmarks: np.ndarray,
    times: np.ndarray,
    strictness: str,
    aspect_ratio: float,
    timing_reliable: bool,
) -> RepAnalysis:
    limits = _limits(_SQUAT_LIMITS, strictness)
    pose = _Pose(landmarks, times, aspect_ratio)
    pt = pose.pt

    left_ok = pose.seen(L_HIP, L_KNEE)
    right_ok = pose.seen(R_HIP, R_KNEE)
    if (left_ok | right_ok).mean() < 0.5:
        return RepAnalysis(
            reps=[], camera_view="unknown",
            message=("Couldn't see your hips and knees clearly. "
                     "Step back so your whole body is in frame."),
        )

    heights = pose.hip_heights()
    if heights is None:
        return RepAnalysis(
            reps=[], camera_view="unknown",
            message="Couldn't measure your legs. Make sure your hips and knees are in frame.",
        )
    thigh = heights["thigh"]
    hip_height_s = pose.smooth(
        _side_mean(heights["left"], heights["right"], left_ok, right_ok)
    )

    # Camera view from how far apart the hips appear relative to the thigh.
    hip_width = np.abs(pt(L_HIP)[:, 0] - pt(R_HIP)[:, 0])
    view = "front" if float(np.median(hip_width / thigh)) >= _FRONT_VIEW_HIP_RATIO else "side"

    # Per-frame metrics, smoothed, read at each rep's bottom.
    lean = pose.torso_lean()
    knee_angle = pose.smooth(_side_mean(
        _angle_deg(pt(L_HIP), pt(L_KNEE), pt(L_ANKLE)),
        _angle_deg(pt(R_HIP), pt(R_KNEE), pt(R_ANKLE)),
        left_ok, right_ok,
    ))
    knee_width = np.abs(pt(L_KNEE)[:, 0] - pt(R_KNEE)[:, 0])
    ankle_width = np.abs(pt(L_ANKLE)[:, 0] - pt(R_ANKLE)[:, 0])
    knee_ratio = pose.smooth(knee_width / np.maximum(ankle_width, 1e-6))
    ankle_width_s = pose.smooth(ankle_width)
    hip_tilt = pose.smooth(np.abs(pt(L_HIP)[:, 1] - pt(R_HIP)[:, 1]) / thigh)

    segments = segment_reps(
        hip_height_s, times,
        enter_drop=_SQUAT_ENTER_DROP, exit_drop=_SQUAT_EXIT_DROP,
        min_duration=_SQUAT_MIN_REP_S, max_duration=_SQUAT_MAX_REP_S,
        top=1.0,
    )

    # Hip height at an unseen knee is a guess, so such a dip can't count.
    legs_seen = left_ok | right_ok
    segments = [
        seg for seg in segments
        if legs_seen[seg[1]] and knee_angle[seg[1]] <= _SQUAT_MAX_BOTTOM_KNEE_DEG
    ]

    reps: list[RepResult] = []
    for n, (start, bottom, end) in enumerate(segments, start=1):
        depth = float(hip_height_s[bottom])
        checks = [_check(
            "depth", "Depth", depth, limits["depth_max"], at_most=True, tolerance=0.4,
            unit="thigh", cue="Squat deeper — get your hips down to knee level.", weight=2.0,
        )]

        if view == "side":
            lean_b = float(lean[bottom])
            checks.append(_check(
                "torso_lean", "Chest up", lean_b, limits["lean_max"], at_most=True,
                tolerance=20.0, unit="deg",
                cue=f"Keep your chest up — torso leaned {lean_b:.0f}° at the bottom.",
            ))
        else:
            # Knee tracking only means something when the feet are apart.
            if ankle_width_s[bottom] >= 0.15 * thigh[bottom]:
                checks.append(_check(
                    "knee_tracking", "Knees out", float(knee_ratio[bottom]), limits["knee_min"],
                    at_most=False, tolerance=0.3, unit="ratio",
                    cue="Push your knees out over your toes — they're caving in.",
                ))
            checks.append(_check(
                "hip_level", "Level hips", float(hip_tilt[bottom]), limits["hip_tilt_max"],
                at_most=True, tolerance=0.15, unit="thigh",
                cue="Keep your hips level — you're shifting to one side.",
            ))

        descent = float(times[bottom] - times[start])
        if timing_reliable:
            checks.append(_check(
                "descent_control", "Controlled descent", descent, limits["descent_min"],
                at_most=False, tolerance=0.4, unit="s",
                cue=f"Control the way down — you dropped in {descent:.1f}s.",
            ))

        reps.append(_make_rep(n, (start, bottom, end), times, checks, {
            "hip_height": depth,
            "knee_angle_deg": knee_angle[bottom],
            "torso_lean_deg": lean[bottom],
            "descent_s": descent,
            "rep_duration_s": times[end] - times[start],
        }))

    notes = []
    if view == "front":
        notes.append("Filmed from the front: torso lean isn't checked. "
                     "Film from the side to grade it.")
    else:
        notes.append("Filmed from the side: knee tracking isn't checked. "
                     "Film from the front to grade it.")
    _timing_note(timing_reliable, notes, "descent speed")

    return _finish(reps, view, "squat", notes,
                   "Make sure your whole body is in frame and stand all the way up between reps.")


# ─── Biceps curl ───────────────────────────────────────────────────
#   flex_max       elbow angle at the top of the curl
#   extend_min     elbow angle before the rep (arms straight between reps)
#   upper_arm_max  upper arm angle from hanging straight down during the rep
#   swing_max      torso lean range during the rep (body english)
#   lower_min      seconds lowering the weight
_CURL_LIMITS = {
    "lenient": dict(flex_max=80, extend_min=130, upper_arm_max=40, swing_max=20, lower_min=0.3),
    "moderate": dict(flex_max=65, extend_min=145, upper_arm_max=30, swing_max=12, lower_min=0.5),
    "strict": dict(flex_max=55, extend_min=155, upper_arm_max=20, swing_max=8, lower_min=0.8),
    "drill_sergeant": dict(
        flex_max=50, extend_min=160, upper_arm_max=15, swing_max=5, lower_min=1.0,
    ),
}
_CURL_MAX_BOTTOM_ELBOW_DEG = 110.0

_ARMS = ((L_SHOULDER, L_ELBOW, L_WRIST), (R_SHOULDER, R_ELBOW, R_WRIST))


def _upper_arm_from_vertical(pose: _Pose) -> np.ndarray:
    """Smoothed upper-arm angle from hanging straight down, mean over seen sides."""
    def side(sh: int, el: int) -> np.ndarray:
        v = pose.pt(el) - pose.pt(sh)
        return np.degrees(np.arctan2(np.abs(v[:, 0]), v[:, 1]))
    return pose.smooth(_side_mean(
        side(L_SHOULDER, L_ELBOW), side(R_SHOULDER, R_ELBOW),
        pose.seen(L_SHOULDER, L_ELBOW), pose.seen(R_SHOULDER, R_ELBOW),
    ))


def _grade_curl(landmarks, times, strictness, aspect_ratio, timing_reliable) -> RepAnalysis:
    limits = _limits(_CURL_LIMITS, strictness)
    pose = _Pose(landmarks, times, aspect_ratio)
    elbow, arms_seen = pose.mean_angle(*_ARMS)
    if arms_seen.mean() < 0.5:
        return _NOT_IN_FRAME
    upper_arm = _upper_arm_from_vertical(pose)
    lean = pose.torso_lean()
    view = pose.upper_body_view()

    segments = segment_reps(elbow, times, enter_drop=40, exit_drop=20,
                            min_duration=0.4, max_duration=10)
    segments = [s for s in segments
                if arms_seen[s[1]] and elbow[s[1]] <= _CURL_MAX_BOTTOM_ELBOW_DEG]

    reps = []
    for k, (start, bottom, end) in enumerate(segments):
        rep_frames = slice(start, end + 1)
        extension = float(np.max(elbow[_rest_window(segments, k, times, after=False)]))
        swing = float(np.ptp(lean[rep_frames]))
        lower = float(times[end] - times[bottom])
        checks = [
            _check("full_curl", "Full curl", float(elbow[bottom]), limits["flex_max"],
                   at_most=True, tolerance=40, unit="deg", weight=2.0,
                   cue="Curl all the way up — squeeze at the top."),
            _check("full_extension", "Full extension", extension, limits["extend_min"],
                   at_most=False, tolerance=40, unit="deg",
                   cue="Lower all the way — straighten your arms between reps."),
            _check("elbows_pinned", "Elbows pinned", float(np.max(upper_arm[rep_frames])),
                   limits["upper_arm_max"], at_most=True, tolerance=25, unit="deg",
                   cue="Keep your elbows pinned to your sides."),
            _check("no_swing", "No swinging", swing, limits["swing_max"],
                   at_most=True, tolerance=15, unit="deg",
                   cue="Don't swing — keep your torso still."),
        ]
        if timing_reliable:
            checks.append(_check(
                "lowering_control", "Slow lowering", lower, limits["lower_min"],
                at_most=False, tolerance=0.4, unit="s",
                cue=f"Lower the weight slowly — you took {lower:.1f}s.",
            ))
        reps.append(_make_rep(k + 1, (start, bottom, end), times, checks, {
            "elbow_top_deg": elbow[bottom],
            "elbow_start_deg": extension,
            "torso_swing_deg": swing,
            "lowering_s": lower,
        }))

    notes: list[str] = []
    _timing_note(timing_reliable, notes, "lowering speed")
    return _finish(reps, view, "curl", notes,
                   "Keep your arms in frame and straighten them fully between reps.")


# ─── Overhead press ────────────────────────────────────────────────
#   lockout_min    elbow angle at the top
#   lean_max       torso lean from vertical during the rep (side view)
#   uneven_max     left/right wrist height difference at the top, in arm
#                  lengths (front view)
#   lower_min      seconds lowering the weight
_PRESS_LIMITS = {
    "lenient": dict(lockout_min=150, lean_max=25, uneven_max=0.25, lower_min=0.25),
    "moderate": dict(lockout_min=160, lean_max=15, uneven_max=0.15, lower_min=0.4),
    "strict": dict(lockout_min=165, lean_max=10, uneven_max=0.10, lower_min=0.6),
    "drill_sergeant": dict(lockout_min=170, lean_max=7, uneven_max=0.07, lower_min=0.8),
}
# Rep segmentation on wrist height above the shoulder in arm lengths:
# ~0.1–0.3 racked at the shoulders, ~0.9 locked out overhead, negative with
# the arms hanging. A rep goes above PRESS_UP and back below PRESS_DOWN.
_PRESS_UP = 0.65
_PRESS_DOWN = 0.40
_PRESS_MIN_TOP_ELBOW_DEG = 120.0


def _grade_press(landmarks, times, strictness, aspect_ratio, timing_reliable) -> RepAnalysis:
    limits = _limits(_PRESS_LIMITS, strictness)
    pose = _Pose(landmarks, times, aspect_ratio)
    elbow, arms_seen = pose.mean_angle(*_ARMS)
    if arms_seen.mean() < 0.5:
        return _NOT_IN_FRAME

    def wrist_height(sh: int, el: int, wr: int) -> tuple[np.ndarray, np.ndarray]:
        ok = pose.seen(sh, el, wr)
        arm = pose.rolling_length(sh, el, ok) + pose.rolling_length(el, wr, ok)
        arm = np.maximum(_fill_nans(arm), 1e-4) if np.isfinite(arm).any() else np.ones(len(ok))
        return (pose.pt(sh)[:, 1] - pose.pt(wr)[:, 1]) / arm, ok

    h_l, ok_l = wrist_height(L_SHOULDER, L_ELBOW, L_WRIST)
    h_r, ok_r = wrist_height(R_SHOULDER, R_ELBOW, R_WRIST)
    height = pose.smooth(_side_mean(h_l, h_r, ok_l, ok_r))
    uneven = pose.smooth(np.abs(h_l - h_r))
    lean = pose.torso_lean()
    view = pose.upper_body_view()

    # Negate so the rest position (racked) is high and the press dips.
    segments = segment_reps(-height, times, enter_drop=_PRESS_UP, exit_drop=_PRESS_DOWN,
                            min_duration=0.4, max_duration=10, top=0.0)
    segments = [s for s in segments
                if arms_seen[s[1]] and elbow[s[1]] >= _PRESS_MIN_TOP_ELBOW_DEG]

    reps = []
    for k, (start, top, end) in enumerate(segments):
        rep_frames = slice(start, end + 1)
        lockout = float(np.max(elbow[rep_frames]))
        lower = float(times[end] - times[top])
        checks = [_check(
            "lockout", "Lockout", lockout, limits["lockout_min"], at_most=False,
            tolerance=30, unit="deg", weight=2.0,
            cue="Lock out overhead — straighten your arms fully.",
        )]
        if view == "side":
            checks.append(_check(
                "no_lean_back", "Ribs down", float(np.max(lean[rep_frames])), limits["lean_max"],
                at_most=True, tolerance=15, unit="deg",
                cue="Don't lean back — brace your core and squeeze your glutes.",
            ))
        elif ok_l[top] and ok_r[top]:
            checks.append(_check(
                "even_arms", "Even arms", float(uneven[top]), limits["uneven_max"],
                at_most=True, tolerance=0.2, unit="ratio",
                cue="Press both arms evenly — one side is lagging.",
            ))
        if timing_reliable:
            checks.append(_check(
                "lowering_control", "Controlled lowering", lower, limits["lower_min"],
                at_most=False, tolerance=0.4, unit="s",
                cue=f"Lower the weight under control — you took {lower:.1f}s.",
            ))
        reps.append(_make_rep(k + 1, (start, top, end), times, checks, {
            "elbow_lockout_deg": lockout,
            "wrist_height": height[top],
            "torso_lean_deg": np.max(lean[rep_frames]),
            "lowering_s": lower,
        }))

    notes = []
    if view == "side":
        notes.append("Filmed from the side: arm evenness isn't checked. "
                     "Film from the front to grade it.")
    else:
        notes.append("Filmed from the front: leaning back isn't checked. "
                     "Film from the side to grade it.")
    _timing_note(timing_reliable, notes, "lowering speed")
    return _finish(reps, view, "press", notes,
                   "Keep your arms in frame and bring the weight back to your shoulders "
                   "between reps.")


# ─── Push-up ───────────────────────────────────────────────────────
#   depth_max      elbow angle at the bottom
#   line_min       shoulder–hip–ankle angle (180 = straight body)
#   lockout_min    elbow angle before the rep
#   descent_min    seconds lowering
_PUSHUP_LIMITS = {
    "lenient": dict(depth_max=110, line_min=155, lockout_min=140, descent_min=0.2),
    "moderate": dict(depth_max=100, line_min=165, lockout_min=150, descent_min=0.3),
    "strict": dict(depth_max=90, line_min=170, lockout_min=160, descent_min=0.5),
    "drill_sergeant": dict(depth_max=80, line_min=173, lockout_min=165, descent_min=0.7),
}
_PUSHUP_MAX_BOTTOM_ELBOW_DEG = 135.0
# Torso angle from vertical above this means the user is lying, not standing.
_LYING_MIN_LEAN_DEG = 50.0


def _line_cue(sag: float) -> str:
    if sag > 0:
        return "Squeeze your glutes and brace — your hips are sagging."
    return "Lower your hips — keep a straight line from head to heels."


def _grade_pushup(landmarks, times, strictness, aspect_ratio, timing_reliable) -> RepAnalysis:
    limits = _limits(_PUSHUP_LIMITS, strictness)
    pose = _Pose(landmarks, times, aspect_ratio)
    elbow, arms_seen = pose.mean_angle(*_ARMS)
    if arms_seen.mean() < 0.5:
        return _NOT_IN_FRAME
    lean = pose.torso_lean()
    line, sag, line_seen = pose.body_line()
    view = pose.upper_body_view()

    segments = segment_reps(elbow, times, enter_drop=35, exit_drop=15,
                            min_duration=0.4, max_duration=10)
    # A push-up happens lying down; elbow bends while standing are setup.
    segments = [s for s in segments
                if arms_seen[s[1]] and elbow[s[1]] <= _PUSHUP_MAX_BOTTOM_ELBOW_DEG
                and lean[s[1]] >= _LYING_MIN_LEAN_DEG]

    reps = []
    for k, (start, bottom, end) in enumerate(segments):
        rep_frames = slice(start, end + 1)
        lockout = float(np.max(elbow[_rest_window(segments, k, times, after=False)]))
        descent = float(times[bottom] - times[start])
        checks = [
            _check("depth", "Depth", float(elbow[bottom]), limits["depth_max"],
                   at_most=True, tolerance=40, unit="deg", weight=2.0,
                   cue="Go lower — bring your chest toward the floor."),
            _check("lockout", "Lockout", lockout, limits["lockout_min"],
                   at_most=False, tolerance=30, unit="deg",
                   cue="Push all the way up — lock out your arms between reps."),
        ]
        if view == "side" and line_seen[bottom]:
            worst = start + int(np.argmin(line[rep_frames]))
            checks.append(_check(
                "body_line", "Straight body", float(line[worst]), limits["line_min"],
                at_most=False, tolerance=30, unit="deg", cue=_line_cue(sag[worst]),
            ))
        if timing_reliable:
            checks.append(_check(
                "descent_control", "Controlled descent", descent, limits["descent_min"],
                at_most=False, tolerance=0.3, unit="s",
                cue=f"Lower yourself under control — you dropped in {descent:.1f}s.",
            ))
        reps.append(_make_rep(k + 1, (start, bottom, end), times, checks, {
            "elbow_bottom_deg": elbow[bottom],
            "body_line_deg": np.min(line[rep_frames]),
            "descent_s": descent,
        }))

    notes = []
    if view != "side":
        notes.append("Not filmed from the side: body line isn't checked. "
                     "Film from the side to grade it.")
    _timing_note(timing_reliable, notes, "descent speed")
    return _finish(reps, view, "push-up", notes,
                   "Film from the side with your whole body in frame, "
                   "and lock out your arms between reps.")


# ─── Lunge ─────────────────────────────────────────────────────────
#   depth_max      front-leg hip height above the knee, in thigh lengths
#   shin_max       front shin angle from vertical at the bottom (side view)
#   lean_max       torso lean from vertical at the bottom (side view)
#   descent_min    seconds lowering
_LUNGE_LIMITS = {
    "lenient": dict(depth_max=0.45, shin_max=40, lean_max=40, descent_min=0.25),
    "moderate": dict(depth_max=0.35, shin_max=35, lean_max=30, descent_min=0.4),
    "strict": dict(depth_max=0.25, shin_max=30, lean_max=20, descent_min=0.6),
    "drill_sergeant": dict(depth_max=0.15, shin_max=25, lean_max=15, descent_min=0.8),
}
_LUNGE_MAX_BOTTOM_KNEE_DEG = 140.0


def _grade_lunge(landmarks, times, strictness, aspect_ratio, timing_reliable) -> RepAnalysis:
    limits = _limits(_LUNGE_LIMITS, strictness)
    pose = _Pose(landmarks, times, aspect_ratio)
    heights = pose.hip_heights()
    left_ok, right_ok = pose.seen(L_HIP, L_KNEE), pose.seen(R_HIP, R_KNEE)
    if heights is None or (left_ok | right_ok).mean() < 0.5:
        return _NOT_IN_FRAME

    # The front thigh drops the most, so track the lower of the two sides.
    h_l = pose.smooth(np.where(left_ok, heights["left"], np.nan))
    h_r = pose.smooth(np.where(right_ok, heights["right"], np.nan))
    front_height = np.fmin(h_l, h_r)
    knee_l, knee_r, kl_ok, kr_ok = pose.sided_angle(
        (L_HIP, L_KNEE, L_ANKLE), (R_HIP, R_KNEE, R_ANKLE))
    knee_l, knee_r = pose.smooth(knee_l), pose.smooth(knee_r)
    lean = pose.torso_lean()
    hip_width = np.abs(pose.pt(L_HIP)[:, 0] - pose.pt(R_HIP)[:, 0])
    view = ("front" if float(np.median(hip_width / heights["thigh"])) >= _FRONT_VIEW_HIP_RATIO
            else "side")

    def shin_from_vertical(knee: int, ankle: int) -> np.ndarray:
        v = pose.pt(knee) - pose.pt(ankle)
        return pose.smooth(np.degrees(np.arctan2(np.abs(v[:, 0]), -v[:, 1])))

    shin_l = shin_from_vertical(L_KNEE, L_ANKLE)
    shin_r = shin_from_vertical(R_KNEE, R_ANKLE)

    segments = segment_reps(front_height, times, enter_drop=0.3, exit_drop=0.12,
                            min_duration=0.4, max_duration=10, top=1.0)
    segments = [s for s in segments
                if (left_ok | right_ok)[s[1]]
                and min(knee_l[s[1]], knee_r[s[1]]) <= _LUNGE_MAX_BOTTOM_KNEE_DEG]

    reps = []
    for k, (start, bottom, end) in enumerate(segments):
        left_front = h_l[bottom] <= h_r[bottom]
        depth = float(front_height[bottom])
        descent = float(times[bottom] - times[start])
        checks = [_check(
            "depth", "Depth", depth, limits["depth_max"], at_most=True, tolerance=0.4,
            unit="thigh", weight=2.0, cue="Sink lower — bring your front thigh toward parallel.",
        )]
        if view == "side":
            shin = float((shin_l if left_front else shin_r)[bottom])
            checks += [
                _check("front_shin", "Front shin", shin, limits["shin_max"], at_most=True,
                       tolerance=20, unit="deg",
                       cue="Keep your front knee over your ankle — take a longer step."),
                _check("torso_upright", "Torso upright", float(lean[bottom]), limits["lean_max"],
                       at_most=True, tolerance=20, unit="deg",
                       cue="Stay tall — keep your torso upright."),
            ]
        if timing_reliable:
            checks.append(_check(
                "descent_control", "Controlled descent", descent, limits["descent_min"],
                at_most=False, tolerance=0.4, unit="s",
                cue=f"Control the way down — you dropped in {descent:.1f}s.",
            ))
        reps.append(_make_rep(k + 1, (start, bottom, end), times, checks, {
            "front_hip_height": depth,
            "front_knee_deg": (knee_l if left_front else knee_r)[bottom],
            "torso_lean_deg": lean[bottom],
            "descent_s": descent,
        }, side="left" if left_front else "right"))

    notes = []
    if view == "front":
        notes.append("Filmed from the front: torso and shin angle aren't checked. "
                     "Film from the side to grade them.")
    _timing_note(timing_reliable, notes, "descent speed")
    return _finish(reps, view, "lunge", notes,
                   "Make sure your whole body is in frame and stand all the way up between reps.")


# ─── Deadlift ──────────────────────────────────────────────────────
#   lockout_min      hip angle (shoulder–hip–knee) at the top
#   hips_first_min   hip angle when the knees reach near-straight on the way
#                    up; low means the hips shot up before the chest
#   lean_back_max    backward torso lean at lockout
#   lower_min        seconds lowering
_DEADLIFT_LIMITS = {
    "lenient": dict(lockout_min=155, hips_first_min=110, lean_back_max=20, lower_min=0.2),
    "moderate": dict(lockout_min=165, hips_first_min=125, lean_back_max=12, lower_min=0.4),
    "strict": dict(lockout_min=170, hips_first_min=135, lean_back_max=8, lower_min=0.6),
    "drill_sergeant": dict(lockout_min=172, hips_first_min=140, lean_back_max=5, lower_min=0.8),
}
_DEADLIFT_MAX_BOTTOM_HIP_DEG = 130.0
_DEADLIFT_KNEES_STRAIGHT_DEG = 155.0
# Knees bent less than this at the bottom is a stiff-legged / Romanian style,
# where "hips first" doesn't apply.
_DEADLIFT_MIN_KNEE_BEND_DEG = 140.0


def _grade_deadlift(landmarks, times, strictness, aspect_ratio, timing_reliable) -> RepAnalysis:
    limits = _limits(_DEADLIFT_LIMITS, strictness)
    pose = _Pose(landmarks, times, aspect_ratio)
    hip, hips_seen = pose.mean_angle(
        (L_SHOULDER, L_HIP, L_KNEE), (R_SHOULDER, R_HIP, R_KNEE))
    knee, _ = pose.mean_angle((L_HIP, L_KNEE, L_ANKLE), (R_HIP, R_KNEE, R_ANKLE))
    if hips_seen.mean() < 0.5:
        return _NOT_IN_FRAME
    view = pose.upper_body_view()

    # Signed torso lean: positive forward of vertical, negative leaning back.
    torso = pose.mid(L_SHOULDER, R_SHOULDER) - pose.mid(L_HIP, R_HIP)
    forward = pose.facing() * torso[:, 0]
    lean_signed = pose.smooth(np.degrees(np.arctan2(forward, -torso[:, 1])))

    segments = segment_reps(hip, times, enter_drop=40, exit_drop=15,
                            min_duration=0.6, max_duration=15)
    segments = [s for s in segments
                if hips_seen[s[1]] and hip[s[1]] <= _DEADLIFT_MAX_BOTTOM_HIP_DEG]

    reps = []
    for k, (start, bottom, end) in enumerate(segments):
        top_frames = _rest_window(segments, k, times, after=True)
        top = top_frames.start + int(np.argmax(hip[top_frames]))
        lockout = float(hip[top])
        # The most backward lean on the way up and at the top. The hip angle
        # peaks while passing upright, before any lean back, so the lockout
        # frame alone would miss it.
        lean_back = max(0.0, -float(np.min(lean_signed[bottom:top_frames.stop])))
        lower = float(times[bottom] - times[start])
        checks = [
            _check("lockout", "Lockout", lockout, limits["lockout_min"], at_most=False,
                   tolerance=25, unit="deg", weight=2.0,
                   cue="Finish each rep — stand tall with your hips fully locked out."),
            _check("no_lean_back", "No lean back", lean_back, limits["lean_back_max"],
                   at_most=True, tolerance=15, unit="deg",
                   cue="Don't lean back at the top — just stand tall."),
        ]
        if knee[bottom] <= _DEADLIFT_MIN_KNEE_BEND_DEG:
            ascent = np.arange(bottom, end + 1)
            straight = ascent[knee[ascent] >= _DEADLIFT_KNEES_STRAIGHT_DEG]
            if len(straight):
                checks.append(_check(
                    "hips_first", "Hips and chest together", float(hip[straight[0]]),
                    limits["hips_first_min"], at_most=False, tolerance=30, unit="deg",
                    cue="Don't let your hips shoot up — push the floor away and lift your "
                        "chest with your hips.",
                ))
        if timing_reliable:
            checks.append(_check(
                "lowering_control", "Controlled lowering", lower, limits["lower_min"],
                at_most=False, tolerance=0.4, unit="s",
                cue=f"Lower the bar under control — you took {lower:.1f}s.",
            ))
        reps.append(_make_rep(k + 1, (start, bottom, end), times, checks, {
            "hip_bottom_deg": hip[bottom],
            "knee_bottom_deg": knee[bottom],
            "hip_lockout_deg": lockout,
            "lean_back_deg": lean_back,
        }))

    notes = ["Bending down and standing back up counts as a rep, including setting the "
             "bar down at the end — stop recording with the bar on the floor."]
    if view == "front":
        notes.insert(0, "Deadlifts need a side view: film from the side to count and grade reps.")
    _timing_note(timing_reliable, notes, "lowering speed")
    return _finish(reps, view, "deadlift", notes,
                   "Film from the side with your whole body in frame, and stand fully "
                   "upright between reps.")


# ─── Plank (hold) ──────────────────────────────────────────────────
#   line_min    shoulder–hip–ankle angle held for most of the plank
#   drift_max   spread of that angle during the hold (hips moving)
_PLANK_LIMITS = {
    "lenient": dict(line_min=155, drift_max=15),
    "moderate": dict(line_min=165, drift_max=10),
    "strict": dict(line_min=170, drift_max=7),
    "drill_sergeant": dict(line_min=173, drift_max=5),
}
_PLANK_MIN_HOLD_S = 3.0


def _grade_plank(landmarks, times, strictness, aspect_ratio, timing_reliable) -> RepAnalysis:
    limits = _limits(_PLANK_LIMITS, strictness)
    pose = _Pose(landmarks, times, aspect_ratio)
    line, sag, line_seen = pose.body_line()
    lying = line_seen & (pose.torso_lean() >= _LYING_MIN_LEAN_DEG)
    view = pose.upper_body_view()

    # Longest run of frames in the plank position.
    best: tuple[int, int] | None = None
    run_start = None
    for i, on in enumerate(np.append(lying, False)):
        if on and run_start is None:
            run_start = i
        elif not on and run_start is not None:
            if best is None or times[i - 1] - times[run_start] > times[best[1]] - times[best[0]]:
                best = (run_start, i - 1)
            run_start = None

    if best is None or times[best[1]] - times[best[0]] < _PLANK_MIN_HOLD_S:
        return RepAnalysis(
            reps=[], camera_view=view, mode="hold",
            message="No plank hold detected. Film from the side with your whole body in frame.",
        )

    a, b = best
    hold = slice(a, b + 1)
    held_s = float(times[b] - times[a])
    # The line most of the hold: the 20th percentile, so a sustained sag
    # fails but a brief wobble doesn't.
    typical = float(np.percentile(line[hold], 20))
    drift = float(np.percentile(line[hold], 90) - np.percentile(line[hold], 10))
    checks = [
        _check("body_line", "Straight body", typical, limits["line_min"], at_most=False,
               tolerance=30, unit="deg", weight=2.0, cue=_line_cue(float(np.median(sag[hold])))),
        _check("steady_hips", "Steady hips", drift, limits["drift_max"], at_most=True,
               tolerance=15, unit="deg", cue="Hold still — your hips are drifting up and down."),
    ]
    middle = a + (b - a) // 2
    result = _make_rep(1, (a, middle, b), times, checks, {
        "hold_s": held_s,
        "body_line_deg": typical,
    })
    verdict = "good form" if result.passed else result.cue
    notes = [] if view == "side" else [
        "Not filmed from the side: the body line may be misread. Film from the side."]
    return RepAnalysis(
        reps=[result], camera_view=view, mode="hold",
        message=f"Held a plank for {held_s:.0f}s — {verdict}", notes=notes,
    )


def _summary(reps: list[RepResult], noun: str, empty_hint: str) -> str:
    if not reps:
        return f"No complete {noun} reps detected. {empty_hint}"
    good = sum(r.passed for r in reps)
    msg = f"{len(reps)} rep{'s' if len(reps) != 1 else ''}, {good} with good form."
    # Most common fault across reps.
    faults: dict[str, list[RepResult]] = {}
    for r in reps:
        for c in r.checks:
            if not c.passed:
                faults.setdefault(c.name, []).append(r)
    if faults:
        name, hit = max(faults.items(), key=lambda kv: len(kv[1]))
        cue = next(c.cue for c in hit[0].checks if c.name == name)
        which = ", ".join(str(r.index) for r in hit)
        msg += f" Main fix (rep{'s' if len(hit) > 1 else ''} {which}): {cue}"
    return msg


# ─── Public API ────────────────────────────────────────────────────

_GRADERS = {
    "squat": _grade_squat,
    "barbell_biceps_curl": _grade_curl,
    "overhead_press": _grade_press,
    "push_up": _grade_pushup,
    "lunge": _grade_lunge,
    "deadlift": _grade_deadlift,
    "plank": _grade_plank,
}


def supports(exercise: str) -> bool:
    """Whether per-rep grading exists for this exercise."""
    return exercise.lower() in _GRADERS


def grade_reps(
    landmarks: np.ndarray,
    times: np.ndarray,
    exercise: str,
    strictness: str = "moderate",
    aspect_ratio: float = 4 / 3,
    timing_reliable: bool = True,
) -> RepAnalysis | None:
    """
    Segment and grade reps. Returns None if the exercise has no grader.

    Args:
        landmarks: (T, 33, 4) MediaPipe image landmarks (x, y, z, visibility).
        times: (T,) frame times in seconds, increasing.
        exercise: Exercise slug, e.g. "squat".
        strictness: Strictness level name.
        aspect_ratio: Frame width / height, to undistort x.
        timing_reliable: False when times were synthesized from an assumed
            FPS; tempo checks are skipped then.
    """
    grader = _GRADERS.get(exercise.lower())
    if grader is None:
        return None
    return grader(landmarks, np.asarray(times, dtype=np.float64),
                  strictness.lower(), aspect_ratio, timing_reliable)
