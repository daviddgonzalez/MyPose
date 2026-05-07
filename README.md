# MyPose

# Personalized Kinematic Evaluator (PKE)

## Overview

BASIC BASIC Overview:

1. Input - either video input for the minimum viable product (MVP) OR streamed via computer vision through a websocket connection (Think livestreaming)

2. Extraction - OpenPose - create the "skeleton" that represents the person, 25 joints go into a 25 node graph with bones as edges. Takes care of blurry frames, parts of body out of screen, etc.

3. Euclidean Normalization - center is hips, essentially make it so its the same whether you're 5 feet away or 2 feet away. Also if you're 6 feet or 4 feet. Temporal Resampling - essentially if the original clip is 30 seconds and you send in a 4 minute version, it speeds it up to 30 seconds. If you send in a super fast 15 second clip, it slows it down to 30 seconds. This is so it can compare 30 seconds of dance/exercise to 30 seconds.

4. Embedding Storage/Creation - Embedding is just 256 variables describing the video - we pass a tensor - literally js 2D array - through the neural network to create these embeddings. User sends in 3-5 videos, we create the average of the 3-5 embeddings, then store in supabase.

5. Evaluation - These 256 variables are like angles between body parts, angle you're leaning, etc. We use cosine similarity to compare two embeddings so the general proportions have to be the same, not magnitudes. If your angles are too far from the training data marked wrong, otherwise it's good :]


This project is an asynchronous Computer Vision pipeline designed to evaluate and correct human movement. Rather than comparing users to a rigid "universal expert," the system utilizes a User-Calibrated Siamese Network. It learns an individual's safe, baseline mobility and evaluates daily workouts against their personal biomechanical profile, flagging deviations and isolating the exact joints that broke form.

The system is designed with a dual-ingestion architecture, supporting both real-time data capture from live footage and a fallback MVP handling pre-recorded video uploads.




## Tech Stack
* **Frontend:** React and TypeScript.
* **Backend API:** FastAPI (Python) for asynchronous request handling.
* **Machine Learning:** PyTorch (ST-GCN and Siamese Network).
* **Computer Vision:** OpenCV and MediaPipe Pose.
* **Database & Auth:** Supabase PostgreSQL (pgvector for embeddings, relational tables for user metadata).
* **Object Storage:** Supabase Storage (for MVP video uploads).
* **Containerization & Deployment:** Docker (for containerizing the FastAPI application and PyTorch environment).
* **High-Performance Logic:** C++ (for computationally heavy evaluation algorithms).

## Quick Start (Running Locally)

To run the full stack locally (Frontend + Backend), simply use the `start.py` script from the root directory:
```powershell
python start.py
```
This script will automatically start the backend FastAPI server and the Next.js frontend, and gracefully kill both when you press `Ctrl+C`.

### Important Setup Rules
If you encounter errors starting the project, double-check these common pitfalls:
1. **Python Version**: You **must** use Python 3.10, 3.11, or 3.12. Do not use Python 3.13+ (MediaPipe does not provide C++ binaries for newer versions and will crash the backend).
2. **Virtual Environment Location**: The `start.py` script expects your virtual environment to be located exactly at `backend\venv` (or `backend\.venv`). Create it using `python -m venv backend\venv`.
3. **NPM Installs**: Do **not** run `npm install` in the root directory. It will create a `package.json` lockfile that permanently breaks the Next.js Turbopack compiler. You must run `npm install` strictly from inside the `frontend/` directory.

## System Architecture

### 1. Data Ingestion (Dual-Path Strategy)
To support both live tracking and a fallback MVP, the pipeline standardizes around a common coordinate payload. 

**Path A: The Live Pipeline (Target)**
* **Process:** The React frontend accesses the user's webcam. MediaPipe JS runs directly in the browser (edge computing) to extract skeletal landmarks frame-by-frame.
* **Transmission:** The frontend streams a lightweight JSON array of x, y, z coordinates to the FastAPI backend via WebSockets. No video data is transmitted, drastically reducing bandwidth and server load.

**Path B: The MVP Fallback (Pre-recorded Uploads)**
* **Process:** The user uploads an .mp4 file via the React frontend to Supabase Storage.
* **Extraction:** The FastAPI backend is triggered asynchronously. It downloads the video, runs OpenCV and MediaPipe in Python to extract the skeletal landmarks, and generates the exact same JSON array format as Path A.

### 2. Base Model (The "Transfer" Foundation)
* **Architecture:** Spatial-Temporal Graph Convolutional Network (ST-GCN).
* **Pre-training Phase:** Pre-trained on AIST++ or Fit3D using Contrastive Loss to learn the temporal dynamics of human movement.

