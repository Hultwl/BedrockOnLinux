"""bol.gui — the Tkinter desktop GUI."""
# SPDX-License-Identifier: MIT

import os
import subprocess
import sys
import threading
from pathlib import Path

from .auth import NativeAuth, msa_logout, msa_signed_in
from .config import LOGS, PRETTY, VERSION
from .content import _mojang_dir, import_content
from .games import list_mc_versions
from .gamesetup import do_setup
from .launch import launch
from . import log
from .log import BolError, _LEVELS, warn
from .prefix import _mc_running, kill_wine, reset_prefix
from .update import check_for_update, self_update
from .util import load_settings, save_settings

def gui():
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        warn("Tkinter missing (install python3-tk).")
        return

    # Minecraft-launcher inspired palette: dark slate + signature green.
    BG, PANEL, PANEL2 = "#181a20", "#23262e", "#2c303a"
    FG, SUB, GOLD = "#f2f3f5", "#969ca6", "#e0b341"
    GREEN, GREEN_H = "#4c9f4f", "#58b85b"
    FIELD = "#2c303a"

    try:
        root = tk.Tk()
    except tk.TclError as e:
        # No usable X11 display — e.g. a pure Wayland session where the X11
        # socket wasn't granted (Flatpak issue #7). Don't dump a traceback.
        warn(f"No graphical display available ({e}). The launcher GUI needs an "
             "X11 (or XWayland) display. Use the command line instead, e.g. "
             "'bedrock-on-linux play', '… setup', '… login' or '… doctor'.")
        return
    root.title(PRETTY)
    root.geometry("880x560")
    root.minsize(800, 520)
    root.configure(bg=BG)

    icon_img = None
    here = Path(__file__).resolve().parent
    for p in (here / "data/icon.png",
              Path("/usr/lib/bedrock-on-linux/data/icon.png"),
              Path("/usr/share/icons/hicolor/256x256/apps/bedrock-on-linux.png")):
        if p.exists():
            try:
                icon_img = tk.PhotoImage(file=str(p))
                root.iconphoto(True, icon_img)
                root._icon = icon_img
                break
            except Exception:
                pass

    stl = ttk.Style()
    try:
        stl.theme_use("clam")
    except Exception:
        pass
    stl.configure(".", background=BG, foreground=FG, fieldbackground=FIELD,
                  bordercolor=PANEL2, lightcolor=PANEL2, darkcolor=PANEL2)
    stl.configure("Mc.TCombobox", fieldbackground=FIELD, background=FIELD,
                  foreground=FG, arrowcolor=FG, borderwidth=0, padding=8)
    stl.map("Mc.TCombobox", fieldbackground=[("readonly", FIELD)],
            foreground=[("readonly", FG)])
    stl.configure("Bar.Horizontal.TProgressbar", background=GREEN,
                  troughcolor=PANEL2, borderwidth=0, thickness=6)
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", FG)
    root.option_add("*TCombobox*Listbox.selectBackground", GREEN)

    na = NativeAuth()
    ui = {"versions": [], "busy": False, "details": False}

    def button(parent, text, cmd, bg, fg, hbg, font, padx, pady):
        b = tk.Label(parent, text=text, bg=bg, fg=fg, font=font,
                     padx=padx, pady=pady, cursor="hand2")
        b._bg, b._fg, b._hbg, b._on = bg, fg, hbg, True
        b.bind("<Enter>", lambda e: b._on and b.configure(bg=b._hbg))
        b.bind("<Leave>", lambda e: b._on and b.configure(bg=b._bg))
        b.bind("<Button-1>", lambda e: b._on and cmd())

        def enable(v):
            b._on = v
            b.configure(bg=b._bg if v else PANEL2, fg=b._fg if v else SUB,
                        cursor="hand2" if v else "arrow")
        b.enable = enable
        return b

    # ---- top bar: logo + title, account on the right ----
    top = tk.Frame(root, bg=BG)
    top.pack(fill="x", padx=24, pady=(16, 4))
    if icon_img is not None:
        try:
            sm = icon_img.subsample(max(1, icon_img.width() // 38))
            il = tk.Label(top, image=sm, bg=BG)
            il.image = sm
            il.pack(side="left", padx=(0, 12))
        except Exception:
            pass
    tk.Label(top, text="BedrockOnLinux", bg=BG, fg=FG,
             font=("", 16, "bold")).pack(side="left")

    acct = tk.Frame(top, bg=PANEL)
    acct.pack(side="right")
    acct_dot = tk.Label(acct, text="●", bg=PANEL, fg=SUB)
    acct_dot.pack(side="left", padx=(12, 6), pady=9)
    acct_txt = tk.StringVar(value="Not signed in")
    tk.Label(acct, textvariable=acct_txt, bg=PANEL, fg=FG).pack(side="left",
                                                                pady=9)
    acct_btn = button(acct, "Sign in", lambda: acct_click(), PANEL2, FG,
                      "#363b46", ("", 10, "bold"), 12, 6)
    acct_btn.pack(side="left", padx=(10, 8), pady=6)

    # ---- hero: centred logo + title ----
    hero = tk.Frame(root, bg=BG)
    hero.pack(fill="both", expand=True)
    hw = tk.Frame(hero, bg=BG)
    hw.place(relx=0.5, rely=0.42, anchor="center")
    if icon_img is not None:
        try:
            f = max(1, icon_img.width() // 130)
            hi = icon_img.subsample(f)
            hl = tk.Label(hw, image=hi, bg=BG)
            hl.image = hi
            hl.pack()
        except Exception:
            pass
    tk.Label(hw, text="Minecraft Bedrock", bg=BG, fg=FG,
             font=("", 23, "bold")).pack(pady=(12, 2))
    tk.Label(hw, text="Bedrock Edition for Linux",
             bg=BG, fg=SUB, font=("", 11)).pack()

    # ---- bottom bar: version selector (left), gear/details/PLAY (right) ----
    bar = tk.Frame(root, bg=PANEL)
    bar.pack(fill="x", side="bottom")
    barin = tk.Frame(bar, bg=PANEL)
    barin.pack(fill="x", padx=24, pady=15)

    vbox = tk.Frame(barin, bg=PANEL)
    vbox.pack(side="left")
    tk.Label(vbox, text="VERSION", bg=PANEL, fg=SUB,
             font=("", 8, "bold")).pack(anchor="w")
    mc_var = tk.StringVar()
    mc_cb = ttk.Combobox(vbox, textvariable=mc_var, width=24, state="readonly",
                         style="Mc.TCombobox", font=("", 11))
    mc_cb.pack(anchor="w", pady=(3, 0))

    play_btn = button(barin, "▶   PLAY", lambda: do_play(), GREEN, "white",
                      GREEN_H, ("", 15, "bold"), 46, 14)
    play_btn.pack(side="right")
    button(barin, "⚙", lambda: open_settings(), PANEL, SUB, PANEL2,
           ("", 15), 12, 10).pack(side="right", padx=(0, 12))
    det_btn = button(barin, "Details", lambda: toggle_details(), PANEL, SUB,
                     PANEL2, ("", 10), 12, 12)
    det_btn.pack(side="right", padx=(0, 4))

    # ---- status line + progress (above the bar) ----
    status = tk.Frame(root, bg=BG)
    status.pack(fill="x", side="bottom", padx=24, pady=(0, 8))
    status_txt = tk.StringVar(value="Ready to play.")
    status_lbl = tk.Label(status, textvariable=status_txt, bg=BG, fg=SUB,
                          anchor="w")
    status_lbl.pack(fill="x")
    prog = ttk.Progressbar(status, style="Bar.Horizontal.TProgressbar",
                           mode="determinate")

    # ---- collapsible details log ----
    detwrap = tk.Frame(root, bg=BG)
    logbox = tk.Text(detwrap, height=8, bg="#0d0f13", fg="#7fd97f", bd=0,
                     font=("monospace", 9), highlightthickness=0,
                     padx=10, pady=8)
    logbox.pack(fill="both", expand=True, padx=24, pady=(0, 4))
    for _tg, (_lbl, _a1, _a2, _lc, _mc) in _LEVELS.items():
        _nm = _lbl.strip()
        logbox.tag_configure("L_" + _nm, foreground=_lc,
                             font=("monospace", 9, "bold"))
        logbox.tag_configure("M_" + _nm, foreground=_mc)

    def toggle_details():
        ui["details"] = not ui["details"]
        if ui["details"]:
            detwrap.pack(fill="both", side="bottom")
            det_btn.configure(fg=FG)
        else:
            detwrap.pack_forget()
            det_btn.configure(fg=SUB)

    # ---- friendly status line + progress bar ----
    def set_status(t, color=SUB):
        root.after(0, lambda: (status_txt.set(t),
                               status_lbl.configure(fg=color)))

    def _show_bar():
        if not prog.winfo_ismapped():
            prog.pack(fill="x", pady=(6, 0))

    def bar_busy():           # animated bar for steps with no measurable %
        def ap():
            _show_bar()
            prog.configure(mode="indeterminate")
            prog.start(14)
        root.after(0, ap)

    def set_progress(g, t):   # measurable download progress
        def ap():
            _show_bar()
            prog.stop()
            prog.configure(mode="determinate", maximum=max(1, t), value=g)
            status_txt.set(f"Downloading Minecraft…  "
                           f"{int(100 * g / max(1, t))}%")
            status_lbl.configure(fg=FG)
        root.after(0, ap)

    def end_progress():
        def ap():
            prog.stop()
            prog.pack_forget()
        root.after(0, ap)

    def _friendly(line):
        m = line
        for tag in ("::", "OK", "!!", "xx"):
            if m.startswith(tag):
                m = m[len(tag):].strip()
                break
        low = m.lower()
        if "downloading minecraft" in low:
            return None        # handled by the % progress bar
        if ("building winegdk" in low or "cloning winegdk" in low
                or "updating winegdk" in low):
            return ("Setting up the game engine — first run, "
                    "this can take a while…")
        if "installing minecraft" in low or "reinstalling minecraft" in low:
            return "Installing Minecraft…"
        if "preparing gdk-proton" in low or "extracting" in low:
            return "Preparing the engine…"
        if "pre-auth" in low or "signing in" in low:
            return "Signing in to Xbox Live…"
        if "minecraft is running" in low:
            # the launcher's work is done — steady state, stop the spinner
            return ("Minecraft is running — close the game to come back here.",
                    True)
        if "starting minecraft" in low or "launching minecraft" in low:
            return "Starting Minecraft…"
        if "game closed" in low:
            return ("Minecraft closed.", True)
        return None

    def glog(line):
        lvl = _LEVELS.get(line[:2])
        if lvl:
            label = lvl[0]
            nm = label.strip()
            logbox.insert("end", label + "  ", "L_" + nm)
            logbox.insert("end", line[2:].strip() + "\n", "M_" + nm)
        else:
            logbox.insert("end", line + "\n")
        logbox.see("end")
        if not ui["busy"]:
            return
        if line.startswith("xx"):
            set_status(line[2:].strip(), "#e06c5b")
            return
        txt = _friendly(line)
        if txt:
            steady = False
            if isinstance(txt, tuple):
                txt, steady = txt
            if steady:
                # nothing measurable is running — stop the spinner, calm colour
                set_status(txt, GREEN if "running" in txt.lower() else SUB)
                end_progress()
            else:
                set_status(txt, FG)
                bar_busy()         # animate while a real step runs
    log._LOG_SINK = lambda m: root.after(0, glog, m)

    # ---- account (device-code Microsoft sign-in) ----
    def acct_state(ph):
        if ph == "in":
            acct_dot.configure(fg=GREEN)
            acct_txt.set("Signed in")
            acct_btn.configure(text="Sign out")
            acct_btn._mode = "out"
        elif ph == "auth":
            acct_dot.configure(fg=GOLD)
            acct_txt.set("Sign-in pending…")
            acct_btn._mode = "out"
        else:
            acct_dot.configure(fg=SUB)
            acct_txt.set("Not signed in")
            acct_btn.configure(text="Sign in")
            acct_btn._mode = "in"

    def acct_click():
        if getattr(acct_btn, "_mode", "in") == "out":
            msa_logout()
            na.stop()
            acct_state("out")
        else:
            threading.Thread(target=lambda: na.start(on_auth, on_online),
                             daemon=True).start()

    def on_auth(url, code):
        root.after(0, lambda: (acct_state("auth"), code_dialog(url, code)))

    def on_online():
        root.after(0, lambda: acct_state("in"))

    def code_dialog(url, code):
        d = tk.Toplevel(root, bg=PANEL)
        d.title("Sign in to Microsoft")
        d.configure(padx=26, pady=22)
        d.transient(root)
        d.resizable(False, False)
        tk.Label(d, text="Sign in to your Microsoft account", bg=PANEL, fg=FG,
                 font=("", 13, "bold")).pack(anchor="w")
        tk.Label(d, text="Open the link and enter this code:", bg=PANEL,
                 fg=SUB).pack(anchor="w", pady=(8, 12))
        cf = tk.Frame(d, bg=FIELD)
        cf.pack(fill="x")
        tk.Label(cf, text=code, bg=FIELD, fg=GOLD,
                 font=("monospace", 20, "bold")).pack(padx=18, pady=10)
        row = tk.Frame(d, bg=PANEL)
        row.pack(fill="x", pady=(14, 0))
        button(row, "Open link", lambda: subprocess.Popen(
            ["xdg-open", url], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL), GREEN, "white", GREEN_H,
            ("", 11, "bold"), 16, 9).pack(side="left")
        button(row, "Copy code", lambda: (root.clipboard_clear(),
               root.clipboard_append(code)), PANEL2, FG, "#363b46",
               ("", 11), 16, 9).pack(side="left", padx=10)

    # ---- versions ----
    def refresh_versions():
        beta = load_settings().get("show_betas", False)
        try:
            ui["versions"] = list_mc_versions(beta)
        except Exception as e:
            log._LOG_SINK(f"xx versions: {e}")
            return
        labels = [v["tag"] + ("  · beta" if v["beta"] else "")
                  for v in ui["versions"]]

        def ap():
            mc_cb.configure(values=labels)
            cur = (load_settings().get("mc_version") or "")
            pick = next((x for x in labels
                         if x.split("  ")[0] == cur
                         or x.split("  ")[0].startswith(cur + ".")),
                        labels[0] if labels else "")
            if labels:
                mc_var.set(pick)
        root.after(0, ap)

    def selected_version():
        if not ui["versions"] or not mc_var.get():
            return None
        labels = [v["tag"] + ("  · beta" if v["beta"] else "")
                  for v in ui["versions"]]
        try:
            return ui["versions"][labels.index(mc_var.get())]
        except ValueError:
            return None

    # ---- PLAY: auto-install (version + engine) then launch ----
    def busy(on):
        ui["busy"] = on
        play_btn.enable(not on)

    def do_play():
        if ui["busy"]:
            return
        busy(True)
        set_status("Preparing…", FG)
        bar_busy()

        def work():
            try:
                ver = selected_version()
                # do_setup logs each step; glog() turns them into a friendly
                # status line + animated/measured progress bar.
                do_setup(mc_ver=ver, progress=set_progress)
                set_status("Starting Minecraft…", FG)
                launch()
                set_status("Minecraft closed.", SUB)
            except Exception as e:
                log._LOG_SINK(f"xx {e}")
            finally:
                end_progress()
                root.after(0, lambda: busy(False))
        threading.Thread(target=work, daemon=True).start()

    # ---- settings popup (the few advanced bits, out of the way) ----
    def open_settings():
        d = tk.Toplevel(root, bg=PANEL)
        d.title("Settings")
        d.configure(padx=26, pady=22)
        d.transient(root)
        d.resizable(False, False)
        tk.Label(d, text="Settings", bg=PANEL, fg=FG,
                 font=("", 14, "bold")).pack(anchor="w", pady=(0, 12))
        beta_v = tk.BooleanVar(value=load_settings().get("show_betas", False))

        def save_beta():
            s2 = load_settings()
            s2["show_betas"] = beta_v.get()
            save_settings(s2)
            threading.Thread(target=refresh_versions, daemon=True).start()
        tk.Checkbutton(d, text="Show beta / preview versions", variable=beta_v,
                       command=save_beta, bg=PANEL, fg=FG, selectcolor=FIELD,
                       activebackground=PANEL, activeforeground=FG, bd=0,
                       highlightthickness=0, anchor="w").pack(fill="x", pady=2)

        diag_v = tk.BooleanVar(value=load_settings().get("diagnostics", False))

        def save_diag():
            s2 = load_settings()
            s2["diagnostics"] = diag_v.get()
            save_settings(s2)
        tk.Checkbutton(d, text="Advanced diagnostics (verbose logs — for bug "
                       "reports)", variable=diag_v, command=save_diag, bg=PANEL,
                       fg=FG, selectcolor=FIELD, activebackground=PANEL,
                       activeforeground=FG, bd=0, highlightthickness=0,
                       anchor="w").pack(fill="x", pady=2)
        tk.Frame(d, bg=PANEL2, height=1).pack(fill="x", pady=12)

        imp_status = tk.StringVar(value="")

        def do_import():
            from tkinter import filedialog, messagebox
            files = filedialog.askopenfilenames(
                parent=d, title="Import Minecraft content",
                filetypes=[("Minecraft content",
                            "*.mcpack *.mcaddon *.mcworld *.mctemplate *.mcskin"),
                           ("All files", "*.*")])
            if not files:
                return
            imp_status.set("Importing…")

            def work():
                done, errs = [], []
                for f in files:
                    try:
                        done += import_content(f)
                    except BolError as e:
                        errs.append(str(e))
                    except Exception as e:        # noqa: BLE001
                        errs.append(f"{Path(f).name}: {e}")
                msg = (f"Imported {len(done)} item(s)."
                       if done else "Nothing imported.")
                if errs:
                    msg += "\n\nProblems:\n• " + "\n• ".join(errs)
                if _mc_running():
                    msg += ("\n\nMinecraft is running — restart it to see the "
                            "new content.")
                d.after(0, lambda: (imp_status.set(""),
                                    messagebox.showinfo("Import", msg, parent=d)))
            threading.Thread(target=work, daemon=True).start()

        for label, fn in (
            ("Import content (.mcpack / .mcworld / .mcaddon)…", do_import),
            ("Open Minecraft folder", lambda: subprocess.Popen(
                ["xdg-open", str(_mojang_dir())], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)),
            ("Open logs folder", lambda: subprocess.Popen(
                ["xdg-open", str(LOGS)], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)),
            ("Repair (reset Wine prefix)", lambda: threading.Thread(
                target=reset_prefix, daemon=True).start()),
            ("Force stop Minecraft", kill_wine),
        ):
            button(d, label, fn, PANEL2, FG, "#363b46", ("", 11), 14, 9
                   ).pack(fill="x", pady=3)
        tk.Label(d, textvariable=imp_status, bg=PANEL, fg=GOLD,
                 font=("", 9)).pack(anchor="w")
        tk.Label(d, text=f"{PRETTY} {VERSION}", bg=PANEL, fg=SUB,
                 font=("", 9)).pack(anchor="w", pady=(14, 0))

    # ---- self-update notification (background check → banner) ----
    def relaunch_app():
        na.stop()
        try:
            if os.environ.get("APPIMAGE"):
                os.execv(os.environ["APPIMAGE"], [os.environ["APPIMAGE"], "gui"])
            tgt = os.path.realpath(sys.argv[0] or __file__)
            os.execv(sys.executable, [sys.executable, tgt, "gui"])
        except Exception:
            root.destroy()

    def update_progress(got, total):
        def ap():
            _show_bar()
            prog.stop()
            prog.configure(mode="determinate", maximum=max(1, total), value=got)
            status_txt.set(f"Downloading update…  {int(100 * got / max(1, total))}%")
            status_lbl.configure(fg=FG)
        root.after(0, ap)

    def restart_prompt():
        d = tk.Toplevel(root, bg=PANEL)
        d.title("Update installed")
        d.configure(padx=24, pady=20)
        d.transient(root)
        d.resizable(False, False)
        tk.Label(d, text="Update installed", bg=PANEL, fg=FG,
                 font=("", 13, "bold")).pack(anchor="w")
        tk.Label(d, text="Restart now to run the new version?", bg=PANEL,
                 fg=SUB).pack(anchor="w", pady=(4, 14))
        row = tk.Frame(d, bg=PANEL)
        row.pack(fill="x")
        button(row, "Restart now", relaunch_app, GREEN, "white", GREEN_H,
               ("", 11, "bold"), 16, 7).pack(side="right")
        button(row, "Later", d.destroy, PANEL2, FG, "#363b46",
               ("", 11), 14, 7).pack(side="right", padx=(0, 8))

    def run_update(rel, banner):
        banner.destroy()
        set_status(f"Updating to v{rel['version']}…", FG)
        bar_busy()

        def done(state, msg):
            end_progress()
            set_status(msg, GREEN if state == "ok"
                       else ("#e06c5b" if state == "error" else SUB))
            if state == "ok":
                restart_prompt()

        def work():
            state, msg = self_update(rel, progress=update_progress)
            root.after(0, lambda: done(state, msg))
        threading.Thread(target=work, daemon=True).start()

    def show_update_banner(rel):
        bn = tk.Frame(root, bg="#26331f")
        tk.Label(bn, text=f"  ⟳  Update available — v{rel['version']}   "
                          f"(you have {VERSION})", bg="#26331f", fg="#cfe8c2",
                 font=("", 10, "bold")).pack(side="left", padx=(20, 0), pady=8)
        button(bn, "Later", bn.destroy, "#26331f", "#9fb89a", "#33421f",
               ("", 10), 12, 5).pack(side="right", padx=(0, 16), pady=6)
        button(bn, "Update now", lambda: run_update(rel, bn), GREEN, "white",
               GREEN_H, ("", 10, "bold"), 14, 5).pack(side="right",
                                                      padx=(0, 8), pady=6)
        bn.pack(fill="x", after=top)

    def update_check():
        rel = check_for_update()
        if rel:
            root.after(0, lambda: show_update_banner(rel))

    acct_state("in" if msa_signed_in() else "out")
    threading.Thread(target=refresh_versions, daemon=True).start()
    threading.Thread(target=update_check, daemon=True).start()

    def on_close():
        na.stop()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
