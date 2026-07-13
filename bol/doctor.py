"""bol.doctor — environment health checks."""
# SPDX-License-Identifier: MIT

import shutil
import sys

from . import deps
from .config import PRETTY, VERSION
from .gpu_safety import (
    acknowledge_gpu_safety_incident,
    graphics_safety_problem,
)
from .log import info, ok, warn


def _acknowledge_gpu_crash():
    """Clear an interrupted-launch block only while PLAY is fully idle."""

    # Import lazily to keep the ordinary doctor lightweight and avoid making
    # GPU safety state depend on the Wine/UMU modules at import time.
    from .prefix import active_prefix, launch_lock, prefix_processes

    with launch_lock():
        running = prefix_processes(active_prefix())
        if running:
            warn("Cannot acknowledge GPU safety while BedrockOnLinux still has "
                 f"{len(running)} Wine/UMU process(es). Force-stop them first.")
            return False
        had_marker = acknowledge_gpu_safety_incident()
    warn("GPU safety incident explicitly acknowledged for the current boot"
         + ("; interrupted-launch marker cleared." if had_marker else "."))
    return True


def doctor(acknowledge_gpu_crash=False):
    if acknowledge_gpu_crash and not _acknowledge_gpu_crash():
        return False
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
    tk_ok = deps.have("tkinter")
    print(f"  {'tkinter':12} : {'OK (GUI)' if tk_ok else 'MANQUANT (GUI)'}")
    if not tk_ok:
        miss.append("python3-tk")
    ctk_ok = deps.have("customtkinter")
    print(f"  {'customtkinter':12} : "
          f"{'OK (GUI)' if ctk_ok else 'auto-installed on launch'}")
    cr_ok = deps.have("cryptography")
    print(f"  {'cryptography':12} : "
          f"{'OK (login)' if cr_ok else 'MANQUANT (login)'}")
    if not cr_ok:
        miss.append("python3-cryptography")
    gpu_problem = graphics_safety_problem()
    print(f"  {'graphics':12} : "
          f"{'BLOQUÉ' if gpu_problem else 'OK (no unsafe state found)'}")
    if gpu_problem:
        warn("Unsafe graphics session: " + gpu_problem + ". Repair the host "
             "GPU driver and reboot; no Vulkan probe was attempted.")
    if miss:
        warn("To install: " + hint.format(" ".join(sorted(set(miss)))))
        return False
    if gpu_problem:
        return False
    ok("System ready.")
    return True
