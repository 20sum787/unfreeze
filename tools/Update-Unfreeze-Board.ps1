# Run from Windows PowerShell. The board must already contain the full camera app.
param([string]$BoardAddress = "10.105.16.241", [switch]$RetryLink)
$ErrorActionPreference = "Stop"
$archive = Get-Item -LiteralPath (Join-Path $PSScriptRoot "../dist/Unfreeze-UNO-Q-AppLab.zip")
$sha = (Get-FileHash -LiteralPath $archive.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$remote = "arduino@$BoardAddress"
$upload = "unfreeze-update-$sha.zip"
if (-not $RetryLink) {
    & scp $archive.FullName "${remote}:$upload"
    if ($LASTEXITCODE -ne 0) { throw "Upload failed. The running application has not been stopped." }
}

$script = @'
set -eu
umask 077
cd "$HOME"
archive="unfreeze-update-SHA.zip"
printf '%s  %s\n' 'SHA' "$archive" | sha256sum -c -
app="$HOME/ArduinoApps/unfreeze-uno-q"
test -f "$app/app.yaml" && test -f "$app/models/door-v6.eim" || { echo "Expected the installed full camera app at $app"; exit 1; }
if [ 'RETRY_MODE' = 'yes' ]; then
python3 - "$archive" "$app" <<'PY'
from pathlib import Path
import hashlib, re, sys, tempfile, zipfile
archive, app = map(Path, sys.argv[1:])
prefix = "unfreeze-uno-q/sketch/"
with zipfile.ZipFile(archive) as package:
    for name in package.namelist():
        if not name.startswith(prefix) or name.endswith("/"):
            continue
        path = app / name.removeprefix("unfreeze-uno-q/")
        if not path.is_file() or path.read_bytes() != package.read(name):
            sys.exit(f"Installed source differs from ZIP: {path}. Run the updater without -RetryLink.")
ino = (app / "sketch/sketch.ino").read_bytes()
for symbol in (b"setup", b"loop"):
    if not re.search(rb"(?m)^void " + symbol + rb"\s*\(\s*\)\s*\{", ino):
        sys.exit("Missing entry point in installed sketch")
print("Verified sketch.ino:", len(ino), "bytes; sha256", hashlib.sha256(ino).hexdigest(), flush=True)
cache = app / ".cache/sketch"
if cache.is_dir() and not cache.is_symlink():
    backup = Path(tempfile.mkdtemp(prefix="link-recovery-", dir=cache.parent)) / "sketch"
    cache.rename(backup)
    print("Previous build cache saved:", backup, flush=True)
PY
else
python3 - "$archive" "$app" <<'PY'
from pathlib import Path
import os, shutil, subprocess, sys, tempfile, time, zipfile
archive, app = map(Path, sys.argv[1:])
with tempfile.TemporaryDirectory() as temp, zipfile.ZipFile(archive) as z:
    for entry in z.namelist():
        if entry.startswith(("unfreeze-uno-q/python/", "unfreeze-uno-q/sketch/")):
            z.extract(entry, temp)
    src = Path(temp) / "unfreeze-uno-q"
    if "freeze-pulse-alarm-v3" not in (src/"python/companion.py").read_text() or not (src/"sketch/sketch.ino").is_file():
        sys.exit("Unexpected package version")
    backup = Path.home() / time.strftime("unfreeze-code-%Y%m%d-%H%M%S.tar.gz")
    subprocess.run(["tar", "-C", str(app), "-czf", str(backup), "python", "sketch"], check=True)
    print("Backup:", backup, flush=True)
    subprocess.run(["arduino-app-cli","app","stop","user:unfreeze-uno-q"], check=True)
    os.umask(0o022)
    for file in src.rglob("*"):
        if file.is_file():
            target = app / file.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, target)
PY
fi
umask 022
if ! arduino-app-cli app start user:unfreeze-uno-q; then
    echo "Sketch diagnostics after failed start:"
    grep -nE '^void (setup|loop)\(' "$app/sketch/sketch.ino" || true
    gen="$app/.cache/sketch/sketch/sketch.ino.cpp"
    ls -l "$gen" "$gen.o" || true
    grep -nE '^void (setup|loop)\(' "$gen" || true
    nmtool=$(find "$HOME/.arduino15/internal" -name arm-zephyr-eabi-nm -type f -print -quit)
    if [ -n "$nmtool" ] && [ -f "$gen.o" ]; then
        "$nmtool" -g --defined-only "$gen.o" | grep -E 'setup|loop' || echo "No entry-point symbols in sketch object"
    fi
    exit 1
fi
python3 - <<'PY'
import json, time, urllib.request
for attempt in range(90):
    try:
        with urllib.request.urlopen("http://127.0.0.1:7000/v1/build", timeout=2) as r:
            state = json.load(r)
        if state.get("appBuild") == "freeze-pulse-alarm-v3" and state.get("mcuFreezeHoldMs") == 5000 and state.get("mcuCueRevision") == 3:
            print("Verified:", state)
            break
    except (OSError, ValueError):
        pass
    time.sleep(1)
else:
    raise SystemExit("Update not verified. Check App Lab logs and /v1/build.")
PY
'@
# Pass the script as Base64 so SSH receives the same bytes in Windows PowerShell and pwsh.
$mode = if ($RetryLink) { "yes" } else { "no" }
$body = $script.Replace("SHA", $sha).Replace("RETRY_MODE", $mode).Replace("`r", "")
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($body))
& ssh -t $remote "echo $encoded | base64 -d | bash"
if ($LASTEXITCODE -ne 0) { throw "Board update did not finish. Check the output above." }
