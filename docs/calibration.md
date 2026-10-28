---
title: Calibration
---

# Calibration

[← Home](index.md) · Previous: [Raspberry Pi setup](pi-setup.md)

Run these on the Pi over SSH (or use the dashboard buttons). Everything you set here is saved in the ESP32's flash, so it survives reboots and reflashing.

## 1. Lid angles

Each SG90 needs two angles: **closed** and **open**. The defaults are closed 10° and open 100°. Your hinge will need slightly different values, and on one bin the servo may even turn the other way round (for example closed 170°, open 80°). The firmware works either way.

Use `servo` to try angles. It moves the servo but saves nothing:

```bash
binctl servo 1 10      # bin 1 to 10°
binctl servo 1 20      # a bit more
binctl servo 1 95      # try an open position
```

Move a few degrees at a time and watch for the lid hitting something. When you know the two angles, save them:

```bash
binctl lid 1 closed 12
binctl lid 1 open 95
binctl lid 2 closed 14
binctl lid 2 open 98
```

- **Closed:** the lid sits flat on the shell. If the servo **buzzes** while the lid is closed, it is pushing against the stop. Go 3–5° back.
- **Open:** wide enough to drop waste in, but not so far that the lid hits the servo or the other bin.

Test it: `binctl open 1`, then `binctl close 1`. A lid opened by command closes itself after 10 s. On bin 1, wave a hand in front of the IR sensor: the lid opens, and closes 3 s after your hand leaves.

## 2. Bin height (ultrasonic)

The firmware uses the v2 CAD values: **H = 80.4 mm** (sensor face to the empty bucket floor) and **d_full = 22 mm** (sensor face to the bucket rim), so

**Fill % = (80.4 − d) ÷ 58.4 × 100**

Check them on the real bins, with the bucket in place and the lid closed:

1. Empty bucket: `binctl state` → the distance should be about 80 mm. Write down what you get for each bin.
2. Lay a flat piece of card across the bucket rim → the distance should be about 22 mm.

If either is more than ~3 mm off, put your measured values in `firmware/src/config.h` (`BIN_H_MM`, `BIN_DFULL_MM`) and run `./scripts/flash.sh`.

Optional: the speed of sound depends on temperature, and the firmware uses 25 °C. On a hot day, set the room temperature:

```bash
binctl temp 32
```

## 3. Load cell (bin 1)

You need a known mass: a calibration weight, or something weighed on a kitchen scale (100–500 g is ideal for the 1 kg cell).

1. Put the **empty bucket** in place, close the lid and wait a few seconds.
2. Tare (this sets zero to "empty bucket"):

   ```bash
   binctl tare
   ```

3. Put the known mass in the bucket, for example 200 g, and wait 2 seconds.
4. Calibrate with that mass:

   ```bash
   binctl cal 200
   ```

5. Remove it. `binctl state` should show about **0 g**. Put it back: about **200 g**.

Check a few masses and record them for the report (Table 5.1):

| Actual (g) | Reading (g) | Error (g) |
|---|---|---|
| 100 | | |
| 200 | | |
| 500 | | |
| 1000 | | |

Tips:

- Leave the system on for 5–10 minutes before calibrating (the load cell drifts a little while it warms up).
- Weight readings pause while the lid moves and for 1.5 s afterwards, so the servo doesn't disturb them.
- If the reading isn't stable, something is touching the pan or bucket, or a load-cell wire is loose.
- Run `binctl tare` again whenever you change the empty bucket.

## 4. Bridging (CHECK) threshold

When the ultrasonic sensor says a bin is **full** (≥ 80 %) but it weighs very little, the hub marks it **CHECK** instead of FULL. A flat box lying across the top is the typical case.

The rule uses density, the weight divided by the filled volume:

- Start: CHECK if the density is below `SMARTBIN_RHO_MIN` (15 g/L, set in `hub/hub.env`).
- After 5 genuine FULL readings, the hub learns its own threshold: **half the median density of the recent FULL readings** for that bin (the per-bin learned ρ_min from the IDF).

Test it (Table 5.2):

1. Fill bin 1 with loose paper to the rim → **FULL**.
2. Empty it, then lay a flat cardboard sheet or an empty box across the top → **CHECK**.

The dashboard shows the measured density and the current threshold on bin 1's card. If real paper is flagged CHECK, lower `SMARTBIN_RHO_MIN` and run `sudo systemctl restart smartbin-hub`.

Bin 2 has no load cell, so it can only ever show FULL, never CHECK.
