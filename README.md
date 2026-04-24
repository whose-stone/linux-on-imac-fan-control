# iMac Fan Control (Linux)

A retro 90s-styled GUI for controlling the fans of a **2011 iMac**
(iMac12,1 21.5" / iMac12,2 27") running a Debian-based Linux distribution
such as **ParrotOS**, Kali, Debian, Ubuntu, or Mint.

The app talks directly to the `applesmc` kernel module - no extra daemon
is needed. It auto-detects every fan and temperature sensor exposed by
SMC, gives each fan its own slider, and shows a live wall of LCD-style
readouts.

![iMac Fan Control - dark theme on a 27" iMac12,2](docs/screenshot-dark.png)

## Features

- **Auto-detects fans** from `/sys/devices/platform/applesmc.768/fan*_*`.
  On a 27" iMac12,2 you get three sliders: **CPU**, **HDD**, and **ODD**.
- **Exact-RPM control** per fan: "Set Fan Speed" writes `1` to
  `fan*_manual` and the slider value to `fan*_output`, pinning the fan
  to that exact RPM. A **MANUAL / AUTO** indicator next to each fan
  shows the current state.
- **"Release to Auto"** per fan (and a master "Reset All to Auto" in the
  toolbar) writes `0` to `fan*_manual` and hands control back to the SMC.
- **Human-readable temperatures** - `TC0D` shown as "CPU Die", `TG0H`
  as "GPU Heatsink", `TA0P` as "Ambient Air", etc. The raw 4-letter SMC
  code is kept alongside in small monospace for reference.
- **Live RPM readouts** on green-LCD panels, polled every 2 seconds.
- **Light and dark themes** - both styled like a Win95/Mac OS 7-era
  control panel, with chunky bevels and raised buttons. Toggle from
  the toolbar.
- **No background service** - the app only does anything while it's open.

> :warning: **MANUAL mode disables firmware auto-ramp.** If you pin a
> fan at a low RPM and the hardware gets hot, the SMC will NOT
> automatically ramp it up. Watch the temperature readouts and press
> "Release to Auto" if you see sustained temperatures above ~85 C.

## Compatibility

- **Hardware:** any Mac with `applesmc` working under Linux. Designed
  and tested for the 2011 iMac, but will also work on Mac minis,
  MacBooks, etc.
- **OS:** ParrotOS 6+ / Kali / Debian 11+ / Ubuntu 22.04+ / Linux Mint
  21+. Anything with Python 3.9+ and Tk should work.

## Install

```bash
git clone https://github.com/whose-stone/linux-on-imac-fan-control.git
cd linux-on-imac-fan-control
sudo ./install.sh
```

The installer:

1. Installs `python3`, Tk bindings, `policykit-1`, `librsvg2-bin`,
   `desktop-file-utils`, and `lm-sensors` via `apt`.
2. Loads the `applesmc` kernel module and registers it in
   `/etc/modules-load.d/applesmc.conf` so it loads at every boot.
3. Copies the app to `/usr/local/share/imac-fan-control/` and a launcher
   to `/usr/local/bin/imac-fan-control`.
4. Installs the app icon (SVG + PNGs at 16/22/24/32/48/64/128/256 px)
   into `/usr/share/icons/hicolor/` and `/usr/share/pixmaps/`.
5. Installs a `.desktop` entry under **Applications > System Tools**
   and a polkit policy so you can launch with a graphical auth prompt.
6. Refreshes `update-desktop-database`, `gtk-update-icon-cache`, and
   `xdg-desktop-menu` so the entry appears without a logout.

### ParrotOS note: `python3-tk` not in main repo

ParrotOS Lory's `main` component ships without `python3-tk`. The
installer detects this and falls back to the versioned
`python3.11-tk` package, but if your Parrot repo is also missing that,
pull the Debian Bookworm .debs manually once:

```bash
cd /tmp
BLT=https://deb.debian.org/debian/pool/main/b/blt
PY=https://deb.debian.org/debian/pool/main/p/python3-stdlib-extensions

wget "$BLT/blt_2.5.3+dfsg-8_amd64.deb"
wget "$BLT/tk8.6-blt2.5_2.5.3+dfsg-8_amd64.deb"
wget "$PY/python3-tk_3.11.2-3_amd64.deb"

sudo apt install -y ./blt_*.deb ./tk8.6-blt2.5_*.deb ./python3-tk_*.deb
python3 -c 'import tkinter; print("tkinter OK")'
```

Then re-run `sudo ./install.sh`.

## Update

```bash
cd linux-on-imac-fan-control
git pull
sudo ./install.sh
```

Reinstalling is safe and idempotent - every file is overwritten at the
same path.

## Uninstall

```bash
sudo ./install.sh --uninstall
```

## Launch

- **Application menu**: **Applications > System Tools > iMac Fan Control**
- **Terminal** (graphical auth prompt):

  ```bash
  pkexec imac-fan-control
  ```

- **Terminal** (plain sudo):

  ```bash
  sudo imac-fan-control
  ```

Running without root still works - the GUI opens in read-only mode, you
can see live RPM and temperature readouts, but the fan sliders can't
write. The status bar tells you when that happens.

## Usage

1. Launch the app. All fans appear in the left column, every SMC
   temperature sensor in the right column.
2. Drag a fan's slider to the RPM you want.
3. Click **Set Fan Speed**. The fan is pinned to that exact RPM
   (MANUAL mode).
4. Click **Release to Auto** to hand control back to the firmware
   (AUTO mode).
5. Use **Reset All to Auto** in the toolbar to release every fan at once.

## Themes

Toolbar **Switch to Dark** / **Switch to Light**:
- **Light**: classic Win95 silver with a navy title bar.
- **Dark**: charcoal chassis with a CRT-green LCD readout (pictured
  above).

## Troubleshooting

- **"applesmc not found"**: load the module with
  `sudo modprobe applesmc` and check `dmesg | grep applesmc`.
- **Slider snaps back after Apply**: fixed in the latest commit - pull
  and reinstall.
- **Fan doesn't change speed**: confirm the MANUAL indicator flipped on
  and that `cat /sys/devices/platform/applesmc.768/fan*_manual` shows
  `1`. If you got a polkit prompt but then cancelled, the write was
  denied silently.
- **Fan ramps to max after disk swap**: the well-known post-2011 iMac
  HDD fan issue happens when the original drive's thermal sensor goes
  missing. Use this tool to pin the `HDD` fan to a reasonable RPM as a
  workaround; the proper fix is an `smcFanControl`-style HDD temp
  spoof.
- **Bogus temperatures (e.g. `-126 C` or `-7 C`)**: these are ghost
  sensors the SMC still reports but isn't wired to on your specific
  model. They're harmless readouts from empty sensor IDs.
- **Menu entry missing after install**: run
  `sudo update-desktop-database /usr/share/applications` and log out/in.
- **Permission errors when setting speed**: relaunch with
  `pkexec imac-fan-control` or `sudo`.

## Files

| File                            | Purpose                                  |
|---------------------------------|------------------------------------------|
| `imac_fan_control.py`           | The GUI application                      |
| `install.sh`                    | Installer / uninstaller                  |
| `imac-fan-control.desktop`      | Application-menu entry                   |
| `org.imacfan.policy`            | Polkit policy for graphical sudo         |
| `imac-fan-control.svg`          | Application icon                         |
| `docs/screenshot-dark.png`      | Dark-theme screenshot                    |
| `all_fan.py`, `Victus_Fan.py`   | Older NBFC-based laptop fan controllers  |

## License

MIT.
