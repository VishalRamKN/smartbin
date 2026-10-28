---
title: Home
---

# SmartBin: build and setup guide

**AI-Based Smart Garbage Bin Fill-Level Monitoring Robot.** VIT University, SENSE, B.Tech ECE (Robotics & Automation project).
Team: Vishal Ram K N, Thayanandhan P, Varun Vaishnav. Guide: Dr Kathirvelan J.

Each bin measures how full it is in two ways: an **ultrasonic sensor** for volume and a **load cell** for weight. When the two disagree (full by volume, but far too light), the bin is flagged **CHECK** instead of FULL. This catches a flat box bridging the top of the bin.

```
 Bin 1 (left): HC-SR04 + load cell/HX711 + SG90 lid + IR hand sensor ─┐
                                                                      ├─ ESP32 DevKit 38-pin ──USB──> Raspberry Pi 5 ──> dashboard :8080
 Bin 2 (right, dummy): HC-SR04 + SG90 lid ────────────────────────────┘     (firmware/)          (hub/: SQLite log,        └──> cloud (later)
                                                                                                   CHECK rule, API)
```

## Setup, in order

1. **[Wiring](wiring.md)**: pin table, diagram, perfboard layout, checks before power-up
2. **[Raspberry Pi setup](pi-setup.md)**: SD card, SSH, one setup script, flash the ESP32 from the Pi
3. **[Calibration](calibration.md)**: lid angles, bin height, tare and the load-cell scale, the bridging threshold
4. **[Protocol and API](protocol.md)**: serial messages, commands, HTTP API, database export, cloud format

## Quick start (on the Pi, over SSH)

```bash
git clone https://github.com/VishalRamKN/smartbin.git ~/smartbin
cd ~/smartbin && ./scripts/setup_pi.sh     # then log out and SSH in again
./scripts/flash.sh                         # build + flash the ESP32 over USB
binctl watch                               # live readings
```

Dashboard: **http://smartbin.local:8080**

## What's in the repository

| Folder | What it is |
|---|---|
| [`firmware/`](https://github.com/VishalRamKN/smartbin/tree/main/firmware) | ESP32 code (PlatformIO, Arduino framework, no external libraries). Pins and geometry are in `src/config.h` |
| [`hub/`](https://github.com/VishalRamKN/smartbin/tree/main/hub) | Raspberry Pi service: serial reader, status/CHECK rule, SQLite log, dashboard, optional cloud upload |
| [`scripts/`](https://github.com/VishalRamKN/smartbin/tree/main/scripts) | `setup_pi.sh`, `flash.sh`, `binctl`, the udev rule and the systemd unit |
| [`docs/`](https://github.com/VishalRamKN/smartbin/tree/main/docs) | this site |
