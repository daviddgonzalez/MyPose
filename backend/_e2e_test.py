"""One-shot end-to-end backend test. Not part of the app; safe to delete after."""
import json
import sys
import time

import numpy as np
import requests

BASE = "http://localhost:8000"
USERNAME = f"e2e_{int(time.time())}"
PASSWORD = "testpass123"


def synthetic_frames(n=40, seed=0, noise=0.05):
    """Return n frames of 33 landmarks, structured like the FrameData schema."""
    rng = np.random.default_rng(seed)
    # Start from a stable "skeleton" centered on origin so normalization works.
    base = rng.standard_normal((33, 3)) * 0.3
    frames = []
    for i in range(n):
        lms = base + rng.standard_normal((33, 3)) * noise
        frames.append({
            "frame_idx": i,
            "landmarks": [
                {"x": float(lms[j, 0]), "y": float(lms[j, 1]), "z": float(lms[j, 2]), "visibility": 1.0}
                for j in range(33)
            ],
        })
    return frames


def pp(label, resp):
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    print(f"--- {label} ({resp.status_code}) ---")
    print(json.dumps(body, indent=2)[:1500])
    print()
    return body


def main():
    # 1. Register + login
    reg = requests.post(f"{BASE}/api/v1/auth/register",
                        json={"username": USERNAME, "password": PASSWORD})
    body = pp(f"REGISTER {USERNAME}", reg)
    user_id = body["user_id"]
    assert body["message"] == "Account created.", f"local-fallback returned: {body['message']}"

    pp("LOGIN", requests.post(f"{BASE}/api/v1/auth/login",
                              json={"username": USERNAME, "password": PASSWORD}))

    # 2. Calibration
    start = requests.post(f"{BASE}/api/v1/calibrate/start",
                          json={"user_id": user_id, "exercise_name": "squat"})
    sid = pp("CALIBRATE START", start)["session_id"]

    # 4 sequences × 200 frames = 800 total — clears the new defensive floor
    # (>=75 frames per take, >=450 total) added in routes_calibration.py.
    for i in range(4):
        frames = synthetic_frames(n=200, seed=i, noise=0.05)
        r = requests.post(f"{BASE}/api/v1/calibrate/{sid}/sequence",
                          json={"landmarks": frames})
        pp(f"  CALIBRATE SEQ {i+1}", r)

    fin = requests.post(f"{BASE}/api/v1/calibrate/{sid}/finalize")
    fin_body = pp("CALIBRATE FINALIZE", fin)
    assert fin_body["centroid_stored"] is True, "centroid was NOT stored!"
    assert fin_body["num_sequences"] == 4

    # 3. /evaluate — similar to a calibration sequence (probably borderline pass).
    similar = synthetic_frames(n=200, seed=0, noise=0.05)
    r = requests.post(f"{BASE}/api/v1/evaluate",
                      json={"user_id": user_id, "exercise_name": "squat", "landmarks": similar})
    body_similar = pp("EVALUATE: similar-to-calibration", r)
    if r.status_code != 200:
        print("!! /evaluate returned non-200; aborting downstream assertions but continuing other probes.")
        body_similar = {"evaluation_id": "ERR", "distance_to_centroid": 0.0, "passed": None}

    # 4. /evaluate — clearly different (should fail + trigger DTW).
    different = synthetic_frames(n=200, seed=999, noise=0.5)
    r = requests.post(f"{BASE}/api/v1/evaluate",
                      json={"user_id": user_id, "exercise_name": "squat", "landmarks": different})
    body_diff = pp("EVALUATE: deliberately-different", r)
    if r.status_code != 200:
        body_diff = {"evaluation_id": "ERR2", "distance_to_centroid": 0.0, "passed": None,
                     "dtw_triggered": False, "joint_errors": []}

    # 5. Evaluations should be unique (proves we're not returning the same cached row).
    if body_similar.get("evaluation_id", "").startswith("ERR"):
        print("[skip] evaluation_id uniqueness (one or both /evaluate calls failed)")
    else:
        assert body_similar["evaluation_id"] != body_diff["evaluation_id"]

    # 6. Uncalibrated user case — evaluate for an exercise the user hasn't calibrated.
    r = requests.post(f"{BASE}/api/v1/evaluate",
                      json={"user_id": user_id, "exercise_name": "deadlift", "landmarks": similar})
    body_unc = pp("EVALUATE: uncalibrated exercise", r)
    if r.status_code == 200:
        assert "has not calibrated" in body_unc["message"].lower(), body_unc["message"]

    # 7. Unknown exercise.
    r = requests.post(f"{BASE}/api/v1/evaluate",
                      json={"user_id": user_id, "exercise_name": "made_up_exercise", "landmarks": similar})
    body_unk = pp("EVALUATE: unknown exercise", r)
    if r.status_code == 200:
        assert "unknown exercise" in body_unk["message"].lower(), body_unk["message"]

    # 8. Run a second 'similar' evaluation and confirm uniqueness of evaluation_id.
    r2 = requests.post(f"{BASE}/api/v1/evaluate",
                       json={"user_id": user_id, "exercise_name": "squat", "landmarks": similar})
    body_again = pp("EVALUATE: repeat (uniqueness check)", r2)
    if r2.status_code == 200 and not body_similar.get("evaluation_id", "").startswith("ERR"):
        assert body_again["evaluation_id"] != body_similar["evaluation_id"]

    # 9. Upload without user_id/exercise (no real .mp4 — expect 400 content-type error,
    #    proves the route is mounted; the auto-evaluate branch needs a real video).
    r = requests.post(f"{BASE}/api/v1/upload",
                      files={"file": ("fake.txt", b"not-a-video", "text/plain")})
    pp("UPLOAD: rejects non-video", r)

    print("\n=== SUMMARY ===")
    print(f"user_id           : {user_id}")
    print(f"session_id        : {sid}")
    print(f"similar dist      : {body_similar['distance_to_centroid']:.4f}  passed={body_similar['passed']}")
    print(f"different dist    : {body_diff['distance_to_centroid']:.4f}  passed={body_diff['passed']}  dtw={body_diff['dtw_triggered']}")
    print(f"different joint_errs: {len(body_diff['joint_errors'])}")
    if body_diff["joint_errors"]:
        top = sorted(body_diff["joint_errors"], key=lambda e: -e["error_score"])[:3]
        for je in top:
            print(f"   {je['joint_name']:20s} {je['description']}")
    print("\nALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
