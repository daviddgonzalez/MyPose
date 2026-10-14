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
    - checks evaluated at the bottom of each rep.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)

# MediaPipe Pose landmark indices
L_SHOULDER, R_SHOULDER = 11, 12
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


@dataclass
class RepAnalysis:
    """Output of grade_reps()."""
    reps: list[RepResult]
    camera_view: str     # "side" | "front"
    message: str
    notes: list[str] = field(default_factory=list)


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


def segment_reps(
    signal: np.ndarray,
    times: np.ndarray,
    enter_drop: float,
    exit_drop: float,
    min_duration: float,
    max_duration: float,
) -> list[tuple[int, int, int]]:
    """
    Find reps in a smoothed signal that rests high and dips during each rep.

    Hysteresis against the session's rest level (95th percentile):
    a rep starts when the signal drops more than `enter_drop` below rest and
    ends when it climbs back within `exit_drop` of rest. Reps cut off by the
    start or end of the recording are dropped.

    Returns:
        List of (start_idx, bottom_idx, end_idx).
    """
    if len(signal) < 3:
        return []

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
        depth_max=0.15, lean_max=55.0, knee_min=0.85, hip_tilt_max=0.12, descent_min=0.40,
    ),
    "strict": dict(
        depth_max=0.00, lean_max=50.0, knee_min=0.90, hip_tilt_max=0.08, descent_min=0.60,
    ),
    "drill_sergeant": dict(
        depth_max=-0.10, lean_max=45.0, knee_min=0.95, hip_tilt_max=0.05, descent_min=0.80,
    ),
}

# Rep segmentation in thigh lengths of hip height above the knee.
_SQUAT_ENTER_DROP = 0.25
_SQUAT_EXIT_DROP = 0.12
_SQUAT_MIN_REP_S = 0.3
_SQUAT_MAX_REP_S = 10.0

# Hip width / thigh length above this means the camera faces the user.
_FRONT_VIEW_HIP_RATIO = 0.3


