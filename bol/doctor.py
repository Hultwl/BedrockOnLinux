"""bol.doctor — environment health checks."""
# SPDX-License-Identifier: MIT

import shutil
import sys

from . import deps
from .config import PRETTY, VERSION
from .log import info, ok, warn


def doctor():
    info(f"{PRETTY} {VERSION} — system check")
    hint = next((h for pm, h in (
        ("apt-get", "sudo apt install {}"), ("dnf", "sudo dnf install {}"),
        ("pacman", "sudo pacman -S {}"), ("zypper", "sudo zypper in {}"))
        if shutil.which(pm)), "installe : {}")
    miss = []
    print(f"  {'python3':12} : {sys.version.split()[0]}")
    for tool, pkg in (("tar", "tar"), ("curl", "curl"), ("unzstd", "zstd")):
        have = shutil.which(tool)
        print(f"  {tool:12} : {'OK' if have else 'MANQUANT'}")
        if not have and not (tool == "curl" and shutil.which("wget")):
            miss.append(pkg)
    # tkinter (GUI) — probe by import spec so a missing Tk doesn't raise here
    tk_ok = deps.have("tkinter")
    print(f"  {'tkinter':12} : {'OK (GUI)' if tk_ok else 'MANQUANT (GUI)'}")
    if not tk_ok:
        miss.append("python3-tk")
    # cryptography (native Microsoft login) — see bol.deps
    cr_ok = deps.have("cryptography")
    print(f"  {'cryptography':12} : "
          f"{'OK (login)' if cr_ok else 'MANQUANT (login)'}")
    if not cr_ok:
        miss.append("python3-cryptography")
    if miss:
        warn("To install: " + hint.format(" ".join(sorted(set(miss)))))
        return False
    ok("System ready.")
    return True
