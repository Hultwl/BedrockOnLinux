"""bol.deps — runtime bootstrap of the non-stdlib Python deps login needs."""
# SPDX-License-Identifier: MIT
import importlib
import importlib.util
import os
import site
import subprocess
import sys

from .log import info, ok, warn

# Non-stdlib modules the native Microsoft login needs. `cryptography` signs the
# Xbox Live device/request tokens (ES256); without it xbl_preauth bails and the
# in-game login fails with a connection-reset (0x80072746). `requests` was
# dropped in favour of urllib, so cryptography is the only hard dependency.
#   import-name -> pip distribution name
LOGIN_DEPS = {"cryptography": "cryptography"}


def have(mod):
    """True if `mod` can be imported in this interpreter."""
    try:
        return importlib.util.find_spec(mod) is not None
    except Exception:
        return False


def missing_login_deps():
    """Import-names of the login deps that are not currently importable."""
    return [m for m in LOGIN_DEPS if not have(m)]


def _refresh_path():
    """Make a fresh `pip install --user` visible to the running interpreter."""
    try:
        usersite = site.getusersitepackages()
        if usersite and usersite not in sys.path:
            site.addsitedir(usersite)
    except Exception:
        pass
    importlib.invalidate_caches()


def _pip_install(pkgs):
    """Best-effort `pip install` of `pkgs`. Tries a normal --user install, then
    retries with --break-system-packages for PEP 668 'externally managed'
    distros (Debian/Ubuntu 24.04, Fedora, …). Returns True on success."""
    if not have("pip") and importlib.util.find_spec("pip") is None:
        return False
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    base = [sys.executable, "-m", "pip", "install", "--upgrade", "--quiet"]
    if not in_venv:                       # --user is invalid inside a venv
        base.append("--user")
    for extra in ([], ["--break-system-packages"]):
        try:
            subprocess.run(base + extra + list(pkgs),
                           check=True, stdout=subprocess.DEVNULL)
            return True
        except Exception:
            continue
    return False


def ensure_login_deps(install=True):
    """Ensure the login deps are importable. When `install` is set and some are
    missing, try to pip-install them. Returns the list of import-names still
    missing afterwards (empty == all good). Never raises."""
    missing = missing_login_deps()
    if not missing or not install:
        return missing
    if os.environ.get("BOL_NO_PIP") == "1":
        return missing
    info(f"Installing Python dependencies for login: {', '.join(missing)} …")
    if _pip_install(LOGIN_DEPS[m] for m in missing):
        _refresh_path()
        missing = missing_login_deps()
    if missing:
        warn("Could not auto-install Python deps "
             f"({', '.join(missing)}). Install them with your package manager "
             f"(e.g. 'sudo apt install python3-cryptography') or "
             f"'pip install --user {' '.join(LOGIN_DEPS[m] for m in missing)}'.")
    else:
        ok("Python login dependencies ready.")
    return missing
