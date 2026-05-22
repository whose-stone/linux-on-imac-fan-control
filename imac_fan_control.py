#!/usr/bin/env python3
"""
iMac Fan Control - a retro 90s-styled GUI for controlling 2011 iMac fans
on Debian-based distros (ParrotOS, Kali, Debian, Ubuntu, Mint).

Reads/writes the applesmc sysfs interface:
  /sys/devices/platform/applesmc.768/fan*_*
  /sys/devices/platform/applesmc.768/temp*_*

Requires root to write fan_min / fan_manual / fan_output.
"""

import glob
import os
import sys
import time
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, font as tkfont

APP_NAME = "iMac Fan Control"
APP_VERSION = "1.0.0"
SMC_PATHS = [
    "/sys/devices/platform/applesmc.768",
]


# ---------------------------------------------------------------------------
# applesmc sysfs helpers
# ---------------------------------------------------------------------------

def find_smc_path():
    """Locate the applesmc sysfs directory."""
    for p in SMC_PATHS:
        if os.path.isdir(p):
            return p
    for hwmon in glob.glob("/sys/class/hwmon/hwmon*"):
        name_file = os.path.join(hwmon, "name")
        if os.path.isfile(name_file):
            try:
                with open(name_file) as f:
                    if f.read().strip() == "applesmc":
                        return os.path.realpath(hwmon)
            except OSError:
                continue
    return None


