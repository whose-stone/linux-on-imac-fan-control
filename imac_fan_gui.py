#!/usr/bin/env python3
"""Retro iMac fan controller GUI for Debian-based Linux.

Designed for 2011 iMac systems that expose fan and PWM controls through
`/sys/class/hwmon` (typically via applesmc / coretemp drivers).
"""

from __future__ import annotations

import os
import re
import subprocess
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox


SYS_HWMON = Path("/sys/class/hwmon")


@dataclass
class FanChannel:
    hwmon_name: str
    fan_label: str
    fan_input_path: Path
    pwm_path: Path | None
    pwm_enable_path: Path | None
    pwm_max_path: Path | None


@dataclass
class TempSensor:
    label: str
    input_path: Path


class Theme:
    def __init__(self, name: str, bg: str, panel: str, fg: str, accent: str, border: str):
        self.name = name
        self.bg = bg
        self.panel = panel
        self.fg = fg
        self.accent = accent
        self.border = border


LIGHT_THEME = Theme(
    name="Light",
    bg="#ece8d8",
    panel="#f8f4e7",
    fg="#1f1f1f",
    accent="#2f5f9c",
    border="#1f1f1f",
)

DARK_THEME = Theme(
    name="Dark",
    bg="#1f2430",
    panel="#2b3245",
    fg="#f2f2f2",
    accent="#71d0ff",
    border="#8d95a6",
)


class ImacFanControllerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("iMac 2011 Fan Studio")
        self.root.geometry("900x640")
        self.root.minsize(820, 580)

        self.theme = DARK_THEME
        self.fans: list[FanChannel] = []
        self.temps: list[TempSensor] = []
        self.fan_rows: list[dict] = []
        self.temp_labels: list[tk.Label] = []

        self.top_frame = tk.Frame(root)
        self.top_frame.pack(fill="x", padx=16, pady=(16, 8))

        self.title_label = tk.Label(
            self.top_frame,
            text="iMac 2011 Fan Studio",
            font=("Courier", 22, "bold"),
        )
        self.title_label.pack(side="left")

        self.theme_button = tk.Button(
            self.top_frame,
            text="Switch Theme",
            command=self.toggle_theme,
            width=14,
            font=("Courier", 10, "bold"),
        )
        self.theme_button.pack(side="right", padx=8)

        self.refresh_button = tk.Button(
            self.top_frame,
            text="Rescan Hardware",
            command=self.rescan,
            width=16,
            font=("Courier", 10, "bold"),
        )
        self.refresh_button.pack(side="right")

        self.info_label = tk.Label(
            root,
            text=(
                "Retro fan control panel for Debian-based ParrotOS. "
                "Tip: Run with sudo for PWM write access."
            ),
            anchor="w",
            font=("Courier", 10),
        )
        self.info_label.pack(fill="x", padx=16, pady=(0, 10))

        self.main_panel = tk.Frame(root, relief="ridge", bd=3)
        self.main_panel.pack(fill="both", expand=True, padx=16, pady=8)

        self.fan_panel = tk.Frame(self.main_panel)
        self.fan_panel.pack(fill="x", padx=12, pady=(12, 6))

        self.temp_panel = tk.Frame(self.main_panel)
        self.temp_panel.pack(fill="both", expand=True, padx=12, pady=(6, 12))

        self.rescan()
        self.apply_theme()
        self.update_readings()

    def toggle_theme(self) -> None:
        self.theme = LIGHT_THEME if self.theme is DARK_THEME else DARK_THEME
        self.apply_theme()

    def apply_theme(self) -> None:
        t = self.theme
        self.root.configure(bg=t.bg)
        self.top_frame.configure(bg=t.bg)
        self.main_panel.configure(bg=t.panel, highlightbackground=t.border, highlightthickness=1)
        self.fan_panel.configure(bg=t.panel)
        self.temp_panel.configure(bg=t.panel)

        for widget in [self.title_label, self.info_label]:
            widget.configure(bg=t.bg, fg=t.fg)

        for button in [self.theme_button, self.refresh_button]:
            button.configure(bg=t.panel, fg=t.fg, activebackground=t.accent, activeforeground=t.fg)

        for row in self.fan_rows:
            row["name"].configure(bg=t.panel, fg=t.fg)
            row["rpm"].configure(bg=t.panel, fg=t.accent)
            row["slider"].configure(bg=t.panel, fg=t.fg, troughcolor=t.bg, activebackground=t.accent)
            row["value"].configure(bg=t.panel, fg=t.fg)
            row["apply"].configure(bg=t.panel, fg=t.fg, activebackground=t.accent, activeforeground=t.fg)

        for label in self.temp_labels:
            label.configure(bg=t.panel, fg=t.fg)

    def clear_panel(self, panel: tk.Frame) -> None:
        for child in panel.winfo_children():
            child.destroy()

    def rescan(self) -> None:
        self.fans = discover_fans()
        self.temps = discover_temps()
        self.fan_rows = []
        self.temp_labels = []

        self.clear_panel(self.fan_panel)
        self.clear_panel(self.temp_panel)

        fan_header = tk.Label(self.fan_panel, text="Detected Fans", font=("Courier", 14, "bold"))
        fan_header.grid(row=0, column=0, sticky="w", pady=(0, 8))

        if not self.fans:
            tk.Label(
                self.fan_panel,
                text="No controllable fans found. Load applesmc and run as sudo.",
                font=("Courier", 11),
            ).grid(row=1, column=0, sticky="w")
        else:
            for i, fan in enumerate(self.fans, start=1):
                self.add_fan_row(i, fan)

        temp_header = tk.Label(self.temp_panel, text="System Temperatures", font=("Courier", 14, "bold"))
        temp_header.pack(anchor="w", pady=(0, 8))

        if not self.temps:
            lbl = tk.Label(self.temp_panel, text="No temp sensors discovered.", font=("Courier", 11))
            lbl.pack(anchor="w")
            self.temp_labels.append(lbl)
        else:
            for sensor in self.temps:
                lbl = tk.Label(self.temp_panel, text=f"{sensor.label}: --.- °C", font=("Courier", 11))
                lbl.pack(anchor="w", pady=1)
                self.temp_labels.append(lbl)

        self.apply_theme()

    def add_fan_row(self, row_idx: int, fan: FanChannel) -> None:
        frame = tk.Frame(self.fan_panel)
        frame.grid(row=row_idx, column=0, sticky="ew", pady=6)

        name = tk.Label(frame, text=fan.fan_label, font=("Courier", 11, "bold"), width=28, anchor="w")
        name.grid(row=0, column=0, sticky="w")

        rpm_lbl = tk.Label(frame, text="RPM: --", font=("Courier", 11), width=14, anchor="w")
        rpm_lbl.grid(row=0, column=1, padx=8)

        slider = tk.Scale(frame, from_=20, to=100, orient="horizontal", length=260, font=("Courier", 9))
        slider.set(50)
        slider.grid(row=0, column=2, padx=8)

        value_lbl = tk.Label(frame, text="50%", font=("Courier", 10), width=8)
        value_lbl.grid(row=0, column=3, padx=4)

        def on_slide(val: str) -> None:
            value_lbl.configure(text=f"{int(float(val))}%")

        slider.configure(command=on_slide)

        apply_btn = tk.Button(
            frame,
            text="Apply",
            width=8,
            command=lambda f=fan, s=slider: self.set_fan_percent(f, int(s.get())),
            font=("Courier", 10, "bold"),
        )
        apply_btn.grid(row=0, column=4, padx=6)

        self.fan_rows.append({
            "fan": fan,
            "name": name,
            "rpm": rpm_lbl,
            "slider": slider,
            "value": value_lbl,
            "apply": apply_btn,
        })

    def set_fan_percent(self, fan: FanChannel, percent: int) -> None:
        if fan.pwm_path is None:
            messagebox.showwarning("Unsupported", f"{fan.fan_label} has no PWM control.")
            return

        try:
            if fan.pwm_enable_path and fan.pwm_enable_path.exists():
                fan.pwm_enable_path.write_text("1\n", encoding="utf-8")

            pwm_max = 255
            if fan.pwm_max_path and fan.pwm_max_path.exists():
                content = fan.pwm_max_path.read_text(encoding="utf-8").strip()
                pwm_max = int(content or "255")

            pwm_value = max(0, min(pwm_max, round((percent / 100) * pwm_max)))
            fan.pwm_path.write_text(f"{pwm_value}\n", encoding="utf-8")
        except PermissionError:
            messagebox.showerror("Permission denied", "Run with sudo to control fan speed.")
        except OSError as exc:
            messagebox.showerror("Write error", f"Failed to set fan speed: {exc}")

    def update_readings(self) -> None:
        for row in self.fan_rows:
            fan = row["fan"]
            rpm = read_int(fan.fan_input_path)
            row["rpm"].configure(text=f"RPM: {rpm if rpm is not None else '--'}")

        for label, sensor in zip(self.temp_labels, self.temps):
            raw = read_int(sensor.input_path)
            celsius = raw / 1000 if raw is not None else None
            text = f"{sensor.label}: {celsius:.1f} °C" if celsius is not None else f"{sensor.label}: --.- °C"
            label.configure(text=text)

        self.root.after(1500, self.update_readings)