### 3. User Calibration Phase (Few-Shot Fine-Tuning)
* **Input:** 3 to 5 calibration sequences of the user performing the movement correctly.
* **Process:** The final projection layers of the ST-GCN are fine-tuned on the user's calibration data, mapping the acceptable "movement manifold" to their specific anatomy. Embeddings are stored in Supabase PostgreSQL using pgvector.

### 4. Asynchronous Evaluation (The Inference Pipeline)
1. **Embedding Generation:** The coordinate JSON (from Path A or Path B) is normalized (root-relative centering, scale invariance) and passed through the user-calibrated ST-GCN.
2. **Distance Calculation:** The embedding is compared against the user's calibration centroid in the Supabase database.
3. **Algorithmic Fallback:** If the distance exceeds the acceptable threshold, Dynamic Time Warping (DTW) temporally aligns the bad rep with a calibration rep, computing cosine similarity of joint angles to report the exact error.

## Build Progress

- [x] **Phase 1** — Docker + Backend Scaffold + Supabase Schema
- [x] **Phase 2** — Extraction + Normalization Pipeline
- [x] **Phase 3** — C++ Module (DTW + Joint Angles via pybind11)
- [x] **Phase 4** — ST-GCN Architecture — `backend/app/ml/` (`stgcn.py`, `siamese.py`, `model.py`, checkpoints)
- [ ] **Phase 5** — Calibration + Evaluation Services — *partial*: calibration finalize + centroid + ML branch in WebSocket analysis; **`POST /api/v1/evaluate` remains a placeholder**; DTW fallback not wired into live/REST evaluation
- [x] **Phase 6** — Frontend (Next.js/React + TypeScript, MediaPipe, upload + live UX)
- [x] **Phase 7** — Live Pipeline — WebSocket `ws/v1/stream` buffers frames → `analyze_session` (heuristics always; embeddings when centroid + checkpoint exist)
- [ ] **Phase 8** — Pre-training (Fit3D) — *partial*: `pretrain` CLI + `Fit3DContrastiveDataset` implemented; **`data/fit3d/` not in repo**; Fit3D→MediaPipe `.npy` preprocessing is out-of-band (documented in `dataset.py`)

## ML Pipeline Status

*Living assessment (six-stage lifecycle vs code). Evidence paths are from repo root.*

### Maturity matrix

| Stage | Status | Evidence |
|--------|--------|----------|
| **1. Data & labels** | **Partial** | Loader + expected layout in [`backend/app/ml/dataset.py`](backend/app/ml/dataset.py); no sample `data/fit3d/` tree in repo; calibration uses user landmarks via API |
| **2. Training** | **Partial** | [`backend/app/ml/training.py`](backend/app/ml/training.py) (`pretrain`, `finetune`, `compute_centroid`); no fixed validation split/metrics/logging in training loop; checkpoint filename from [`backend/app/config.py`](backend/app/config.py) |
| **3. Evaluation offline** | **Not started** | No held-out suite for embedding quality/threshold tuning; pytest has no PKEModel/training/import tests (`backend/tests/`) |
| **4. Serving & integration** | **Partial** | [`backend/app/main.py`](backend/app/main.py) loads `PKEModel` if checkpoint exists; [`backend/app/services/analysis.py`](backend/app/services/analysis.py) calls `model.embed(normalized)` when centroid present; `(B,3,T,33)` contract in [`backend/app/ml/model.py`](backend/app/ml/model.py) |
| **5. Production persistence** | **Partial** | pgvector-oriented schema [`supabase/migrations/001_initial_schema.sql`](supabase/migrations/001_initial_schema.sql); runtime uses in-memory `_sessions` and `_centroid_store` in calibration + [`backend/app/api/ws_live.py`](backend/app/api/ws_live.py) |
| **6. Ops & quality** | **Minimal** | No `.github/workflows` in repo; DTW exercised only via C++ bindings in [`backend/tests/test_cpp_module.py`](backend/tests/test_cpp_module.py); not invoked from REST/live evaluation |

**Concise posture:** MVP integration uses **heuristics + optional embedding distance on the WebSocket path** after calibration fine-tuning; durable centroids, REST evaluation, and architecture-doc **DTW-on-fail** are still open.

### Prioritized gap backlog

1. **Data pipeline** — Add or document Fit3D→33-joint `.npy` preprocessing; commit or mount `data/fit3d/<exercise>/*.npy` for reproducible pretrain.
2. **Persistence** — Replace in-memory calibration/centroid stores with Supabase (align [`backend/app/api/routes_calibration.py`](backend/app/api/routes_calibration.py) + `ws_live` with migration tables).
3. **REST evaluation** — Implement [`backend/app/api/routes_evaluate.py`](backend/app/api/routes_evaluate.py): normalize → embed → compare to stored centroid → optional DTW/joint report (reuse C++ module + joint angles from [`backend/app/services/normalization.py`](backend/app/services/normalization.py)).
4. **DTW in ML failure path** — Wire DTW + joint-angle comparison when embedding distance exceeds threshold (per architecture overview); today DTW is not called from `analyze_session` or evaluate route.
5. **Offline eval + tests** — Small fixture sequences + tests for `PKEModel.embed` shape/determinism, finetune no-op/range, and threshold behavior; add CI when ready.
6. **Training hygiene** — Seeds, validation metrics, and experiment tracking (optional) before scaling Phase 8.

