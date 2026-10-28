---
title: Protocol and API
---

# Protocol and API

[← Home](index.md)

## ESP32 → Pi (USB serial, 115200 baud, one JSON object per line)

**Reading**, every 2 s for each bin:

```json
{"t":"reading","bin":"BIN-01","ms":123456,"dist_mm":61.3,"fill_pct":32.7,"weight_g":4.2,"lid":"closed","hand":false,"temp_c":25.0}
{"t":"reading","bin":"BIN-02","ms":123456,"dist_mm":74.0,"fill_pct":11.0,"weight_g":null,"lid":"closed","hand":false,"temp_c":25.0}
```

`dist_mm`, `fill_pct` and `weight_g` are `null` while the lid is open, for 1.5 s after it closes, if the sensor gave no echo, or if there's no load cell (BIN-02). `ms` is the ESP32's uptime.

**Lid event**: `{"t":"lid","bin":"BIN-01","state":"open","by":"ir","ms":123500}`. `by` is `ir`, `cmd` or `timeout`. These events also give the number of times each bin was used, which is useful for the prediction model.

**Boot / info**: `{"t":"boot","fw":"1.0.0"}`, followed by an `info` object with the calibration, lid angles and geometry.

**Reply to a command**: `{"t":"ack","cmd":"tare","ok":true,"msg":"offset=84213"}`

## Pi → ESP32 commands (plain text lines)

On the Pi, send any of these with `binctl <command>`:

| Command | What it does |
|---|---|
| `help` | list the commands |
| `info` | firmware, calibration, lid angles, H and d_full |
| `tare` | set zero weight (empty bucket in place) |
| `cal <grams>` | calibrate with a known mass in the bucket |
| `raw` | raw HX711 value (wiring check) |
| `open <1\|2>` / `close <1\|2>` | move a lid. A command-opened lid closes itself after 10 s |
| `lid <1\|2> open\|closed <deg>` | save a lid angle and move there |
| `servo <1\|2> <deg>` | move a servo without saving (for finding angles) |
| `temp <C>` | air temperature for the speed of sound (saved) |
| `rate <ms>` | reading interval, minimum 500 (not saved) |
| `reset` | restart the ESP32 |

## Hub HTTP API (port 8080)

| Method | Path | Returns |
|---|---|---|
| GET | `/` | dashboard |
| GET | `/api/state` | latest reading + status for each bin, device info, recent log |
| GET | `/api/history?bin=BIN-01&minutes=60` | `[[ts, fill_pct, weight_g], …]`, at most 300 points |
| POST | `/api/cmd` with body `{"cmd":"tare"}` | the ESP32's ack |

Status values: `OK` (< 50 %), `FILLING` (50–80 %), `FULL` (≥ 80 %), `CHECK` (full by volume but too light: bridging), `LID_OPEN`, `NO_READING`, `OFFLINE` (no reading for 10 s).

## Local database

`~/smartbin/data/smartbin.db` (SQLite) has the tables `readings(ts, bin, dist_mm, fill_pct, weight_g, lid, status, sent)` and `events(ts, bin, kind, detail)`. To export the readings for the AI work:

```bash
sqlite3 -header -csv ~/smartbin/data/smartbin.db "SELECT datetime(ts,'unixepoch','localtime') AS time, * FROM readings" > readings.csv
```

Copy the file to your laptop: `scp vishal@smartbin.local:readings.csv .`

## Cloud upload

When `SMARTBIN_CLOUD_URL` is set, every 10 s the hub POSTs up to 500 unsent readings:

```http
POST <SMARTBIN_CLOUD_URL>
Content-Type: application/json
X-API-Key: <SMARTBIN_CLOUD_KEY>

{"hub":"HUB-01","readings":[{"id":1,"ts":1793199522.39,"bin":"BIN-01","dist_mm":61.3,"fill_pct":32.7,"weight_g":4.2,"lid":"closed","status":"OK"}, …]}
```

Any 2xx response marks those rows as sent. On any other response, or with no internet, the same rows are retried next time. `id` is unique per hub, so the server can ignore duplicates.