def read_int(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def detect_hardware_name(hwmon_dir: Path) -> str:
    name_file = hwmon_dir / "name"
    if name_file.exists():
        try:
            return name_file.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    return hwmon_dir.name


def discover_fans() -> list[FanChannel]:
    fans: list[FanChannel] = []
    if not SYS_HWMON.exists():
        return fans

    fan_re = re.compile(r"fan(\d+)_input$")

    for hwmon_dir in sorted(SYS_HWMON.glob("hwmon*")):
        hwmon_name = detect_hardware_name(hwmon_dir)
        for entry in sorted(hwmon_dir.iterdir()):
            m = fan_re.match(entry.name)
            if not m:
                continue

            idx = m.group(1)
            label_file = hwmon_dir / f"fan{idx}_label"
            label = label_file.read_text(encoding="utf-8").strip() if label_file.exists() else f"Fan {idx}"
            user_name = f"{label} ({hwmon_name})"

            pwm_path = hwmon_dir / f"pwm{idx}"
            if not pwm_path.exists():
                pwm_path = hwmon_dir / "pwm1" if (hwmon_dir / "pwm1").exists() else None

            pwm_enable_path = hwmon_dir / f"pwm{idx}_enable"
            if not pwm_enable_path.exists():
                pwm_enable_path = hwmon_dir / "pwm1_enable" if (hwmon_dir / "pwm1_enable").exists() else None

            pwm_max_path = hwmon_dir / f"pwm{idx}_max"
            if not pwm_max_path.exists():
                pwm_max_path = None

            fans.append(
                FanChannel(
                    hwmon_name=hwmon_name,
                    fan_label=user_name,
                    fan_input_path=entry,
                    pwm_path=pwm_path,
                    pwm_enable_path=pwm_enable_path,
                    pwm_max_path=pwm_max_path,
                )
            )

    return fans


def discover_temps() -> list[TempSensor]:
    sensors: list[TempSensor] = []
    if not SYS_HWMON.exists():
        return sensors

    temp_re = re.compile(r"temp(\d+)_input$")
    for hwmon_dir in sorted(SYS_HWMON.glob("hwmon*")):
        hwmon_name = detect_hardware_name(hwmon_dir)
        for entry in sorted(hwmon_dir.iterdir()):
            m = temp_re.match(entry.name)
            if not m:
                continue
            idx = m.group(1)
            label_file = hwmon_dir / f"temp{idx}_label"
            raw_label = label_file.read_text(encoding="utf-8").strip() if label_file.exists() else f"Temp {idx}"
            sensors.append(TempSensor(label=f"{raw_label} ({hwmon_name})", input_path=entry))

    return sensors


def check_dependencies() -> None:
    missing = []
    for cmd in ["sensors"]:
        if subprocess.call(["bash", "-lc", f"command -v {cmd} >/dev/null 2>&1"]) != 0:
            missing.append(cmd)

    if missing:
        messagebox.showinfo(
            "Dependency hint",
            "Missing commands: "
            + ", ".join(missing)
            + "\nInstall with: sudo apt install lm-sensors",
        )


def main() -> None:
    root = tk.Tk()
    check_dependencies()
    ImacFanControllerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
