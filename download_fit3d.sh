#!/usr/bin/env bash
#
# download_fit3d.sh — bash port of download_fit3d.ps1.
#
# Fetch and/or extract the Fit3D dataset on Linux/macOS/WSL, validate the
# resulting layout against what backend/app/ml/dataset.py can actually index,
# and optionally kick off a pretrain run.
#
# Differences from the PowerShell original, on purpose:
#   * handles .tar.gz / .tgz / .tar as well as .zip (our archives are .tar.gz;
#     the PS1 only calls Expand-Archive and cannot read them),
#   * accepts BOTH dataset layouts — the preprocessed <exercise>/*.npy tree the
#     PS1 validated, and the raw fit3d_train/train/<subject>/joints3d_25/*.json
#     tree the real Fit3D archives actually contain,
#   * extracts in place under --dest instead of copying a second full copy,
#   * uses the venv python at backend/venv/bin/python, or --python.
#
# Examples:
#   ./download_fit3d.sh --archive backend/data/fit3d_train.tar.gz --dest backend/data --overwrite
#   ./download_fit3d.sh --source-url 'https://.../fit3d_train.tar.gz' --dest backend/data
#   ./download_fit3d.sh --archive backend/data/fit3d_train.tar.gz --run-pretrain --epochs 1 --device cpu
#
set -eu

SCRIPT_PATH=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT="$SCRIPT_PATH"

SOURCE_URL=""
ARCHIVE=""
DEST="$REPO_ROOT/backend/data"
BACKEND_DIR="$REPO_ROOT/backend"
TMP_DIR="$REPO_ROOT/.tmp_fit3d"
OVERWRITE=0
RUN_PRETRAIN=0
EPOCHS=1
DEVICE="cpu"
CHECKPOINT_DIR="checkpoints"
KEEP_ARCHIVE=1
CLEANUP_DATA=0
PYTHON_BIN=""
DATASET_SUBDIR=""

usage() {
    cat <<'USAGE'
download_fit3d.sh — fetch/extract Fit3D and (optionally) pretrain.

  --source-url URL     Download from URL (http(s) or a Google Drive share link)
  --archive PATH       Use an archive already on disk (.tar.gz/.tgz/.tar/.zip)
  --dest DIR           Extraction root            (default: ./backend/data)
  --subdir NAME        Extract into DIR/NAME instead of DIR
  --overwrite          Replace an existing extraction target
  --keep-archive       Keep a downloaded archive   (default: keep)
  --delete-archive     Delete the archive after a successful extract
  --run-pretrain       Run a pretrain after extraction
  --epochs N           Pretrain epochs             (default: 1)
  --device DEV         cpu | cuda                  (default: cpu)
  --checkpoint-dir D   Relative to backend/        (default: checkpoints)
  --cleanup-data       Delete the extracted dataset after pretrain
  --python PATH        Python to use for pretrain  (default: backend/venv/bin/python,
                       else backend/venv/Scripts/python.exe, else python3)
  -h, --help
USAGE
}

die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '  %s\n' "$*"; }

while [ $# -gt 0 ]; do
    case "$1" in
        --source-url)     SOURCE_URL=$2; shift 2 ;;
        --archive)        ARCHIVE=$2; shift 2 ;;
        --dest)           DEST=$2; shift 2 ;;
        --subdir)         DATASET_SUBDIR=$2; shift 2 ;;
        --overwrite)      OVERWRITE=1; shift ;;
        --keep-archive)   KEEP_ARCHIVE=1; shift ;;
        --delete-archive) KEEP_ARCHIVE=0; shift ;;
        --run-pretrain)   RUN_PRETRAIN=1; shift ;;
        --epochs)         EPOCHS=$2; shift 2 ;;
        --device)         DEVICE=$2; shift 2 ;;
        --checkpoint-dir) CHECKPOINT_DIR=$2; shift 2 ;;
        --cleanup-data)   CLEANUP_DATA=1; shift ;;
        --python)         PYTHON_BIN=$2; shift 2 ;;
        -h|--help)        usage; exit 0 ;;
        *)                usage >&2; die "unknown option: $1" ;;
    esac
done

[ -n "$SOURCE_URL" ] || [ -n "$ARCHIVE" ] || { usage >&2; die "need --source-url or --archive"; }
[ -d "$BACKEND_DIR" ] || die "backend directory not found: $BACKEND_DIR"

