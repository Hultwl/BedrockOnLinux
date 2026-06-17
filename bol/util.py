"""bol.util — small shared helpers: run, settings, HTTP, downloads, GitHub, screen/proc."""
# SPDX-License-Identifier: MIT

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .config import (
    APP,
    CACHE,
    DATA,
    GAMES,
    LOGS,
    PROTON_DIR,
    SETTINGS,
    UMU_DIR,
    WINEGDK_BRANCH,
    WINEGDK_REPO,
)
from .log import IS_TTY, die

def run(cmd, **kw):
    kw.setdefault("check", True)
    return subprocess.run(cmd, **kw)


def mkdirs():
    for d in (DATA, PROTON_DIR, UMU_DIR, CACHE, LOGS, GAMES):
        d.mkdir(parents=True, exist_ok=True)


def load_settings():
    s = {}
    if SETTINGS.exists():
        try:
            s = json.loads(SETTINGS.read_text())
        except Exception:
            s = {}
    # Always use the WineGDK engine unless the user pointed at a custom build.
    s.setdefault("native_login", True)
    if not s.get("proton_dir") and not s.get("proton_url"):
        s.setdefault("proton_source", "winegdk")
        s.setdefault("winegdk_repo", WINEGDK_REPO)
        s.setdefault("winegdk_branch", WINEGDK_BRANCH)
        # A stale persisted repo/branch is repointed and forces a clean rebuild.
        if s.get("winegdk_repo") != WINEGDK_REPO \
                or s.get("winegdk_branch") != WINEGDK_BRANCH:
            s["winegdk_repo"] = WINEGDK_REPO
            s["winegdk_branch"] = WINEGDK_BRANCH
            s.pop("winegdk_built", None)
    return s


def save_settings(s):
    DATA.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(s, indent=2))


def http_json(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": APP, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def http_post_form(url, fields):
    """POST application/x-www-form-urlencoded → parsed JSON. OAuth endpoints
    return their error payload with a 4xx, so decode the body either way."""
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"User-Agent": APP, "Accept": "application/json",
                 "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            raise


def download(url, dest: Path, label=None, progress=None):
    label = label or dest.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": APP})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            total = int(r.headers.get("Content-Length", 0))
            got = 0
            last = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if progress and total:
                        progress(got, total)
                    if IS_TTY and total and got - last > (1 << 21):
                        last = got
                        print(f"\r{':: '}{label}: {got*100//total:3d}% "
                              f"({got>>20}/{total>>20} MiB)", end="", flush=True)
        if IS_TTY:
            print()
    except urllib.error.URLError as e:
        die(f"Download failed: {url}\n{e}")
    tmp.replace(dest)
    return dest


def gh_latest(repo):
    return http_json(f"https://api.github.com/repos/{repo}/releases/latest")


def gh_releases(repo, per_page=50):
    return http_json(
        f"https://api.github.com/repos/{repo}/releases?per_page={per_page}")


def asset_url(release, predicate):
    for a in release.get("assets", []):
        if predicate(a["name"]):
            return a["browser_download_url"], a["name"], a.get("size", 0)
    return None, None, 0


def _screen_wh():
    """Primary screen WxH from xrandr (for gamescope sizing), or None."""
    if not shutil.which("xrandr"):
        return None
    try:
        out = subprocess.run(["xrandr"], capture_output=True, text=True,
                             timeout=5).stdout
    except Exception:
        return None
    m = re.search(r"current\s+(\d+)\s+x\s+(\d+)", out)
    return (m.group(1), m.group(2)) if m else None


def _pkill(pattern):
    """Best-effort kill of processes whose cmdline matches `pattern`."""
    if shutil.which("pkill"):
        subprocess.run(["pkill", "-9", "-f", pattern],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            cl = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ")
            if pattern.encode() in cl:
                os.kill(int(pid), 9)
        except Exception:
            pass