def read_file(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


# Sysfs roots we are ever allowed to write to.  write_file() refuses
# anything outside these, so a future bug can't turn it into an
# arbitrary-write-as-root primitive.
_WRITABLE_PREFIXES = (
    "/sys/devices/platform/applesmc.",
    "/sys/class/hwmon/",
)

# Absolute paths only - never resolve privilege helpers via $PATH, which
# the invoking user could point at a malicious binary.
_PRIV_HELPERS = ("/usr/bin/pkexec", "/usr/bin/sudo")


def write_file(path, value):
    """Try writing directly; fall back to pkexec/sudo via tee."""
    real = os.path.realpath(path)
    if not real.startswith(_WRITABLE_PREFIXES):
        return False, f"Refusing to write outside applesmc sysfs: {real}"
    try:
        with open(path, "w") as f:
            f.write(str(value))
        return True, None
    except PermissionError:
        for helper in _PRIV_HELPERS:
            if not os.access(helper, os.X_OK):
                continue
            try:
                subprocess.run(
                    [helper, "tee", path],
                    input=f"{value}\n".encode(),
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                return True, None
            except subprocess.CalledProcessError as e:
                return False, e.stderr.decode(errors="replace").strip()
        return False, "Permission denied (run as root or install pkexec/sudo)"
    except OSError as e:
        return False, str(e)


def friendly_fan_name(raw_label, idx):
    """Return a human label for a fan given its applesmc label and index.
    E.g. ('CPU', '3') -> 'CPU Fan'.  The raw SMC identifier is kept
    separately so the UI can render it as 'CPU Fan (fan3)'.
    """
    label = (raw_label or "").strip()
    if not label:
        return f"Fan {idx}"
    # Avoid a double 'Fan' suffix if the firmware already included one.
    if label.lower().endswith("fan"):
        return label
    return f"{label} Fan"


def discover_fans(smc_path):
    """Return list of fan dicts: {idx, label, min, max, input_path, min_path, manual_path}."""
    fans = []
    for min_path in sorted(glob.glob(os.path.join(smc_path, "fan*_min"))):
        base = os.path.basename(min_path)
        idx = base[len("fan"):-len("_min")]
        try:
            int(idx)
        except ValueError:
            continue
        raw_label = read_file(os.path.join(smc_path, f"fan{idx}_label")) or ""
        label = friendly_fan_name(raw_label, idx)
        try:
            fan_min = int(read_file(os.path.join(smc_path, f"fan{idx}_min"), "0"))
        except ValueError:
            fan_min = 0
        try:
            fan_max = int(read_file(os.path.join(smc_path, f"fan{idx}_max"), "6000"))
        except ValueError:
            fan_max = 6000
        try:
            fan_safe = int(read_file(os.path.join(smc_path, f"fan{idx}_safe"), str(fan_min)))
        except ValueError:
            fan_safe = fan_min
        fans.append({
            "idx": idx,
            "label": label,
            "code": f"fan{idx}",
            "min_rpm": fan_min,
            "max_rpm": fan_max,
            "safe_rpm": fan_safe,
            "input_path": os.path.join(smc_path, f"fan{idx}_input"),
            "min_path": os.path.join(smc_path, f"fan{idx}_min"),
            "manual_path": os.path.join(smc_path, f"fan{idx}_manual"),
            "output_path": os.path.join(smc_path, f"fan{idx}_output"),
        })
    return fans


def discover_temps(smc_path):
    """Return list of (friendly_label, raw_code, path) for every applesmc
    temperature sensor that currently reports a physically plausible value.

    applesmc exposes every SMC key the firmware publishes, including ones that
    aren't actually wired on a given board (ghost sensors).  Those typically
    read back as large negatives like -126/-128 C.  Filter them out at
    discovery time so the UI only shows real sensors.
    """
    temps = []
    for label_path in sorted(glob.glob(os.path.join(smc_path, "temp*_label"))):
        base = os.path.basename(label_path)
        idx = base[len("temp"):-len("_label")]
        raw = read_file(label_path) or f"temp{idx}"
        input_path = os.path.join(smc_path, f"temp{idx}_input")
        if not os.path.isfile(input_path):
            continue
        reading = read_temp_c(input_path)
        if not is_plausible_temp(reading):
            continue
        temps.append((friendly_temp_name(raw), raw, input_path))
    return temps


# A real thermistor on a running iMac should always be within this range.
# Anything outside it is either a ghost sensor or a transient error.
TEMP_MIN_C = 0.0
TEMP_MAX_C = 130.0


def is_plausible_temp(c):
    return c is not None and TEMP_MIN_C <= c <= TEMP_MAX_C


# Human-readable names for applesmc 4-letter SMC temperature codes.
# Covers the sensors commonly present on 2011 iMacs (iMac12,1/12,2).
_TEMP_NAME_MAP = {
    # Ambient / board
    "TA0P": "Ambient Air",
    "TA1P": "Ambient Air 2",
    "TA0V": "Ambient Air (filtered)",
    "TA0S": "PCI Slot",
    # CPU
    "TC0D": "CPU Die",
    "TC0E": "CPU (PECI)",
    "TC0F": "CPU (PECI filtered)",
    "TC0H": "CPU Heatsink",
    "TC0P": "CPU Proximity",
    "TC1C": "CPU Core 1",
    "TC2C": "CPU Core 2",
    "TC3C": "CPU Core 3",
    "TC4C": "CPU Core 4",
    "TC0c": "CPU Core 0",
    "TC1c": "CPU Core 1",
    "TC2c": "CPU Core 2",
    "TC3c": "CPU Core 3",
    "TC4c": "CPU Core 4",
    "TCGC": "CPU GFX Core",
    "TCGc": "CPU GFX Core",
    "TCSC": "CPU System Agent",
    "TCSc": "CPU System Agent",
    "TCXC": "CPU Package",
    "TCXc": "CPU Package",
    # GPU
    "TG0D": "GPU Die",
    "TG0d": "GPU Die",
    "TG0H": "GPU Heatsink",
    "TG0h": "GPU Heatsink",
    "TG0P": "GPU Proximity",
    "TG0p": "GPU Proximity",
    "TG1H": "GPU Heatsink 2",
    # Heatsinks
    "Th0H": "Main Heatsink 1",
    "Th1H": "Main Heatsink 2",
    "Th2H": "Main Heatsink 3",
    "TH0O": "Heatsink Outlet 1",
    "TH1O": "Heatsink Outlet 2",
    # Storage
    "TH0P": "Hard Drive",
    "TH1P": "Hard Drive Bay 2",
    "THSP": "Hard Drive Proximity",
    "TO0P": "Optical Drive",
    # LCD
    "TL0P": "LCD Panel",
    "TL1P": "LCD Proximity",
    "TL0V": "LCD Backlight Sensor 1",
    "TL1V": "LCD Backlight Sensor 2",
    "TL2V": "LCD Backlight Sensor 3",
    "TL0p": "LCD Panel 2",
    "TL1p": "LCD Panel 3",
    "TLAV": "LCD Ambient",
    # Memory
    "TM0P": "Memory Proximity",
    "TM0S": "Memory Slot",
    "Tm0P": "Memory Bank",
    # Northbridge / PCH
    "TN0D": "Northbridge Die",
    "TN0H": "Northbridge Heatsink",
    "TN0P": "Northbridge Proximity",
    "TS0D": "PCH Die",
    "TS0P": "PCH Proximity",
    # Power
    "TP0P": "Power Supply",
    "Tp0C": "Power Supply 1",
    "Tp1C": "Power Supply 2",
    # Misc
    "TW0P": "Wireless Proximity",
    "TB0T": "Battery",
    "TB1T": "Battery Cell 1",
    "TB2T": "Battery Cell 2",
    "TI0P": "Thunderbolt Proximity",
    "TZ0C": "Thermal Zone 0",
    "TZ1C": "Thermal Zone 1",
}


def friendly_temp_name(code):
    """Map a raw SMC code like 'TC0D' to a friendly name; fall back to the code."""
    if code in _TEMP_NAME_MAP:
        return _TEMP_NAME_MAP[code]
    # Case-insensitive retry - some SMCs use lowercase 'c' / 'd' / 'p'.
    ci = next((v for k, v in _TEMP_NAME_MAP.items() if k.lower() == code.lower()), None)
    if ci:
        return ci
    # Heuristic fallback for unknown codes: pick a readable prefix
    if len(code) == 4 and code[0] in "Tt":
        zone = code[1]
        suffix = code[-1]
        zone_map = {
            "A": "Ambient", "C": "CPU", "G": "GPU", "H": "Heatsink",
            "h": "Heatsink", "L": "LCD", "M": "Memory", "m": "Memory",
            "N": "Northbridge", "O": "Optical", "P": "Power",
            "p": "Power", "S": "PCH", "W": "Wireless", "B": "Battery",
            "I": "Thunderbolt", "Z": "Thermal Zone",
        }
        suffix_map = {"D": "Die", "H": "Heatsink", "P": "Proximity",
                      "C": "Core", "S": "Slot", "T": "Temp"}
        base = zone_map.get(zone, f"Sensor {zone}")
        tail = suffix_map.get(suffix, "")
        friendly = f"{base} {tail}".strip()
        return friendly or code
    return code


def read_temp_c(path):
    raw = read_file(path)
    if raw is None:
        return None
    try:
        return int(raw) / 1000.0
    except ValueError:
        return None


def read_rpm(path):
    raw = read_file(path)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Themes (Win95-style retro palettes)
# ---------------------------------------------------------------------------

THEMES = {
    "light": {
        "bg":          "#C0C0C0",
        "fg":          "#000000",
        "panel":       "#C0C0C0",
        "panel_dark":  "#808080",
        "panel_light": "#FFFFFF",
        "title_bg":    "#000080",
        "title_fg":    "#FFFFFF",
        "accent":      "#000080",
        "lcd_bg":      "#9BBC0F",
        "lcd_fg":      "#0F380F",
        "lcd_warn":    "#A02020",
        "btn_bg":      "#C0C0C0",
        "btn_fg":      "#000000",
        "trough":      "#808080",
        "scale_bg":    "#C0C0C0",
    },
    "dark": {
        "bg":          "#2A2A2A",
        "fg":          "#E0E0E0",
        "panel":       "#3A3A3A",
        "panel_dark":  "#101010",
        "panel_light": "#5A5A5A",
        "title_bg":    "#000040",
        "title_fg":    "#00FF80",
        "accent":      "#00FF80",
        "lcd_bg":      "#101810",
        "lcd_fg":      "#00FF40",
        "lcd_warn":    "#FF4040",
        "btn_bg":      "#3A3A3A",
        "btn_fg":      "#E0E0E0",
        "trough":      "#101010",
        "scale_bg":    "#3A3A3A",
    },
}


# ---------------------------------------------------------------------------
# Custom Win95-style widgets
# ---------------------------------------------------------------------------

class BevelFrame(tk.Frame):
    """Frame with a hard 90s-style bevel: 1px highlight + 1px shadow."""
    def __init__(self, master, theme, raised=True, **kwargs):
        super().__init__(master, bg=theme["panel"], **kwargs)
        self._theme = theme
        self._raised = raised
        self._top = tk.Frame(self, height=1)
        self._left = tk.Frame(self, width=1)
        self._bottom = tk.Frame(self, height=1)
        self._right = tk.Frame(self, width=1)
        self.inner = tk.Frame(self, bg=theme["panel"])

        self._top.pack(side="top", fill="x")
        self._bottom.pack(side="bottom", fill="x")
        self._left.pack(side="left", fill="y")
        self._right.pack(side="right", fill="y")
        self.inner.pack(fill="both", expand=True)
        self.apply_theme(theme)

    def apply_theme(self, theme):
        self._theme = theme
        self.configure(bg=theme["panel"])
        self.inner.configure(bg=theme["panel"])
        if self._raised:
            tl, br = theme["panel_light"], theme["panel_dark"]
        else:
            tl, br = theme["panel_dark"], theme["panel_light"]
        self._top.configure(bg=tl)
        self._left.configure(bg=tl)
        self._bottom.configure(bg=br)
        self._right.configure(bg=br)


class TitleBar(tk.Frame):
    """Faux Win95 title bar inside the window."""
    def __init__(self, master, theme, text):
        super().__init__(master, bg=theme["title_bg"], height=22)
        self._theme = theme
        self.label = tk.Label(
            self, text=text, bg=theme["title_bg"], fg=theme["title_fg"],
            font=("Helvetica", 10, "bold"), anchor="w", padx=6,
        )
        self.label.pack(side="left", fill="both", expand=True)

    def apply_theme(self, theme):
        self._theme = theme
        self.configure(bg=theme["title_bg"])
        self.label.configure(bg=theme["title_bg"], fg=theme["title_fg"])


class LcdLabel(tk.Label):
    """Green-LCD-on-grey 7-segment-ish readout."""
    def __init__(self, master, theme, text="--", width=10):
        self._theme = theme
        super().__init__(
            master, text=text,
            bg=theme["lcd_bg"], fg=theme["lcd_fg"],
            font=("Courier", 11, "bold"),
            relief="sunken", bd=2, padx=6, pady=2, anchor="e",
            width=width,
        )

    def apply_theme(self, theme):
        self._theme = theme
        self.configure(bg=theme["lcd_bg"], fg=theme["lcd_fg"])

    def set_value(self, text, warn=False):
        self.configure(
            text=text,
            fg=self._theme["lcd_warn"] if warn else self._theme["lcd_fg"],
        )


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

class FanControlApp:
    POLL_SECONDS = 2.0

    def __init__(self, root):
        self.root = root
        self.theme_name = "light"
        self.theme = THEMES[self.theme_name]
        self.smc_path = find_smc_path()
        self.fans = []
        self.temps = []
        self.fan_widgets = {}
        self.temp_widgets = {}
        self.slider_vars = {}
        self.slider_widgets = {}
        self.user_min = {}
        self.suppress_command = set()
        self.poll_stop = threading.Event()
        self.poll_thread = None
        self.is_root = (os.geteuid() == 0)

        if not self.smc_path:
            messagebox.showerror(
                APP_NAME,
                "applesmc not found.\n\n"
                "Make sure the 'applesmc' kernel module is loaded:\n"
                "  sudo modprobe applesmc\n\n"
                "This tool requires a Mac running Linux.",
            )
            root.destroy()
            return

        self.fans = discover_fans(self.smc_path)
        self.temps = discover_temps(self.smc_path)

        if not self.fans:
            messagebox.showerror(
                APP_NAME,
                f"No fans were found under {self.smc_path}.",
            )
            root.destroy()
            return

        self._build_ui()
        self._apply_theme(self.theme_name)
        self._start_polling()

        if not self.is_root:
            self.status_var.set(
                "Not running as root - reads only. Use 'sudo' or pkexec to set fan speeds."
            )

    # ------- UI construction -------

    def _build_ui(self):
        self.root.title(APP_NAME)
        self.root.geometry("640x720")
        self.root.minsize(560, 600)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.outer = BevelFrame(self.root, self.theme, raised=True)
        self.outer.pack(fill="both", expand=True, padx=2, pady=2)

        self.title_bar = TitleBar(
            self.outer.inner, self.theme,
            f" {APP_NAME}  v{APP_VERSION}  -  iMac (applesmc)",
        )
        self.title_bar.pack(fill="x", padx=2, pady=2)

        # Toolbar
        toolbar = tk.Frame(self.outer.inner, bg=self.theme["panel"])
        toolbar.pack(fill="x", padx=4, pady=(2, 4))

        self.theme_btn = self._make_button(
            toolbar, "Switch to Dark", self._toggle_theme
        )
        self.theme_btn.pack(side="left", padx=(0, 4))

        self.refresh_btn = self._make_button(
            toolbar, "Refresh", self._refresh_now
        )
        self.refresh_btn.pack(side="left", padx=(0, 4))

        self.reset_btn = self._make_button(
            toolbar, "Reset All to Auto", self._reset_all
        )
        self.reset_btn.pack(side="left", padx=(0, 4))

        self.about_btn = self._make_button(
            toolbar, "About", self._show_about
        )
        self.about_btn.pack(side="right")

        # Body: two columns - fans (left), temperatures (right)
        body = tk.Frame(self.outer.inner, bg=self.theme["panel"])
        body.pack(fill="both", expand=True, padx=4, pady=2)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        # ---- Fans group
        self.fans_group = self._make_group(body, "Fans")
        self.fans_group.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        for fan in self.fans:
            self._make_fan_row(self.fans_group.inner, fan)

        # ---- Temps group
        self.temps_group = self._make_group(body, "Temperatures")
        self.temps_group.grid(row=0, column=1, sticky="nsew")

        temps_canvas = tk.Canvas(
            self.temps_group.inner, bg=self.theme["panel"],
            highlightthickness=0, bd=0,
        )
        temps_scroll = tk.Scrollbar(
            self.temps_group.inner, orient="vertical", command=temps_canvas.yview
        )
        temps_canvas.configure(yscrollcommand=temps_scroll.set)
        temps_scroll.pack(side="right", fill="y")
        temps_canvas.pack(side="left", fill="both", expand=True)
        self._temps_canvas = temps_canvas

        temps_inner = tk.Frame(temps_canvas, bg=self.theme["panel"])
        self._temps_inner = temps_inner
        temps_canvas.create_window((0, 0), window=temps_inner, anchor="nw")
        temps_inner.bind(
            "<Configure>",
            lambda e: temps_canvas.configure(scrollregion=temps_canvas.bbox("all")),
        )

        for label, raw_code, path in self.temps:
            self._make_temp_row(temps_inner, label, raw_code, path)

        # ---- Status bar
        self.status_var = tk.StringVar(value="Ready.")
        status_wrap = BevelFrame(self.outer.inner, self.theme, raised=False)
        status_wrap.pack(fill="x", padx=2, pady=(2, 2))
        self.status_label = tk.Label(
            status_wrap.inner, textvariable=self.status_var,
            bg=self.theme["panel"], fg=self.theme["fg"],
            font=("Helvetica", 9), anchor="w", padx=6, pady=2,
        )
        self.status_label.pack(fill="x")

        self._extra_widgets = [toolbar, body, self.status_label]

    def _make_group(self, master, title):
        group = BevelFrame(master, self.theme, raised=True)
        header = tk.Label(
            group.inner, text=title, bg=self.theme["panel"], fg=self.theme["fg"],
            font=("Helvetica", 10, "bold"), anchor="w", padx=6, pady=2,
        )
        header.pack(fill="x")
        sep = tk.Frame(group.inner, height=1, bg=self.theme["panel_dark"])
        sep.pack(fill="x", padx=4)
        sep_hl = tk.Frame(group.inner, height=1, bg=self.theme["panel_light"])
        sep_hl.pack(fill="x", padx=4)
        group._header = header
        group._sep = sep
        group._sep_hl = sep_hl
        return group

    def _make_button(self, master, text, command):
        btn = tk.Button(
            master, text=text, command=command,
            bg=self.theme["btn_bg"], fg=self.theme["btn_fg"],
            activebackground=self.theme["panel_light"],
            activeforeground=self.theme["btn_fg"],
            relief="raised", bd=2, padx=10, pady=2,
            font=("Helvetica", 9, "bold"), highlightthickness=0,
        )
        return btn

    def _make_fan_row(self, parent, fan):
        row = BevelFrame(parent, self.theme, raised=False)
        row.pack(fill="x", padx=4, pady=4)

        header = tk.Frame(row.inner, bg=self.theme["panel"])
        header.pack(fill="x", padx=4, pady=(4, 0))

        name_lbl = tk.Label(
            header, text=fan["label"],
            bg=self.theme["panel"], fg=self.theme["fg"],
            font=("Helvetica", 10, "bold"), anchor="w",
        )
        name_lbl.pack(side="left")
        code_lbl = tk.Label(
            header, text=f"({fan['code']})",
            bg=self.theme["panel"], fg=self.theme["panel_dark"],
            font=("Courier", 8),
        )
        code_lbl.pack(side="left", padx=(4, 0))

        mode_lbl = tk.Label(
            header, text="AUTO",
            bg=self.theme["panel"], fg=self.theme["accent"],
            font=("Courier", 9, "bold"),
        )
        mode_lbl.pack(side="left", padx=(8, 0))

        rpm_lbl = LcdLabel(header, self.theme, text="---- RPM", width=10)
        rpm_lbl.pack(side="right")

        info = tk.Label(
            row.inner,
            text=f"Range: {fan['min_rpm']}-{fan['max_rpm']} RPM",
            bg=self.theme["panel"], fg=self.theme["fg"],
            font=("Helvetica", 8), anchor="w",
        )
        info.pack(fill="x", padx=4)

        # Initial slider value: current fan*_output if the fan is already
        # in manual mode, otherwise the current measured RPM (falls back to min).
        manual_now = read_rpm(fan["manual_path"]) == 1
        initial = read_rpm(fan["output_path"]) if manual_now else read_rpm(fan["input_path"])
        if initial is None:
            initial = fan["min_rpm"]
        initial = max(fan["min_rpm"], min(initial, fan["max_rpm"]))

        var = tk.IntVar(value=initial)
        scale = tk.Scale(
            row.inner, from_=fan["min_rpm"], to=fan["max_rpm"],
            orient="horizontal", variable=var, resolution=50,
            showvalue=True, length=320,
            bg=self.theme["scale_bg"], fg=self.theme["fg"],
            troughcolor=self.theme["trough"],
            activebackground=self.theme["panel_light"],
            highlightthickness=0, relief="raised", bd=2,
            font=("Helvetica", 8),
            command=lambda v, f=fan: self._on_slider(f, v),
        )
        scale.pack(fill="x", padx=4, pady=(2, 4))

        actions = tk.Frame(row.inner, bg=self.theme["panel"])
        actions.pack(fill="x", padx=4, pady=(0, 4))

        apply_btn = self._make_button(
            actions, "Set Fan Speed", lambda f=fan: self._apply_fan(f)
        )
        apply_btn.pack(side="left", padx=(0, 4))

        auto_btn = self._make_button(
            actions, "Release to Auto", lambda f=fan: self._reset_fan(f)
        )
        auto_btn.pack(side="left")

        self.slider_vars[fan["idx"]] = var
        self.slider_widgets[fan["idx"]] = scale
        self.fan_widgets[fan["idx"]] = {
            "row": row, "header": header, "name": name_lbl,
            "mode": mode_lbl, "rpm": rpm_lbl, "info": info, "scale": scale,
            "actions": actions, "apply": apply_btn, "auto": auto_btn,
        }

    def _make_temp_row(self, parent, label, raw_code, path):
        row = tk.Frame(parent, bg=self.theme["panel"])
        row.pack(fill="x", padx=4, pady=2)
        name = tk.Label(
            row, text=label, bg=self.theme["panel"], fg=self.theme["fg"],
            font=("Helvetica", 9), anchor="w", width=22,
        )
        name.pack(side="left")
        code = tk.Label(
            row, text=f"({raw_code})",
            bg=self.theme["panel"], fg=self.theme["panel_dark"],
            font=("Courier", 8), anchor="w",
        )
        code.pack(side="left", padx=(4, 0))
        value = LcdLabel(row, self.theme, text="-- C", width=8)
        value.pack(side="right")
        self.temp_widgets[path] = {"row": row, "name": name,
                                    "code": code, "value": value}

    # ------- Theming -------

    def _apply_theme(self, name):
        self.theme_name = name
        self.theme = THEMES[name]
        t = self.theme
        self.root.configure(bg=t["bg"])

        def walk(widget):
            for w in widget.winfo_children():
                if isinstance(w, BevelFrame):
                    w.apply_theme(t)
                    walk(w.inner)
                elif isinstance(w, TitleBar):
                    w.apply_theme(t)
                elif isinstance(w, LcdLabel):
                    w.apply_theme(t)
                else:
                    self._restyle_generic(w, t)
                    walk(w)

        self.outer.apply_theme(t)
        self.title_bar.apply_theme(t)
        walk(self.outer.inner)
        self.theme_btn.configure(text="Switch to Light" if name == "dark" else "Switch to Dark")
        if hasattr(self, "_temps_canvas"):
            self._temps_canvas.configure(bg=t["panel"])
            self._temps_inner.configure(bg=t["panel"])

    def _restyle_generic(self, w, t):
        cls = w.winfo_class()
        try:
            if cls == "Frame":
                w.configure(bg=t["panel"])
            elif cls == "Label":
                w.configure(bg=t["panel"], fg=t["fg"])
            elif cls == "Button":
                w.configure(
                    bg=t["btn_bg"], fg=t["btn_fg"],
                    activebackground=t["panel_light"],
                    activeforeground=t["btn_fg"],
                )
            elif cls == "Scale":
                w.configure(
                    bg=t["scale_bg"], fg=t["fg"],
                    troughcolor=t["trough"],
                    activebackground=t["panel_light"],
                    highlightbackground=t["panel"],
                )
            elif cls == "Scrollbar":
                w.configure(bg=t["panel"], troughcolor=t["trough"],
                            activebackground=t["panel_light"])
        except tk.TclError:
            pass

    def _toggle_theme(self):
        self._apply_theme("dark" if self.theme_name == "light" else "light")

    # ------- Polling -------

    def _start_polling(self):
        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()

    def _poll_loop(self):
        while not self.poll_stop.is_set():
            try:
                self._update_readouts()
            except Exception as e:
                print(f"Poll error: {e}", file=sys.stderr)
            self.poll_stop.wait(self.POLL_SECONDS)

    def _update_readouts(self):
        # fan RPMs / manual mode indicator
        for fan in self.fans:
            rpm = read_rpm(fan["input_path"])
            manual = read_rpm(fan["manual_path"])
            widgets = self.fan_widgets.get(fan["idx"])
            if not widgets:
                continue
            text = f"{rpm} RPM" if rpm is not None else "--- RPM"
            warn = rpm is not None and rpm >= int(fan["max_rpm"] * 0.95)
            self.root.after(0, widgets["rpm"].set_value, text, warn)
            mode_txt = "MANUAL" if manual == 1 else "AUTO"
            self.root.after(0, lambda w=widgets, t=mode_txt: w["mode"].config(text=t))

        # temperatures
        for label, raw_code, path in self.temps:
            t = read_temp_c(path)
            widgets = self.temp_widgets.get(path)
            if not widgets:
                continue
            if not is_plausible_temp(t):
                self.root.after(0, widgets["value"].set_value, "-- C", False)
            else:
                warn = t >= 80
                self.root.after(0, widgets["value"].set_value, f"{t:5.1f} C", warn)

    def _refresh_now(self):
        threading.Thread(target=self._update_readouts, daemon=True).start()
        self.status_var.set("Refreshed.")

    # ------- Fan actions -------

    def _on_slider(self, fan, value):
        # User is dragging the slider - just remember the target.  Nothing else
        # fights this value now, so the slider stays exactly where the user put it.
        self.user_min[fan["idx"]] = int(float(value))

    def _apply_fan(self, fan):
        """Force the fan to an exact RPM using applesmc manual mode."""
        var = self.slider_vars[fan["idx"]]
        target = int(var.get())
        target = max(fan["min_rpm"], min(target, fan["max_rpm"]))

        # Enable manual mode, then write the exact RPM to fan*_output.
        ok1, err1 = write_file(fan["manual_path"], 1)
        if not ok1:
            self.status_var.set(f"Failed to enable manual mode: {err1}")
            messagebox.showerror(
                APP_NAME,
                f"Could not write to:\n{fan['manual_path']}\n\n{err1}",
            )
            return
        ok2, err2 = write_file(fan["output_path"], target)
        if not ok2:
            self.status_var.set(f"Failed to set {fan['label']}: {err2}")
            messagebox.showerror(
                APP_NAME,
                f"Could not write to:\n{fan['output_path']}\n\n{err2}",
            )
            return
        self.status_var.set(
            f"{fan['label']}: locked at {target} RPM (MANUAL mode)."
        )

    def _reset_fan(self, fan):
        """Hand control back to the SMC (firmware auto-cooling)."""
        ok, err = write_file(fan["manual_path"], 0)
        if ok:
            self.status_var.set(
                f"{fan['label']}: released to AUTO (firmware-controlled)."
            )
        else:
            self.status_var.set(f"Reset failed: {err}")

    def _reset_all(self):
        failures = []
        for fan in self.fans:
            ok, err = write_file(fan["manual_path"], 0)
            if not ok:
                failures.append(f"{fan['label']}: {err}")
        if failures:
            self.status_var.set("Reset finished with errors (see dialog).")
            messagebox.showwarning(APP_NAME, "Some fans could not be reset:\n\n" + "\n".join(failures))
        else:
            self.status_var.set("All fans released to AUTO (firmware control).")

    # ------- Misc -------

    def _show_about(self):
        messagebox.showinfo(
            APP_NAME,
            f"{APP_NAME} v{APP_VERSION}\n\n"
            "Retro fan controller for the 2011 iMac running Linux.\n"
            "Reads applesmc sysfs to detect fans and temperatures.\n"
            "'Set Fan Speed' locks the fan at an exact RPM via fan*_manual\n"
            "+ fan*_output.  'Release to Auto' hands control back to the SMC.\n\n"
            "(c) MIT License.",
        )

    def _on_close(self):
        self.poll_stop.set()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        # Use a classic theme as the base for ttk widgets.
        ttk.Style(root).theme_use("classic")
    except tk.TclError:
        pass
    app = FanControlApp(root)
    if root.winfo_exists():
        root.mainloop()


if __name__ == "__main__":
    main()