case "$DEST" in /*) ;; *) DEST="$REPO_ROOT/$DEST" ;; esac
mkdir -p "$DEST" "$TMP_DIR"

# ─── Download ────────────────────────────────────────────────────────────
gdrive_id() {
    # Echo the file id for a Google Drive link, or nothing.
    printf '%s' "$1" | sed -n \
        -e 's|.*drive\.google\.com/file/d/\([^/]*\)/.*|\1|p' \
        -e 's|.*drive\.google\.com/open?id=\([^&]*\).*|\1|p' \
        -e 's|.*drive\.google\.com/uc?.*id=\([^&]*\).*|\1|p'
}

download() {
    url=$1; dest=$2
    fid=$(gdrive_id "$url")
    if [ -n "$fid" ]; then
        if command -v gdown >/dev/null 2>&1; then
            info "google drive file $fid — using gdown"
            gdown --id "$fid" -O "$dest"
            return
        fi
        info "google drive file $fid — using curl + confirm token"
        cookie="$TMP_DIR/gdrive.cookie"
        curl -sL -c "$cookie" "https://drive.google.com/uc?export=download&id=$fid" -o "$TMP_DIR/gdrive.html"
        token=$(sed -n 's/.*confirm=\([0-9A-Za-z_-]*\).*/\1/p' "$TMP_DIR/gdrive.html" | head -1)
        if [ -z "$token" ]; then
            token=$(sed -n 's/.*download_warning[^\t]*\t\([^\t]*\)$/\1/p' "$cookie" | head -1)
        fi
        [ -n "$token" ] || die "no Google Drive confirm token; is the file shared with 'anyone with the link'? (pip install gdown is the reliable path)"
        curl -L -b "$cookie" \
            "https://drive.google.com/uc?export=download&confirm=$token&id=$fid" -o "$dest"
        return
    fi

    if command -v curl >/dev/null 2>&1; then
        curl -fL --progress-bar "$url" -o "$dest"
    elif command -v wget >/dev/null 2>&1; then
        wget -O "$dest" "$url"
    else
        die "neither curl nor wget is installed"
    fi
}

if [ -z "$ARCHIVE" ]; then
    base=$(printf '%s' "$SOURCE_URL" | sed 's/[?#].*//' | sed 's|.*/||')
    case "$base" in *.tar.gz|*.tgz|*.tar|*.zip) ;; *) base="fit3d_download.tar.gz" ;; esac
    ARCHIVE="$TMP_DIR/$base"
    if [ -f "$ARCHIVE" ]; then
        info "using cached download: $ARCHIVE"
    else
        info "downloading -> $ARCHIVE"
        download "$SOURCE_URL" "$ARCHIVE"
    fi
