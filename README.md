# iMac 2011 Fan Studio (ParrotOS / Debian)

A retro-inspired (90s style) GUI fan controller for Linux on Intel iMacs (including 2011 models).

It automatically:
- detects available fan channels from `/sys/class/hwmon`
- creates one slider per detected fan
- displays live RPM and system temperatures
- supports **Dark** and **Light** themes

## Why this tool

Many iMac fan scripts are fixed to specific fan IDs. This app scans hardware sensors at runtime so it can adapt to what the system exposes.

---

## Install from GitHub

```bash
git clone https://github.com/<your-user>/linux-on-imac-fan-control.git
cd linux-on-imac-fan-control
chmod +x imac_fan_gui.py
```

## Debian / ParrotOS dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-tk lm-sensors
```

Optional but recommended:

```bash
sudo sensors-detect
```

---

## Run

> Fan speed writes generally require root.

```bash
sudo ./imac_fan_gui.py
```

or

```bash
sudo python3 imac_fan_gui.py
```

---

## Notes for 2011 iMac hardware

- Fan control usually depends on kernel support via `applesmc` and exposed PWM entries.
- If no controllable fan appears, verify sensor modules are loaded and that `/sys/class/hwmon/*/pwm*` files exist.
- Temperature values are read from discovered `temp*_input` files and shown in °C.

---

## Safety

- Avoid running fans at very low values during sustained load.
- Start with moderate settings (40–60%) and monitor temperatures.
- You can always click **Rescan Hardware** to refresh detected sensors.