def _grade_squat(
    landmarks: np.ndarray,
    times: np.ndarray,
    strictness: str,
    aspect_ratio: float,
    timing_reliable: bool,
) -> RepAnalysis:
    limits = _SQUAT_LIMITS.get(strictness, _SQUAT_LIMITS["moderate"])

    xy = landmarks[:, :, :2].astype(np.float64).copy()
    xy[:, :, 0] *= aspect_ratio
    vis = landmarks[:, :, 3]

    def pt(i: int) -> np.ndarray:
        return xy[:, i, :]

    left_ok = (vis[:, L_HIP] >= VISIBILITY_MIN) & (vis[:, L_KNEE] >= VISIBILITY_MIN)
    right_ok = (vis[:, R_HIP] >= VISIBILITY_MIN) & (vis[:, R_KNEE] >= VISIBILITY_MIN)

    if (left_ok | right_ok).mean() < 0.5:
        return RepAnalysis(
            reps=[], camera_view="unknown",
            message=("Couldn't see your hips and knees clearly. "
                     "Step back so your whole body is in frame."),
        )

    # Thigh length reference: the long end of the 2D hip→knee distance,
    # i.e. the thigh as seen while standing upright.
    def thigh_ref(hip: int, knee: int, ok: np.ndarray) -> float:
        lengths = np.linalg.norm(pt(hip) - pt(knee), axis=1)
        return float(np.percentile(lengths[ok], 95)) if ok.any() else np.nan

    ref_l = thigh_ref(L_HIP, L_KNEE, left_ok)
    ref_r = thigh_ref(R_HIP, R_KNEE, right_ok)
    thigh = float(np.nanmean([ref_l, ref_r]))
    if not np.isfinite(thigh) or thigh < 1e-4:
        return RepAnalysis(
            reps=[], camera_view="unknown",
            message="Couldn't measure your legs. Make sure your hips and knees are in frame.",
        )
    ref_l = ref_l if np.isfinite(ref_l) else thigh
    ref_r = ref_r if np.isfinite(ref_r) else thigh

    # Hip height above the knee in thigh lengths: ~1 standing, 0 at parallel.
    # Uses only the vertical axis, so it reads the same from front or side.
    height_l = (pt(L_KNEE)[:, 1] - pt(L_HIP)[:, 1]) / ref_l
    height_r = (pt(R_KNEE)[:, 1] - pt(R_HIP)[:, 1]) / ref_r
    hip_height = _side_mean(height_l, height_r, left_ok, right_ok)

    dt = float(np.median(np.diff(times))) if len(times) > 1 else 1 / 30
    window = max(1, int(round(SMOOTHING_SECONDS / max(dt, 1e-3))))
    hip_height_s = _smooth(hip_height, window)

    # Camera view from how far apart the hips appear relative to the thigh.
    hip_width = np.abs(pt(L_HIP)[:, 0] - pt(R_HIP)[:, 0])
    view = "front" if float(np.median(hip_width)) / thigh >= _FRONT_VIEW_HIP_RATIO else "side"

    # Per-frame metrics, smoothed, read at each rep's bottom.
    shoulder_mid = (pt(L_SHOULDER) + pt(R_SHOULDER)) / 2
    hip_mid = (pt(L_HIP) + pt(R_HIP)) / 2
    torso = shoulder_mid - hip_mid
    lean = _smooth(np.degrees(np.arctan2(np.abs(torso[:, 0]), -torso[:, 1])), window)

    knee_angle = _smooth(_side_mean(
        _angle_deg(pt(L_HIP), pt(L_KNEE), pt(L_ANKLE)),
        _angle_deg(pt(R_HIP), pt(R_KNEE), pt(R_ANKLE)),
        left_ok, right_ok,
    ), window)

    knee_width = np.abs(pt(L_KNEE)[:, 0] - pt(R_KNEE)[:, 0])
    ankle_width = np.abs(pt(L_ANKLE)[:, 0] - pt(R_ANKLE)[:, 0])
    knee_ratio = _smooth(knee_width / np.maximum(ankle_width, 1e-6), window)
    ankle_width_s = _smooth(ankle_width, window)
    hip_tilt = _smooth(np.abs(pt(L_HIP)[:, 1] - pt(R_HIP)[:, 1]) / thigh, window)

    segments = segment_reps(
        hip_height_s, times,
        enter_drop=_SQUAT_ENTER_DROP, exit_drop=_SQUAT_EXIT_DROP,
        min_duration=_SQUAT_MIN_REP_S, max_duration=_SQUAT_MAX_REP_S,
    )

    reps: list[RepResult] = []
    for n, (start, bottom, end) in enumerate(segments, start=1):
        checks: list[tuple[RepCheck, float]] = []  # (check, weight)

        depth = float(hip_height_s[bottom])
        ok = depth <= limits["depth_max"]
        checks.append((RepCheck(
            name="depth", label="Depth", passed=ok,
            value=round(depth, 2), target=limits["depth_max"], unit="thigh",
            score=_graded(ok, depth - limits["depth_max"], 0.4),
            cue="" if ok else "Squat deeper — get your hips down to knee level.",
        ), 2.0))

        if view == "side":
            lean_b = float(lean[bottom])
            ok = lean_b <= limits["lean_max"]
            checks.append((RepCheck(
                name="torso_lean", label="Chest up", passed=ok,
                value=round(lean_b, 1), target=limits["lean_max"], unit="deg",
                score=_graded(ok, lean_b - limits["lean_max"], 20.0),
                cue="" if ok else f"Keep your chest up — torso leaned {lean_b:.0f}° at the bottom.",
            ), 1.0))
        else:
            # Knee tracking only means something when the feet are apart.
            if ankle_width_s[bottom] >= 0.15 * thigh:
                ratio = float(knee_ratio[bottom])
                ok = ratio >= limits["knee_min"]
                checks.append((RepCheck(
                    name="knee_tracking", label="Knees out", passed=ok,
                    value=round(ratio, 2), target=limits["knee_min"], unit="ratio",
                    score=_graded(ok, limits["knee_min"] - ratio, 0.3),
                    cue="" if ok else "Push your knees out over your toes — they're caving in.",
                ), 1.0))
            tilt = float(hip_tilt[bottom])
            ok = tilt <= limits["hip_tilt_max"]
            checks.append((RepCheck(
                name="hip_level", label="Level hips", passed=ok,
                value=round(tilt, 2), target=limits["hip_tilt_max"], unit="thigh",
                score=_graded(ok, tilt - limits["hip_tilt_max"], 0.15),
                cue="" if ok else "Keep your hips level — you're shifting to one side.",
            ), 1.0))

        descent = float(times[bottom] - times[start])
        if timing_reliable:
            ok = descent >= limits["descent_min"]
            checks.append((RepCheck(
                name="descent_control", label="Controlled descent", passed=ok,
                value=round(descent, 2), target=limits["descent_min"], unit="s",
                score=_graded(ok, limits["descent_min"] - descent, 0.4),
                cue="" if ok else f"Control the way down — you dropped in {descent:.1f}s.",
            ), 1.0))

        total_weight = sum(w for _, w in checks)
        score = 100.0 * sum(c.score * w for c, w in checks) / total_weight
        failed = [c for c, _ in checks if not c.passed]
        # Most important cue: the failed check with the lowest score.
        cue = min(failed, key=lambda c: c.score).cue if failed else None

        reps.append(RepResult(
            index=n,
            start_time=round(float(times[start] - times[0]), 2),
            bottom_time=round(float(times[bottom] - times[0]), 2),
            end_time=round(float(times[end] - times[0]), 2),
            score=round(score, 1),
            passed=not failed,
            checks=[c for c, _ in checks],
            cue=cue,
            metrics={
                "hip_height": round(depth, 2),
                "knee_angle_deg": round(float(knee_angle[bottom]), 1),
                "torso_lean_deg": round(float(lean[bottom]), 1),
                "descent_s": round(descent, 2),
                "rep_duration_s": round(float(times[end] - times[start]), 2),
            },
        ))

    notes = []
    if view == "front":
        notes.append("Filmed from the front: torso lean isn't checked. "
                     "Film from the side to grade it.")
    else:
        notes.append("Filmed from the side: knee tracking isn't checked. "
                     "Film from the front to grade it.")
    if not timing_reliable:
        notes.append("Frame timing unavailable: descent speed isn't checked.")

    return RepAnalysis(reps=reps, camera_view=view, message=_summary(reps, "squat"), notes=notes)


def _summary(reps: list[RepResult], noun: str) -> str:
    if not reps:
        return (f"No complete {noun} reps detected. Make sure your whole body is in frame "
                f"and stand all the way up between reps.")
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
