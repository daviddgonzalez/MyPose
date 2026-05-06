param(
    [Parameter(Mandatory = $true)]
    [string]$SourceUrl,

    [string]$BackendDir = "backend",
    [string]$DataDir = "backend/data/fit3d",
    [string]$TempDir = ".tmp_fit3d",
    [string]$ArchivePath = "",

    [switch]$OverwriteData,
    [switch]$RunPretrain,
    [int]$Epochs = 1,
    [string]$Device = "cpu",
    [string]$CheckpointDir = "checkpoints",
    [switch]$CleanupDataAfterPretrain,
    [switch]$KeepArchive
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$requiredExercises = @(
    "squat",
    "deadlift",
    "lunge",
    "push_up",
    "plank",
    "overhead_press",
    "barbell_biceps_curl"
)

function Resolve-GDriveDirectDownloadUrl {
    param([string]$Url)

    if ($Url -match "drive\.google\.com/file/d/([^/]+)/") {
        $fileId = $Matches[1]
        return "https://drive.google.com/uc?export=download&id=$fileId"
    }

    if ($Url -match "drive\.google\.com/open\?id=([^&]+)") {
        $fileId = $Matches[1]
        return "https://drive.google.com/uc?export=download&id=$fileId"
    }

    if ($Url -match "drive\.google\.com/uc\?") {
        return $Url
    }

    return $Url
}

function Download-Archive {
    param(
        [string]$Url,
        [string]$Destination
    )

    $directUrl = Resolve-GDriveDirectDownloadUrl -Url $Url
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession

    try {
        Invoke-WebRequest -Uri $directUrl -WebSession $session -OutFile $Destination
        return
    }
    catch {
        # Retry for large Google Drive files that require confirm token.
        if ($directUrl -notmatch "drive\.google\.com") {
            throw
        }
    }

    $first = Invoke-WebRequest -Uri $directUrl -WebSession $session
    $confirmToken = $null

    if ($first.Content -match "confirm=([0-9A-Za-z_]+)") {
        $confirmToken = $Matches[1]
    }

    if (-not $confirmToken) {
        throw "Google Drive download confirmation token not found. Ensure the file is shared for anyone with the link."
    }

    if ($directUrl -match "id=([^&]+)") {
        $fileId = $Matches[1]
    }
    else {
        throw "Could not parse Google Drive file id from URL."
    }

    $confirmedUrl = "https://drive.google.com/uc?export=download&confirm=$confirmToken&id=$fileId"
    Invoke-WebRequest -Uri $confirmedUrl -WebSession $session -OutFile $Destination
}

function Get-ExtractedFit3DRoot {
    param([string]$ExpandedRoot)

    # If archive expands to a single folder, descend once.
    $children = Get-ChildItem -LiteralPath $ExpandedRoot
    if ($children.Count -eq 1 -and $children[0].PSIsContainer) {
        return $children[0].FullName
    }
    return $ExpandedRoot
}

function Validate-Fit3DLayout {
    param([string]$Fit3DRoot)

    $missing = @()
    $totalNpy = 0

    foreach ($exercise in $requiredExercises) {
        $exerciseDir = Join-Path $Fit3DRoot $exercise
        if (-not (Test-Path -LiteralPath $exerciseDir -PathType Container)) {
            $missing += $exercise
            continue
        }

        $npyCount = (Get-ChildItem -LiteralPath $exerciseDir -Filter *.npy -File -ErrorAction SilentlyContinue).Count
        $totalNpy += $npyCount
    }

    if ($missing.Count -gt 0) {
        throw "Dataset layout invalid. Missing exercise folders: $($missing -join ', ')"
    }

    if ($totalNpy -eq 0) {
        throw "Dataset layout invalid. Found zero .npy files across required exercise folders."
    }

    Write-Host "Layout check passed. Total .npy files found: $totalNpy"
}

$repoRoot = (Get-Location).Path
$backendPath = Join-Path $repoRoot $BackendDir
$targetDataPath = Join-Path $repoRoot $DataDir
$tempRoot = Join-Path $repoRoot $TempDir

if (-not (Test-Path -LiteralPath $backendPath -PathType Container)) {
    throw "Backend directory not found: $backendPath"
}

if (-not (Test-Path -LiteralPath $tempRoot -PathType Container)) {
    New-Item -ItemType Directory -Path $tempRoot | Out-Null
}

if ([string]::IsNullOrWhiteSpace($ArchivePath)) {
    $archiveFile = Join-Path $tempRoot "fit3d_download.zip"
}
else {
    if ([System.IO.Path]::IsPathRooted($ArchivePath)) {
        $archiveFile = $ArchivePath
    }
    else {
        $archiveFile = Join-Path $repoRoot $ArchivePath
    }
}

if (-not (Test-Path -LiteralPath $archiveFile -PathType Leaf)) {
    Write-Host "Downloading archive from source URL..."
    Download-Archive -Url $SourceUrl -Destination $archiveFile
}
else {
    Write-Host "Using existing archive: $archiveFile"
}

$expandedRoot = Join-Path $tempRoot "expanded"
if (Test-Path -LiteralPath $expandedRoot) {
    Remove-Item -LiteralPath $expandedRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $expandedRoot | Out-Null

Write-Host "Extracting archive..."
Expand-Archive -LiteralPath $archiveFile -DestinationPath $expandedRoot -Force

$fit3dRoot = Get-ExtractedFit3DRoot -ExpandedRoot $expandedRoot
Validate-Fit3DLayout -Fit3DRoot $fit3dRoot

if (Test-Path -LiteralPath $targetDataPath) {
    if (-not $OverwriteData) {
        throw "Target data directory already exists: $targetDataPath. Re-run with -OverwriteData to replace it."
    }
    Remove-Item -LiteralPath $targetDataPath -Recurse -Force
}

$targetParent = Split-Path -Path $targetDataPath -Parent
if (-not (Test-Path -LiteralPath $targetParent -PathType Container)) {
    New-Item -ItemType Directory -Path $targetParent | Out-Null
}

Write-Host "Copying validated dataset into $targetDataPath ..."
Copy-Item -Path (Join-Path $fit3dRoot "*") -Destination $targetDataPath -Recurse -Force
Write-Host "Dataset ready."

if ($RunPretrain) {
    $venvPython = Join-Path $backendPath "venv/Scripts/python.exe"
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        throw "Python venv not found at $venvPython"
    }

    Write-Host "Running pretrain..."
    Push-Location $backendPath
    try {
        & $venvPython -m app.ml.training pretrain `
            --data-dir "data/fit3d" `
            --epochs $Epochs `
            --device $Device `
            --checkpoint-dir $CheckpointDir
    }
    finally {
        Pop-Location
    }

    $checkpointPath = Join-Path $backendPath "$CheckpointDir/pke_pretrained.pt"
    if (Test-Path -LiteralPath $checkpointPath -PathType Leaf) {
        Write-Host "Checkpoint generated: $checkpointPath"
    }
    else {
        Write-Warning "Pretrain finished but checkpoint not found at expected path: $checkpointPath"
    }

    if ($CleanupDataAfterPretrain) {
        Write-Host "Cleaning up local dataset copy..."
        Remove-Item -LiteralPath $targetDataPath -Recurse -Force
        Write-Host "Local dataset copy removed."
    }
}

if (-not $KeepArchive -and (Test-Path -LiteralPath $archiveFile -PathType Leaf)) {
    Remove-Item -LiteralPath $archiveFile -Force
}

if (Test-Path -LiteralPath $expandedRoot -PathType Container) {
    Remove-Item -LiteralPath $expandedRoot -Recurse -Force
}

Write-Host "Done."
Write-Host "Usage example:"
Write-Host ".\download_fit3d.ps1 -SourceUrl '<google-drive-share-link-or-direct-url>' -RunPretrain -Epochs 1 -Device cpu -OverwriteData"