### Future product check-in (not in current scope)

- Add a per-user progress check-in system to track rep quality trends and total repetition counts over time.
- Keep this as a deferred feature until core calibration/evaluation persistence is fully wired to Supabase.
- New-user default behavior: if a user has no personalization history, evaluate against the base model only.
- Add a **Personalize** button so users can opt into transfer learning, especially for mobility limitations where base-model expectations are not a good fit.
- Redesign mobile navigation/layout so tabs are consistently visible and usable on small screens.

### Personalize UX flow (deferred)

1. **First-time user**: show "Using Base Model" status and a visible **Personalize** CTA on the workout/progress screen.
2. **CTA click**: open a short explanation modal ("Personalize adapts scoring to your mobility and form baseline") with confirm/cancel actions.
3. **If confirmed**: launch calibration capture (3-5 good reps) and run transfer-learning finalize.
4. **On success**: switch status to "Personalized Model Active", record `personalized_at`, and use personalized embeddings for evaluation.
5. **After activation**: keep a secondary option to "Re-personalize" so users can refresh their baseline after recovery/progress changes.

## Next Chat Handoff (tomorrow)

Use this exact prompt in a new chat:

`Read this README first, then continue from the "Tomorrow checkpoint plan" to run pretraining, produce a checkpoint, verify /health shows model_loaded=true, and test calibration finalize persistence to Supabase.`

### Tomorrow checkpoint plan

1. Confirm Fit3D-formatted data directory exists and matches `backend/app/ml/dataset.py` expected layout.
2. Run pretrain from `backend/`:
   - `python -m app.ml.training pretrain --data-dir <fit3d_root> --epochs 1 --device cpu`
3. Ensure checkpoint exists at `checkpoints/pke_pretrained.pt` (or update config/env to the generated filename).
4. Restart backend (`python start.py`) and verify:
   - `GET /health` returns `"model_loaded": true`
5. Run calibration flow:
   - `POST /api/v1/calibrate/start`
   - add >=3 sequences
   - `POST /api/v1/calibrate/{session_id}/finalize`
6. Verify Supabase rows updated:
   - `calibration_sessions`
   - `calibration_sequences` (with embeddings)
   - `calibration_centroids`

### Latest pretrain run (checkpoint note)

- data_dir: `backend/data/fit3d_train`
- epochs: `10`
- batch_size: `16`
- lr: `1e-3`
- device: `cpu`
- output checkpoints:
  - `backend/checkpoints/pke_pretrained.pt` (best)
  - `backend/checkpoints/pke_pretrained_final.pt` (final)

### Runnable verification

Run from `backend/` with venv active (see Quick Start). Adjust host/port if needed.

1. **Model load** — `GET /health` → `model_loaded: true` only if `checkpoints/<checkpoint_file>` exists ([`backend/app/config.py`](backend/app/config.py)). If missing, backend runs heuristic-only; calibration finalize returns failure without embeddings.
2. **Pretrain (requires data)** — `python -m app.ml.training pretrain --data-dir <path_to_fit3d_root> --epochs 1 --device cpu` — succeeds only when directory matches layout in `dataset.py` docstring.
3. **Calibration → live ML** — `POST /api/v1/calibrate/start` → add ≥3 sequences with `landmarks` → `POST .../finalize` (with checkpoint loaded) → open WebSocket `ws/v1/stream`, send `config` with same `user_id` and `exercise` as calibration, stream frames, `end` → `session_feedback` should show `calibration_available: true` and `distance_to_centroid` when centroid was stored.

## Deferred Architecture Decisions

> Revisit these during Phase 8 (Fit3D pre-training) when we have real training data at scale.

- [ ] **ST-GCN depth / width expansion** — Current backbone uses three ST-GCN blocks; channel widths are config-driven via `settings.stgcn_channels` ([`backend/app/config.py`](backend/app/config.py)). Deeper or wider variants are a research item once Fit3D volume justifies capacity and you define how checkpoints transfer.
- [ ] **Cosine Embedding Loss → NT-Xent** — MVP uses Cosine Embedding Loss (works with explicit pairs, no batch-size dependency, one-line PyTorch). NT-Xent (SimCLR-style) is more powerful but needs large batches for implicit negatives — with 3-10 calibration reps the batch is too small to leverage its advantage, and all batch items are the same exercise so "implicit negatives" are barely negative. Revisit when Fit3D pre-training provides real batch diversity (hundreds+ sequences across exercises).
