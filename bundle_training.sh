#!/usr/bin/env bash
#
# bundle_training.sh — build a transferable "train this model elsewhere" bundle.
#
# Lives at the repo root because the training bundle is a repo-wide artifact:
# it pulls from backend/ (code, checkpoints, requirements), cpp/ (optional
# extension) and the repo root itself (.env.example, requirements.txt,
# download_fit3d.*). backend/scripts/ is reserved for `python -m scripts.x`
# modules that must be run from backend/, which this is not.
#
# Default mode produces a small (tens of MB) tarball: code + checkpoints +
# configs + dependency manifests + a generated SETUP.md.
#
#   ./bundle_training.sh                       # code + checkpoints  -> dist/
#   ./bundle_training.sh --data-manifest       # + checksums & download recipe
#   ./bundle_training.sh --with-fit3d-joints   # + ~79 MB of fit3d joint JSON
#                                              #   (enough for a smoke test)
#   ./bundle_training.sh --dry-run             # show what would be included
#
set -eu

SCRIPT_PATH=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT="$SCRIPT_PATH"

# ─── Defaults ────────────────────────────────────────────────────────────
OUT_DIR="$REPO_ROOT/dist"
DATA_DIR="$REPO_ROOT/backend/data"
BUNDLE_NAME="mypose-train-$(date +%Y%m%d-%H%M%S)"
FORMAT="tar.gz"
WITH_FIT3D_JOINTS=0
FIT3D_ALL=0
DATA_MANIFEST=0
WITH_CHECKPOINTS=1
WITH_GIT=0
DO_CHECKSUM=1
DRY_RUN=0
KEEP_STAGE=0

