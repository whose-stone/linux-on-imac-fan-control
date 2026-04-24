# iMac Fan Control (Linux)

A retro 90s-styled GUI for controlling the fans of a **2011 iMac**
(iMac12,1 21.5" / iMac12,2 27") running a Debian-based Linux distribution
such as **ParrotOS**, Kali, Debian, Ubuntu, or Mint.

The app talks directly to the `applesmc` kernel module - no extra daemon
is needed. It auto-detects every fan and temperature sensor exposed by SMC,
gives each fan its own slider, and shows a live wall of LCD-style readouts.

## Features

- **Auto-detects fans** from `/sys/devices/platform/applesmc.768/fan*_*`.
  On a 27" iMac12,2 you typically get three sliders: **CPU**, **HDD**, **ODD**.
- **One slider per fan**, labelled with the firmware-supplied name and
  bounded by the firmware-supplied min/max RPM range.
- **Live temperatures** for every SMC sensor (CPU, GPU, ambient, memory,
  hard drive, optical drive, heatsink, etc).
- **Light and dark themes** - both styled like a Win95/Mac OS 7-era control
  panel, with chunky bevels, raised buttons, and green-LCD readouts.
- **Safe by default**: writes to `fan*_min` so the firmware retains
  emergency thermal control. An "Auto" button per fan and a master
  "Reset All to Auto" button restore the firmware default minimum.
- **No background service**: the app only does anything while it's open.

## Compatibility

- **Hardware:** any Mac with `applesmc` working under Linux. Designed and
  tested for the 2011 iMac, but works on Mac minis, MacBooks, etc.
- **OS:** ParrotOS / Kali / Debian 11+ / Ubuntu 22.04+ / Linux Mint 21+.
  Anything with Python 3.9+ and Tk should work.

## Install from GitHub

```bash
git clone https://github.com/whose-stone/linux-on-imac-fan-control.git
cd linux-on-imac-fan-control
sudo ./install.sh
```

The installer:

1. Installs `python3`, `python3-tk`, `policykit-1`, and `lm-sensors` via
   `apt`.
2. Loads the `applesmc` kernel module and adds it to
   `/etc/modules-load.d/applesmc.conf` so it loads at boot.
3. Copies the app to `/usr/local/share/imac-fan-control/` and a launcher
   to `/usr/local/bin/imac-fan-control`.
4. Installs a `.desktop` entry and a polkit policy so you can launch it
   from your menu and authenticate via the standard graphical prompt.

To uninstall:

```bash
sudo ./install.sh --uninstall
```

## Run

From a terminal, with privileges to write applesmc:

```bash
sudo imac-fan-control
# or
pkexec imac-fan-control
```

Or just click **iMac Fan Control** in your application menu (Utilities).

You can also run the script in place without installing:

```bash
sudo python3 imac_fan_control.py
```

If you launch it without root the GUI still works - you'll see live RPM
and temperature readouts - but the fan sliders won't be able to write.
The status bar will tell you when that's the case.

## How it controls fans

**Set Fan Speed** locks the fan at an exact RPM:

1. Writes `1` to `fan<N>_manual` to take the fan off firmware control.
2. Writes the slider value to `fan<N>_output` as the hard setpoint.

The fan will spin at that RPM until you press **Release to Auto** on
that fan (or **Reset All to Auto** in the toolbar), which writes `0` to
`fan<N>_manual` and hands control back to the SMC.

The mode indicator next to each fan name shows **MANUAL** or **AUTO**
based on the current state of `fan<N>_manual`.

> :warning: In MANUAL mode the firmware will **not** ramp the fan up on
> its own if temperatures spike. Keep an eye on the temperature
> readouts, and release to AUTO if you see sustained high temps.

## Theming

Click **Switch to Dark** / **Switch to Light** in the toolbar. The dark
theme uses a CRT-green LCD readout on a dark grey chassis; the light
theme is classic Win95 silver with a navy title bar.

## Troubleshooting

- **"applesmc not found"**: load the module with
  `sudo modprobe applesmc` and check `dmesg | grep applesmc`. Some Macs
  need the SMC kernel module from a recent kernel.
- **Sliders snap back**: the firmware enforces hardware-defined limits.
  You cannot set a min RPM above `fan*_max` or below `fan*_min`.
- **Fan ramps to 6000 after disk swap**: the famous post-2011 iMac HDD
  fan issue happens when the original disk's thermal sensor goes missing.
  This tool can mask it (set `HDD` slider to a comfortable RPM), but the
  proper fix is `smcFanControl`-style HDD temperature spoofing.
- **Permission errors**: relaunch with `pkexec imac-fan-control` or
  `sudo`.

## Files

| File                            | Purpose                                  |
|---------------------------------|------------------------------------------|
| `imac_fan_control.py`           | The GUI application                      |
| `install.sh`                    | Installer / uninstaller                  |
| `imac-fan-control.desktop`      | Application-menu entry                   |
| `org.imacfan.policy`            | Polkit policy for graphical sudo         |
| `imac-fan-control.svg`          | Application icon                         |
| `all_fan.py`, `Victus_Fan.py`   | Older NBFC-based laptop fan controllers  |

## License

MIT.