else
    case "$ARCHIVE" in /*) ;; *) ARCHIVE="$REPO_ROOT/$ARCHIVE" ;; esac
    [ -f "$ARCHIVE" ] || die "archive not found: $ARCHIVE"
    info "using archive: $ARCHIVE"
fi

# ─── Extract ─────────────────────────────────────────────────────────────
TARGET="$DEST"
[ -n "$DATASET_SUBDIR" ] && TARGET="$DEST/$DATASET_SUBDIR"

# What top-level entry will the archive create?
top_entry() {
    case "$ARCHIVE" in
        *.tar.gz|*.tgz) tar tzf "$ARCHIVE" | head -1 | cut -d/ -f1 ;;
        *.tar)          tar tf  "$ARCHIVE" | head -1 | cut -d/ -f1 ;;
        *.zip)          unzip -Z1 "$ARCHIVE" | head -1 | cut -d/ -f1 ;;
    esac
}

info "inspecting archive ..."
TOP=$(top_entry)
[ -n "$TOP" ] || die "archive appears empty or unreadable: $ARCHIVE"
info "top-level entry: $TOP"

EXTRACTED="$TARGET/$TOP"
if [ -e "$EXTRACTED" ]; then
    if [ "$OVERWRITE" -eq 1 ]; then
        info "removing existing $EXTRACTED (--overwrite)"
        rm -rf "$EXTRACTED"
    else
        die "target already exists: $EXTRACTED — re-run with --overwrite"
    fi
fi

mkdir -p "$TARGET"
info "extracting into $TARGET (this takes a while for the 18 GB train split) ..."
case "$ARCHIVE" in
    *.tar.gz|*.tgz) tar xzf "$ARCHIVE" -C "$TARGET" ;;
    *.tar)          tar xf  "$ARCHIVE" -C "$TARGET" ;;
    *.zip)          command -v unzip >/dev/null 2>&1 || die "unzip not installed"
                    unzip -q "$ARCHIVE" -d "$TARGET" ;;
    *)              die "unsupported archive type: $ARCHIVE" ;;
esac

# ─── Validate ────────────────────────────────────────────────────────────
# Mirrors app/ml/dataset.py: preprocessed <exercise>/*.npy first, then the raw
# {fit3d_train/train,fit3d_test/test,train,test}/<subject>/joints3d_25/*.json.
EXERCISES="squat deadlift lunge push_up plank overhead_press barbell_biceps_curl"

validate() {
    root=$1
    npy=0
    for ex in $EXERCISES; do
        if [ -d "$root/$ex" ]; then
            n=$(find "$root/$ex" -maxdepth 1 -name '*.npy' | wc -l)
            npy=$((npy + n))
        fi
    done
    if [ "$npy" -gt 0 ]; then
        info "layout OK — preprocessed: $npy .npy files"
        return 0
    fi

    for sub in fit3d_train/train fit3d_test/test train test .; do
        [ -d "$root/$sub" ] || continue
        j=$(find "$root/$sub" -mindepth 3 -maxdepth 3 -path '*/joints3d_25/*.json' 2>/dev/null | wc -l)
        if [ "$j" -gt 0 ]; then
            subj=$(find "$root/$sub" -mindepth 1 -maxdepth 1 -type d | wc -l)
            info "layout OK — raw Fit3D under $sub: $subj subjects, $j joints3d_25 json files"
            return 0
        fi
    done

    return 1
}

if validate "$TARGET"; then
    :
elif validate "$EXTRACTED"; then
    :
else
    die "extraction finished but neither layout was found under $TARGET.
     Expected either <exercise>/*.npy or <split>/<subject>/joints3d_25/*.json
     (see backend/app/ml/dataset.py:104-169)."
fi

info "dataset ready at $TARGET"

if [ "$KEEP_ARCHIVE" -eq 0 ] && [ -f "$ARCHIVE" ]; then
    info "removing archive $ARCHIVE (--delete-archive)"
    rm -f "$ARCHIVE"
fi

# ─── Optional pretrain ───────────────────────────────────────────────────
if [ "$RUN_PRETRAIN" -eq 1 ]; then
    if [ -z "$PYTHON_BIN" ]; then
        if [ -x "$BACKEND_DIR/venv/bin/python" ]; then
            PYTHON_BIN="$BACKEND_DIR/venv/bin/python"
        elif [ -x "$BACKEND_DIR/venv/Scripts/python.exe" ]; then
            PYTHON_BIN="$BACKEND_DIR/venv/Scripts/python.exe"
        else
            PYTHON_BIN=$(command -v python3 || command -v python || true)
        fi
    fi
    [ -n "$PYTHON_BIN" ] || die "no python found; pass --python"

    # training.py wants the directory that CONTAINS train/ (or fit3d_train/).
    DATA_ARG="$TARGET"
    if [ -d "$EXTRACTED/train" ] || [ -d "$EXTRACTED/test" ]; then
        DATA_ARG="$EXTRACTED"
    fi

    info "pretraining with $PYTHON_BIN (--data-dir $DATA_ARG)"
    ( cd "$BACKEND_DIR" && "$PYTHON_BIN" -m app.ml.training pretrain \
        --data-dir "$DATA_ARG" \
        --dataset fit3d \
        --epochs "$EPOCHS" \
        --device "$DEVICE" \
        --checkpoint-dir "$CHECKPOINT_DIR" )

    case "$CHECKPOINT_DIR" in
        /*) CKPT="$CHECKPOINT_DIR/pke_pretrained.pt" ;;
        *)  CKPT="$BACKEND_DIR/$CHECKPOINT_DIR/pke_pretrained.pt" ;;
    esac
    if [ -f "$CKPT" ]; then
        info "checkpoint: $CKPT"
    else
        printf 'WARNING: pretrain finished but %s is missing\n' "$CKPT" >&2
    fi

    if [ "$CLEANUP_DATA" -eq 1 ]; then
        info "removing extracted dataset $EXTRACTED (--cleanup-data)"
        rm -rf "$EXTRACTED"
    fi
fi

rmdir "$TMP_DIR" 2>/dev/null || true
echo "Done."
