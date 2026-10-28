---
title: Raspberry Pi setup
---

# Raspberry Pi 5 setup (over SSH)

[← Home](index.md) · Previous: [Wiring](wiring.md) · Next: [Calibration](calibration.md)

After step 1 you do everything from your laptop over SSH. The Pi needs no monitor or keyboard.

**You need:** Raspberry Pi 5 with its active cooler, a microSD card (32 GB+, A2), the **official 27 W USB-C supply**, a USB **data** cable for the ESP32, and a laptop on the same network as the Pi. A phone hotspot is the easiest network: college Wi-Fi often blocks devices from seeing each other.

---

## 1. Flash the SD card (on your laptop)

1. Install **Raspberry Pi Imager** (on Fedora: `sudo dnf install rpi-imager`, or the Flatpak).
2. Device: **Raspberry Pi 5**. OS: **Raspberry Pi OS Lite (64-bit)** (under "Raspberry Pi OS (other)"). Storage: your SD card.
3. When it asks about OS customisation, choose **Edit settings** and set:
   - **Hostname:** `smartbin`
   - **Username / password:** your choice. These steps use `vishal`; use your own name wherever you see it.
   - **Wireless LAN:** your hotspot's SSID and password, **Wireless LAN country: IN**
   - **Locale:** Asia/Kolkata
   - **Services tab → Enable SSH** → "Use password authentication" (or paste your laptop's public key from `~/.ssh/id_ed25519.pub`)
4. Write the card, put it in the Pi, and power it on. The first boot takes about 2 minutes.

## 2. SSH in

From your laptop:

```bash
ssh vishal@smartbin.local
```

Type `yes` the first time to accept the host key.

If `smartbin.local` isn't found, look up the Pi's IP address in your hotspot's list of connected devices and use `ssh vishal@<ip>` instead.

**Tip:** VS Code can open the Pi directly. Install the "Remote - SSH" extension and connect to `vishal@smartbin.local`, and you get the Pi's files and a terminal inside VS Code.

## 3. Update the Pi

```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

Wait about 30 seconds, then SSH in again.

## 4. Get the code and run the setup script

```bash
sudo apt install -y git
git clone https://github.com/VishalRamKN/smartbin.git ~/smartbin
cd ~/smartbin
./scripts/setup_pi.sh
```

The script is safe to run again. It does the following:

1. installs `git`, `python3-venv`, `sqlite3`, `curl`
2. adds you to the `dialout` group (permission to use the serial port)
3. creates `~/smartbin/.venv` with `pyserial` and **PlatformIO** (used to build and flash the ESP32 from the Pi)
4. installs a udev rule so the ESP32 always appears as **`/dev/smartbin`**, whichever USB port it's in
5. creates `hub/hub.env` (settings) and the **`smartbin-hub`** systemd service, which starts on every boot
6. installs the `binctl` command

Then **log out and SSH in again** so the `dialout` group takes effect:

```bash
exit
ssh vishal@smartbin.local
groups        # should list dialout
```

## 5. Plug in the ESP32 and flash the firmware

Plug the ESP32 into any of the Pi's USB ports. Wiring can come later: flashing a bare ESP32 is the first test.

```bash
ls -l /dev/smartbin          # → /dev/smartbin -> ttyUSB0 (or ttyACM0)
cd ~/smartbin
./scripts/flash.sh
```

The **first build downloads the ESP32 toolchain (about 300 MB) and takes 5–10 minutes**. Later builds take under a minute.
`flash.sh` stops the hub while it uses the serial port, and restarts it when flashing is done.

If the upload sticks at `Connecting........`, hold the **BOOT** button on the ESP32 until the percentages start.

## 6. Check that it works

```bash
binctl state
```

Expected output with a bare ESP32:

```
ESP32 connected on /dev/smartbin
  BIN-01  NO_READING fill       --  dist        --  weight        --  lid closed (0.8 s ago)
  BIN-02  NO_READING fill       --  dist        --  weight        --  lid closed (0.8 s ago)
```

Useful commands:

```bash
binctl watch                          # live view, refreshes every 2 s (Ctrl+C to quit)
binctl help                           # list of ESP32 commands
binctl info                           # firmware version, calibration, lid angles
journalctl -u smartbin-hub -f         # hub log
sudo systemctl restart smartbin-hub   # after editing hub/hub.env
./scripts/flash.sh monitor            # raw serial output from the ESP32 (stops the hub meanwhile)
```

**Dashboard:** open **http://smartbin.local:8080** in your laptop's browser. It shows a card per bin with the fill bar, distance, weight, lid state, status and the last hour as a graph, plus buttons for the lids, tare and calibration.

If the browser can't reach it (some networks block it), tunnel it through SSH and open http://localhost:8080 instead:

```bash
ssh -L 8080:localhost:8080 vishal@smartbin.local
```

Now wire the sensors one at a time ([wiring guide, section 6](wiring.md#6-bring-it-up-one-module-at-a-time)), then [calibrate](calibration.md).

## 7. Updating the code later

After you push changes to GitHub:

```bash
cd ~/smartbin
git pull
./scripts/flash.sh                    # only if firmware/ changed
sudo systemctl restart smartbin-hub   # only if hub/ changed
```

Calibration and lid angles are stored in the ESP32's flash memory, so reflashing keeps them.

## 8. Sending data to the cloud (later)

When the Lightsail server has an endpoint, set it in `~/smartbin/hub/hub.env`:

```
SMARTBIN_CLOUD_URL=https://<your-server>/api/ingest
SMARTBIN_CLOUD_KEY=<a long random string>
```

Then run `sudo systemctl restart smartbin-hub`. Readings are always kept in `~/smartbin/data/smartbin.db` first. If the internet drops, the backlog is sent later. The request format is in [protocol](protocol.md#cloud-upload).

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `/dev/smartbin` doesn't exist | Run `dmesg \| tail` right after plugging in. If nothing appears, the cable is **charge-only**: use a data cable. If you see a `ttyUSB`/`ttyACM` line but no symlink, your board has an unusual USB chip. Send the output of `udevadm info -q property -n /dev/ttyUSB0 \| grep ID_` to the team so the rule can be extended. |
| `Permission denied: /dev/smartbin` | Log out and SSH in again after the setup script (the `dialout` group). |
| Flash fails with "port is busy" | Something else has the port open: `sudo systemctl stop smartbin-hub` (flash.sh normally does this), and close any `screen`/`minicom` session. |
| `binctl` says "Hub not running" | `sudo systemctl status smartbin-hub` and `journalctl -u smartbin-hub -n 50`. |
| ESP32 resets when a lid moves (a `boot` line appears in `binctl watch`) | 470 µF capacitor missing or reversed, or a weak supply. Use the official 27 W Pi supply: with other supplies the Pi limits its USB ports to 600 mA. |
| Distance stays `--` | TRIG/ECHO swapped, divider wrong, or the lid has just moved (readings pause for 1.5 s after the lid closes). Check that the divider node reads ~3.3 V to GND while the sensor runs. |
| Distance jumps around | The sensor isn't square to the bucket floor, the bucket is nearly empty and the echo comes off a wall, or the other bin's echo is getting in. Raise `PINGS` in `config.h`. |
| `hx_alive: false` | DT/SCK swapped, HX711 VCC not on 3V3, or a loose GND. |
| Weight drifts slowly | Normal for a few minutes after power-up. Tare again once it's warm. If it never settles, something touches the pan or bucket (see the 2.6 mm gap in the CAD notes). |
| Servo buzzes at closed | The closed angle presses the lid into its stop. Lower it by 3–5° (see [calibration](calibration.md#1-lid-angles)). |
| `smartbin.local` not found | Use the IP address. On Fedora, check that `avahi-daemon` is running on the laptop. |