usage() {
    cat <<'USAGE'
bundle_training.sh — build a transferable training bundle for the MyPose model.

Usage: ./bundle_training.sh [options]

  -o, --out DIR         Output directory                (default: ./dist)
  -n, --name NAME       Bundle name                     (default: mypose-train-<timestamp>)
      --format FMT      tar.gz | zip | dir              (default: tar.gz)
      --data-dir DIR    Where the fit3d archives live   (default: ./backend/data)

      --with-fit3d-joints    Include the ONLY part of fit3d the trainer reads:
                        the joints3d_25/*.json files the loader actually
                        indexes, in their original
                        fit3d_train/train/sXX/joints3d_25/ layout (~79 MB /
                        80 files). Good enough for a full end-to-end smoke
                        test on the target machine. The .tar.gz archives are
                        never bundled.
      --fit3d-all-exercises  As above but every exercise in joints3d_25/,
                        not just the ones dataset.py indexes (~441 MB).
      --data-manifest   Emit DATA_MANIFEST.txt: dataset provenance — sizes +
                        sha256 of the local fit3d archives, plus the CMU
                        download recipe.
      --no-checksum     Skip sha256 in --data-manifest (sha256 of 18 GB is slow).

      --no-checkpoints  Do not include backend/checkpoints/*.pt
      --with-git        Include the .git directory (off by default)

      --dry-run         Print the file list and exit; create nothing
      --keep-stage      Keep the staging directory after archiving
  -h, --help            This text

Excluded always: backend/venv, .venv, node_modules, frontend/, frontend/.next,
__pycache__, *.pyc, .pytest_cache, cpp/build, .env, *.log, and every
backend/data/*.tar.gz (the 20 GB fit3d archives are never bundled).
USAGE
}

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '  %s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }

# ─── Arg parsing ─────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        -o|--out)         OUT_DIR=$2; shift 2 ;;
        -n|--name)        BUNDLE_NAME=$2; shift 2 ;;
        --format)         FORMAT=$2; shift 2 ;;
        --data-dir)       DATA_DIR=$2; shift 2 ;;
        --with-fit3d-joints)   WITH_FIT3D_JOINTS=1; shift ;;
        --fit3d-all-exercises) WITH_FIT3D_JOINTS=1; FIT3D_ALL=1; shift ;;
        --with-data)      die "--with-data was removed: the fit3d .tar.gz archives are ~20 GB and ~98% of that is video/smplx the trainer never reads. Use --with-fit3d-joints (~79 MB) or let the target run scripts.download_cmu_mocap." ;;
        --data-manifest)  DATA_MANIFEST=1; shift ;;
        --no-checksum)    DO_CHECKSUM=0; shift ;;
        --no-checkpoints) WITH_CHECKPOINTS=0; shift ;;
        --with-git)       WITH_GIT=1; shift ;;
        --dry-run)        DRY_RUN=1; shift ;;
        --keep-stage)     KEEP_STAGE=1; shift ;;
        -h|--help)        usage; exit 0 ;;
        *)                usage >&2; die "unknown option: $1" ;;
    esac
done

case "$FORMAT" in
    tar.gz|zip|dir) ;;
    *) die "--format must be tar.gz, zip or dir (got: $FORMAT)" ;;
esac

[ -d "$REPO_ROOT/backend/app/ml" ] || die "not a MyPose checkout: $REPO_ROOT/backend/app/ml missing"

STAGE="$OUT_DIR/$BUNDLE_NAME"

# ─── What goes in ────────────────────────────────────────────────────────
# Paths are relative to the repo root. Everything training needs, nothing else.
INCLUDE_PATHS="
backend/app
backend/scripts
backend/tests
backend/pyproject.toml
backend/requirements.txt
backend/requirements-train.txt
backend/Dockerfile
cpp
requirements.txt
.env.example
.gitignore
README.md
download_fit3d.ps1
download_fit3d.sh
bundle_training.sh
"

TAR_EXCLUDES="
--exclude=__pycache__
--exclude=*.pyc
--exclude=*.pyo
--exclude=.pytest_cache
--exclude=.ruff_cache
--exclude=venv
--exclude=.venv
--exclude=node_modules
--exclude=.next
--exclude=build
--exclude=.env
--exclude=.env.local
--exclude=*.log
--exclude=*.egg-info
--exclude=.DS_Store
"

present_paths() {
    for p in $INCLUDE_PATHS; do
        [ -e "$REPO_ROOT/$p" ] && printf '%s\n' "$p"
    done
    if [ "$WITH_GIT" -eq 1 ] && [ -d "$REPO_ROOT/.git" ]; then
        printf '%s\n' ".git"
    fi
    if [ "$WITH_CHECKPOINTS" -eq 1 ] && [ -d "$REPO_ROOT/backend/checkpoints" ]; then
        printf '%s\n' "backend/checkpoints"
    fi
}

PATHS=$(present_paths)
[ -n "$PATHS" ] || die "nothing to bundle — include list resolved to zero paths"

if [ "$DRY_RUN" -eq 1 ]; then
    echo "Dry run — bundle would contain these top-level paths:"
    printf '%s\n' "$PATHS" | sed 's/^/    /'
    echo
    echo "Files (after exclusions):"
    # shellcheck disable=SC2086
    (cd "$REPO_ROOT" && tar cf - $TAR_EXCLUDES $PATHS 2>/dev/null | tar tf - ) \
        | grep -v '/$' | sed 's/^/    /'
    exit 0
fi

# ─── Stage ───────────────────────────────────────────────────────────────
echo "Bundling MyPose training environment"
info "repo:   $REPO_ROOT"
info "stage:  $STAGE"

rm -rf "$STAGE"
mkdir -p "$STAGE"

# shellcheck disable=SC2086
(cd "$REPO_ROOT" && tar cf - $TAR_EXCLUDES $PATHS) | tar xf - -C "$STAGE"

# Never ship a compiled extension built for the source machine.
rm -rf "$STAGE/cpp/build"
find "$STAGE" -name '*.so' -o -name '*.pyd' -o -name '*.dll' | while read -r f; do
    rm -f "$f"
done

# ─── Data ────────────────────────────────────────────────────────────────
# The fit3d .tar.gz archives are never bundled: ~20 GB of which the loader
# reads only the joints3d_25/*.json trees (videos/, smplx/, gpp/,
# camera_parameters/ and rep_ann.json are never opened — see
# app/ml/dataset.py:140-169 and _load_raw at :187).
DATA_NOTE="not included"
if [ "$WITH_FIT3D_JOINTS" -eq 1 ]; then
    # Which raw filenames the loader will actually index. Read straight out of
    # dataset.py's EXERCISE_ALIASES so this cannot drift.
    KEEP=$(sed -n '/^EXERCISE_ALIASES = {/,/^}/p' "$REPO_ROOT/backend/app/ml/dataset.py" \
           | sed -n 's/^ *"\([A-Za-z0-9_]*\)": *".*/\1/p')
    if [ -z "$KEEP" ]; then
        warn "could not parse EXERCISE_ALIASES from dataset.py; falling back to all exercises"
        FIT3D_ALL=1
    fi

    copied=0
    for split in fit3d_train/train fit3d_test/test train test; do
        [ -d "$DATA_DIR/$split" ] || continue
        for subj_dir in "$DATA_DIR/$split"/*/; do
            jd="${subj_dir}joints3d_25"
            [ -d "$jd" ] || continue
            rel="${jd#"$DATA_DIR"/}"
            dest="$STAGE/backend/data/$rel"
            mkdir -p "$dest"
            if [ "$FIT3D_ALL" -eq 1 ]; then
                for f in "$jd"/*.json; do
                    [ -f "$f" ] || continue
                    cp -f "$f" "$dest/"; copied=$((copied + 1))
                done
            else
                for name in $KEEP; do
                    [ -f "$jd/$name.json" ] || continue
                    cp -f "$jd/$name.json" "$dest/"; copied=$((copied + 1))
                done
            fi
        done
    done

    if [ "$copied" -eq 0 ]; then
        warn "--with-fit3d-joints: no joints3d_25/*.json found under $DATA_DIR"
        DATA_NOTE="fit3d joints requested but none found under $DATA_DIR"
    else
        DSIZE=$(du -sh "$STAGE/backend/data" | cut -f1)
        info "fit3d joints3d_25: $copied json files, $DSIZE"
        if [ "$FIT3D_ALL" -eq 1 ]; then
            DATA_NOTE="fit3d joints3d_25 (all exercises): $copied files, $DSIZE, under backend/data/"
        else
            DATA_NOTE="fit3d joints3d_25 (indexed exercises only): $copied files, $DSIZE, under backend/data/"
        fi
    fi
fi

if [ "$DATA_MANIFEST" -eq 1 ]; then
    MAN="$STAGE/DATA_MANIFEST.txt"
    {
        echo "MyPose fit3d data manifest"
        echo "generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
        echo "source host path: $DATA_DIR"
        echo
        printf '%-28s %14s  %s\n' "FILE" "BYTES" "SHA256"
    } > "$MAN"
    archives=$(find "$DATA_DIR" -maxdepth 1 -type f -name '*.tar.gz' 2>/dev/null | sort || true)
    if [ -z "$archives" ]; then
        echo "(no *.tar.gz found in $DATA_DIR at bundle time)" >> "$MAN"
        warn "--data-manifest: no archives found in $DATA_DIR"
    fi
    for a in $archives; do
        b=$(wc -c < "$a")
        if [ "$DO_CHECKSUM" -eq 1 ]; then
            info "sha256 $(basename "$a") (this can take several minutes) ..."
            sum=$(sha256sum "$a" | cut -d' ' -f1)
        else
            sum="(skipped: --no-checksum)"
        fi
        printf '%-28s %14s  %s\n' "$(basename "$a")" "$b" "$sum" >> "$MAN"
    done
    cat >> "$MAN" <<'MANEOF'

DATASET PROVENANCE
------------------
Recommended corpus: CMU Mocap — NOT listed above and NOT shipped, because the
target machine fetches it itself:
    cd backend && python -m scripts.download_cmu_mocap    # ~1.2 GB git clone
    source: https://github.com/una-dinosauria/cmu-mocap (cgspeed BVH conversion)
    integrity: ~2548 .bvh files, checked by the downloader.

The archives listed above are the legacy Fit3D corpus. Fit3D is not the
recommended training set (13 subjects; embeddings collapse onto subject style).

FIT3D RESTORE RECIPE (only if you actually need Fit3D)
-----------------------------------------------------
1. Get the archives onto the box, either by copying them from the source
   machine:
       rsync -aP <source>:<repo>/backend/data/fit3d_train.tar.gz backend/data/
       rsync -aP <source>:<repo>/backend/data/fit3d_test.tar.gz  backend/data/
   or by re-downloading from the Fit3D distribution URL you originally used
   (the project's download_fit3d.sh / download_fit3d.ps1 take --source-url).

2. Verify before trusting them:
       awk '$3 ~ /^[0-9a-f]{64}$/ {print $3"  backend/data/"$1}' DATA_MANIFEST.txt \
           | sha256sum -c -

3. Extract in place:
       ./download_fit3d.sh --archive backend/data/fit3d_train.tar.gz --dest backend/data --overwrite

   Expected layout afterwards (this is what app/ml/dataset.py indexes):
       backend/data/fit3d_train/train/s03/joints3d_25/*.json

   fit3d_test.tar.gz is not worth extracting for training: its subjects
   contain only camera_parameters/ and videos/ — no joints3d_25/ — so the
   loader indexes nothing from it.
MANEOF
    if [ "$WITH_FIT3D_JOINTS" -eq 1 ]; then
        DATA_NOTE="$DATA_NOTE; DATA_MANIFEST.txt records fit3d archive provenance"
    else
        DATA_NOTE="not included — see DATA_MANIFEST.txt for provenance + fetch recipes"
    fi
fi

# ─── Generated docs ──────────────────────────────────────────────────────
write_setup_md() {
    SETUP="$STAGE/SETUP.md"
    {
        echo "# MyPose — training on another machine"
        echo
        echo "Generated by \`bundle_training.sh\` on $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
        echo "from \`$REPO_ROOT\` (git: $(cd "$REPO_ROOT" && git rev-parse --short HEAD 2>/dev/null || echo 'n/a') on $(cd "$REPO_ROOT" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'n/a'))."
        echo
        echo "Dataset in this bundle: $DATA_NOTE"
        echo
    } > "$SETUP"

    cat >> "$SETUP" <<'MD'
## 0. What this is

Everything needed to pre-train the PKE model (ST-GCN backbone + projection
head, NT-Xent contrastive objective) away from the dev laptop. The web app,
the frontend and the Supabase layer are deliberately **not** here.

Two data paths, and you probably want both in this order:

1. **Smoke test — Fit3D joints** (section 4a). If this bundle was built with
   `--with-fit3d-joints` it already carries the ~79 MB of `joints3d_25/*.json`
   the loader actually reads (the 20 GB of video/smplx/gpp in the original
   archives is never opened). Nothing to download: you can prove the whole
   pipeline runs end to end in a couple of minutes.
2. **Real training — CMU Mocap** (section 4b). One command, ~1.2 GB.
   Fit3D has only ~13 subjects, and with that few the embeddings collapse onto
   subject style instead of motion structure — the exact failure this project
   exists to avoid (`app/ml/dataset_cmu.py:6`, `app/ml/dataset_ntu.py:6`).
   CMU's ~144 subjects / ~2,548 motions were added specifically to fix that.
   Train the checkpoint you actually intend to ship on CMU.

Layout:

    backend/app/ml/        training code (training.py is the entrypoint)
    backend/app/config.py  settings; reads .env, all values have safe defaults
    backend/scripts/       download_cmu_mocap.py, build_negatives_bank.py
    backend/checkpoints/   pre-existing .pt checkpoints (resume / compare)
    backend/requirements-train.txt  training-only dependency set
    cpp/                   optional pybind11 extension — NOT needed to train
    download_fit3d.sh      legacy Fit3D fetch/extract, bash (Linux/macOS/WSL)
    download_fit3d.ps1     legacy Fit3D fetch/extract, PowerShell (Windows)

## 1. Requirements

* Python >= 3.11 (verified on 3.12; `backend/pyproject.toml` sets
  `requires-python = ">=3.11"`).
* **`git` on PATH** — `scripts/download_cmu_mocap.py` shallow-clones the
  dataset with `git clone --depth 1` (`backend/scripts/download_cmu_mocap.py:99`).
* A CUDA-capable GPU is optional. Training runs on CPU by default.
* Disk: ~2 GB venv + ~1.2 GB for the CMU dataset.

## 2. Environment

```bash
cd <bundle>/backend
python3 -m venv venv
. venv/bin/activate            # Windows: venv\Scripts\activate
python -m pip install -U pip
```

### !! Install torch yourself, FIRST. Do not use requirements.txt for torch.

This is the single most expensive mistake available here. Both
`backend/requirements.txt:18-19` and the root `requirements.txt` carry

    --extra-index-url https://download.pytorch.org/whl/cpu
    torch>=2.2.0

which is right for the Railway deploy and wrong for a GPU box: it makes a
CPU-only wheel eligible, and that is what the dev machine ended up with
(`torch 2.11.0+cpu`). Nothing in the training code checks — `--device cuda`
would fail outright, and `--device cpu` would quietly train at a fraction of
the speed for as long as you let it.

```bash
# NVIDIA GPU box — pick the cu1xx matching your driver (nvidia-smi):
pip install torch --index-url https://download.pytorch.org/whl/cu124
# CPU-only box:
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

Then the rest (`requirements-train.txt` deliberately pins no index and no
torch build):

```bash
pip install -r requirements-train.txt
```

**Post-install check — do not skip:**

```bash
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
# GPU box must print something like: 2.6.0+cu124 True
# A '+cpu' build or 'False' means stop and reinstall torch before training.
```

`requirements-train.txt` is the slim, training-only set (torch, numpy,
pydantic-settings, bvh, pytest). `requirements.txt` is the full backend set
and additionally pulls FastAPI, uvicorn, supabase, opencv and mediapipe —
none of which any module under `app/ml/` imports. Use it only if you also
want to run the API on this box.

Rest of the install check:

```bash
python -c "import bvh; print('bvh ok')"        # needed by the CMU loader
python -m app.ml.training pretrain --help
```

## 3. Configuration

`app/config.py` reads `.env` (or `../.env`) but every setting has a default,
so **training works with no `.env` at all**. No `.env` is shipped in this
bundle on purpose — it holds Supabase keys and training never touches
Supabase. If you want to override something, copy the template:

```bash
cp ../.env.example ../.env    # then edit; MODEL_DEVICE / EMBEDDING_DIM matter here
```

Settings that affect training: `MODEL_DEVICE`, `EMBEDDING_DIM`,
`CHECKPOINT_DIR`, `SEQUENCE_LENGTH`, `TARGET_FPS`, `STGCN_CHANNELS`,
`PROJECTION_HIDDEN_DIM`. Note the CLI flags below override some of these;
`--device`/`--embedding-dim` do not read the env at all.

## 4. Data

**Put datasets on a native Linux disk (`~/datasets`, `/data`, ...), never on a
`/mnt/c`-style Windows mount.** Measured on the dev box, a cold read of one
sequence file off `/mnt/c` took up to 1446 ms versus ~69 ms warm; every clip is
re-read every epoch, so that difference is the whole training run. Same applies
to `--checkpoint-dir`.

### 4a. Fit3D joints — the fast smoke test (bundled, no download)

If this bundle carries `backend/data/fit3d_train/train/sXX/joints3d_25/*.json`
(check the "Dataset in this bundle" line at the top), you can validate the
whole pipeline before downloading anything:

```bash
cd <bundle>/backend
python -m app.ml.training pretrain \
    --dataset fit3d --data-dir data/fit3d_train \
    --epochs 1 --batch-size 4 --device cuda --checkpoint-dir /tmp/smoke
# expect: "Fit3D dataset loaded: 80 sequences across 6 exercises",
#         one epoch, then two .pt files in /tmp/smoke
```

That is ~80 clips from 8 subjects — enough to prove the environment, the GPU
and the checkpoint path all work, and useless as an actual training corpus.
Only the `joints3d_25/` JSON trees are shipped, in the exact layout
`app/ml/dataset.py:140-169` expects; `videos/`, `smplx/`, `gpp/`,
`camera_parameters/` and `rep_ann.json` are never read by any code path, and
the Fit3D *test* split contains no `joints3d_25/` at all, so it is not shipped
either.

### 4b. CMU Mocap — the corpus to actually train on

**Run this from the `backend/` directory.** `scripts` is resolved as a
top-level module relative to the current directory; from the bundle root you
get `ModuleNotFoundError: No module named 'scripts'` (verified).

```bash
cd <bundle>/backend
. venv/bin/activate
python -m scripts.download_cmu_mocap                       # -> ~/datasets/cmu-mocap
# or choose a location:
python -m scripts.download_cmu_mocap --dest /data/cmu-mocap
CMU_MOCAP_DIR=/data/cmu-mocap python -m scripts.download_cmu_mocap
```

What it does: `git clone --depth 1 https://github.com/una-dinosauria/cmu-mocap`
(~1.2 GB, the cgspeed Motionbuilder-friendly BVH conversion), then counts
`*.bvh` and warns if the total is more than 5% off `EXPECTED_BVH_COUNT = 2548`
(`scripts/download_cmu_mocap.py:29,83-105`). It is idempotent — it skips the
clone if the destination already holds BVH files; `--force` re-clones. It
deliberately clones **outside** the repo tree so the BVHs never reach git.

Layout: the downloader clones `data/<subject>/<motion>.bvh` and the loader
scans with `Path(data_dir).rglob("*.bvh")` (`app/ml/dataset_cmu.py:90`), so
any nesting works — pass the clone root as `--data-dir`, not `.../data`.

Sanity check before a long run (2-3 s, parses one BVH end to end):

```bash
cd <bundle>/backend
python -c "from app.ml.dataset_cmu import CMUContrastiveDataset as D; \
d = D('~/datasets/cmu-mocap'); print(len(d), 'clips'); print(tuple(d[0][0].shape))"
# expect: 2548 clips  /  (3, 64, 33)
```

### Optional: NTU RGB+D 120 (`--dataset ntu`) — scale-up, not turnkey

Requires **manual registration** with the ROSE Lab
(https://rose1.ntu.edu.sg/dataset/actionRecognition/) and a manual download;
there is no script for it. Unpack the `.skeleton` files into
`backend/data/ntu/nturgbd_skeletons/` and pass `--data-dir data`
(`app/ml/dataset_ntu.py:1-20,134`). 106 subjects, so it has the same
subject-diversity benefit as CMU at much greater setup cost.

### Optional: the full Fit3D archives — almost certainly not worth it

Only if you need the raw videos or the exercises `dataset.py` does not index.
The archives are ~20 GB, of which the trainer reads ~441 MB (all
`joints3d_25/`) or ~79 MB (the indexed exercises only). Extract with:

```bash
./download_fit3d.sh --archive backend/data/fit3d_train.tar.gz --dest backend/data --overwrite
```

If this bundle carries `DATA_MANIFEST.txt` it records the sizes and sha256 of
the archives on the source machine — use it to verify provenance of any copy
you receive.

**Trap:** `--dataset both` is **Fit3D + NTU only** — it does not include CMU
(`app/ml/training.py:52,63-67`). On a machine without Fit3D it fails
immediately with `No sequences found in ...`. Use `--dataset cmu`.

## 5. Train

All commands run from the `backend/` directory (the package root is `app`,
and the scripts are `python -m scripts.*`).

MD

    # ── the real, verified invocation ───────────────────────────────────
    cat >> "$SETUP" <<'MD'
```bash
cd <bundle>/backend
. venv/bin/activate
python -m app.ml.training pretrain \
    --dataset cmu \
    --data-dir ~/datasets/cmu-mocap \
    --epochs 50 \
    --batch-size 32 \
    --lr 1e-3 \
    --temperature 0.1 \
    --device cuda \
    --embedding-dim 256 \
    --checkpoint-dir checkpoints \
    --checkpoint-suffix _cmu
```

Use `--device cpu` if there is no GPU. Everything except `--data-dir` and
`--dataset` is optional; the CLI defaults are epochs=50, batch=16, lr=1e-3,
temperature=0.1, device=cpu, embedding-dim=256, **dataset=fit3d**,
checkpoint-dir=checkpoints (`app/ml/training.py:407-431`) — so `--dataset cmu`
must be passed explicitly.

`--batch-size 1` crashes in BatchNorm ("Expected more than 1 value per channel
when training"); use >= 2, and note `drop_last=True` discards the final partial
batch (`app/ml/training.py:124-130`).

Outputs, written to `--checkpoint-dir`:

* `pke_pretrained<suffix>.pt`       — best-loss checkpoint, rewritten whenever
                                      epoch average loss improves
* `pke_pretrained_final<suffix>.pt` — the last epoch, always written

Two-stage runs (pretrain on one corpus, continue on another) use
`--resume-from` plus `--checkpoint-suffix` so the files do not clobber
each other — e.g. CMU for general motion structure, then NTU if you have it:

```bash
python -m app.ml.training pretrain --dataset cmu --data-dir ~/datasets/cmu-mocap \
    --epochs 50 --batch-size 32 --device cuda --checkpoint-suffix _cmu
python -m app.ml.training pretrain --dataset ntu --data-dir data \
    --epochs 30 --device cuda --checkpoint-suffix _ntu \
    --resume-from checkpoints/pke_pretrained_cmu.pt
```

Long runs: `nohup ... > train.log 2>&1 &` or tmux. There is no
checkpoint-resume-on-crash beyond `--resume-from`, and no validation split
or metric logging in the loop — only the training loss is reported.

## 6. Negatives bank (needed by the calibration finetune)

Heads-up: `scripts/build_negatives_bank.py` is **Fit3D-only** — it constructs
a `Fit3DContrastiveDataset` directly (`scripts/build_negatives_bank.py:33`)
and has no CMU/NTU path, so on a machine without Fit3D it cannot run. Either
build the bank back on the machine that has Fit3D (it only needs the trained
checkpoint, not a GPU), or extend the script. For reference:

```bash
cd backend
python -m scripts.build_negatives_bank \
    --checkpoint checkpoints/pke_pretrained_cmu.pt \
    --data-dir data/fit3d_train \
    --out checkpoints/negatives_bank.npy \
    --count 50 \
    --exclude squat \
    --device cpu
```

## 7. Optional: the C++ extension

`cpp/` builds `pke_cpp` (banded DTW + joint angles). **Training does not use
it** — `app/ml/dtw_fallback.py` is imported only by
`app/api/routes_evaluate.py`, which is the serving path. Build it only if you
also want to run the API or `tests/test_cpp_module.py`:

```bash
pip install pybind11 cmake
cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build cpp/build --config Release
```

Put the resulting `pke_cpp*.so` on `PYTHONPATH`.

## 8. Getting results back

```bash
rsync -aP <gpu-box>:<bundle>/backend/checkpoints/*.pt ./backend/checkpoints/
```

A checkpoint is ~4.5 MB. Drop it in `backend/checkpoints/` on the app machine.
`app/config.py` loads `checkpoint_dir/checkpoint_file`, i.e.
`checkpoints/pke_pretrained.pt` by default — so a run with
`--checkpoint-suffix _cmu` produces `pke_pretrained_cmu.pt`, which the app will
**not** pick up until you rename it or set `CHECKPOINT_FILE=pke_pretrained_cmu.pt`
in `.env`.

## 9. Known rough edges

* `DataLoader(num_workers=0)` is hardcoded "for Windows compatibility"
  (`app/ml/training.py:128`). On a Linux GPU box this makes data loading
  single-threaded and will bottleneck the GPU. Raising it is a one-line change.
* `pretrain()` accepts `weight_decay`, `sequence_length` and `log_interval`,
  but the CLI does not expose them (`app/ml/training.py:410-431`). Edit the
  call or add the flags if you need them.
* `--device cuda` is passed straight to `.to(device)`; there is no
  availability check and no AMP/`torch.compile`. A wrong `--device` fails at
  the first tensor move.
* `--dataset both` means Fit3D + NTU, never CMU (`app/ml/training.py:63-67`).
* CMU clips are parsed from BVH and forward-kinematic'd **per `__getitem__`**
  (`app/ml/dataset_cmu.py:120-131`) — that is CPU-heavy, several hundred ms per
  clip, and with `num_workers=0` it will dominate wall-clock on a GPU box.
  Raising `num_workers` is the single highest-value change before a long CMU run.
* A failed CMU clip recurses into `self.__getitem__(idx + 1)`
  (`app/ml/dataset_cmu.py:110,113`); a systematically broken corpus would
  recurse until Python's recursion limit rather than fail cleanly.
* The Fit3D tree yields only ~80 sequences across 6 exercises (no `plank`),
  which is why CMU is the recommended corpus.
MD
}

write_setup_md

# ─── Manifest + secret scan ──────────────────────────────────────────────
MANIFEST="$STAGE/MANIFEST.txt"
(cd "$STAGE" && find . -type f | sed 's|^\./||' | sort) > "$MANIFEST"
FILE_COUNT=$(wc -l < "$MANIFEST" | tr -d ' ')

echo
echo "Scanning bundle for secrets and junk ..."
LEAKS=0
while read -r rel; do
    case "$rel" in
        .env|*/.env|.env.local|*/.env.local)
            warn "env file in bundle: $rel"; LEAKS=1 ;;
        *venv/*|*/node_modules/*|*/.next/*|*__pycache__*|*.pyc|*.log)
            warn "excluded-class file leaked in: $rel"; LEAKS=1 ;;
        *.pem|*.key|*id_rsa*)
            warn "possible credential file: $rel"; LEAKS=1 ;;
    esac
done < "$MANIFEST"

# Content scan of text files: JWTs, private keys, obvious API tokens.
CONTENT_HITS=$(cd "$STAGE" && grep -rIlE \
    '(eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,})|(-----BEGIN [A-Z ]*PRIVATE KEY-----)|(sk-[A-Za-z0-9]{32,})|(ghp_[A-Za-z0-9]{30,})' \
    . 2>/dev/null || true)
if [ -n "$CONTENT_HITS" ]; then
    warn "possible secret material inside these files:"
    printf '%s\n' "$CONTENT_HITS" | sed 's/^/    /' >&2
    LEAKS=1
fi

if [ "$LEAKS" -eq 1 ]; then
    warn "bundle kept at $STAGE so you can inspect it, but DO NOT SHIP IT AS IS."
else
    info "clean — no .env, venv, node_modules, __pycache__, logs or key material"
fi

# ─── Package ─────────────────────────────────────────────────────────────
echo
STAGE_SIZE=$(du -sh "$STAGE" | cut -f1)
case "$FORMAT" in
    tar.gz)
        ARTIFACT="$OUT_DIR/$BUNDLE_NAME.tar.gz"
        (cd "$OUT_DIR" && tar czf "$BUNDLE_NAME.tar.gz" "$BUNDLE_NAME")
        [ "$KEEP_STAGE" -eq 1 ] || rm -rf "$STAGE"
        ;;
    zip)
        ARTIFACT="$OUT_DIR/$BUNDLE_NAME.zip"
        command -v zip >/dev/null 2>&1 || die "zip not installed; use --format tar.gz"
        (cd "$OUT_DIR" && zip -qr "$BUNDLE_NAME.zip" "$BUNDLE_NAME")
        [ "$KEEP_STAGE" -eq 1 ] || rm -rf "$STAGE"
        ;;
    dir)
        ARTIFACT="$STAGE"
        ;;
esac

ART_SIZE=$(du -sh "$ARTIFACT" | cut -f1)

echo "Bundle ready"
info "artifact:    $ARTIFACT"
info "size:        $ART_SIZE (staged tree: $STAGE_SIZE)"
info "files:       $FILE_COUNT"
info "data:        $DATA_NOTE"
info "next:        read SETUP.md inside the bundle"
echo
case "$FORMAT" in
    dir) echo "  Transfer with:  rsync -aP '$ARTIFACT' user@gpu-box:~/" ;;
    *)   echo "  Transfer with:  scp '$ARTIFACT' user@gpu-box:~/" ;;
esac
