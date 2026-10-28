#!/usr/bin/env python3
"""SmartBin hub for the Raspberry Pi 5.

- Reads the JSON lines the ESP32 prints on the USB serial port
- Works out a status per bin (OK / FILLING / FULL / CHECK / LID_OPEN / OFFLINE)
- Logs everything to SQLite (works offline)
- Serves a live dashboard + JSON API on http://<pi>:8080
- Optionally forwards readings to the cloud server (set SMARTBIN_CLOUD_URL)

Only dependency outside the standard library: pyserial.
"""

import json
import os
import queue
import sqlite3
import statistics
import threading
import time
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import serial

HERE = Path(__file__).resolve().parent


def env(name, default):
    return os.environ.get(name, default)


PORT = env("SMARTBIN_PORT", "/dev/smartbin")
BAUD = int(env("SMARTBIN_BAUD", "115200"))
HTTP_PORT = int(env("SMARTBIN_HTTP_PORT", "8080"))
DB_PATH = Path(env("SMARTBIN_DB", str(HERE.parent / "data" / "smartbin.db")))
FULL_PCT = float(env("SMARTBIN_FULL_PCT", "80"))
FILLING_PCT = float(env("SMARTBIN_FILLING_PCT", "50"))
BUCKET_L = float(env("SMARTBIN_BUCKET_L", "0.20"))     # usable bucket volume up to the rim
RHO_MIN = float(env("SMARTBIN_RHO_MIN", "15"))         # g/L below which a FULL bin is flagged CHECK
OFFLINE_S = float(env("SMARTBIN_OFFLINE_S", "10"))
CLOUD_URL = env("SMARTBIN_CLOUD_URL", "")
CLOUD_KEY = env("SMARTBIN_CLOUD_KEY", "")
CLOUD_EVERY_S = float(env("SMARTBIN_CLOUD_EVERY_S", "10"))
HUB_ID = env("SMARTBIN_HUB_ID", "HUB-01")

# ---------------------------------------------------------------- shared state
lock = threading.Lock()
latest = {}                 # bin id -> last reading dict (with status)
full_density = {}           # bin id -> deque of g/L seen while genuinely FULL
device = {"connected": False, "port": PORT, "info": None, "last_line": 0.0}
log_lines = deque(maxlen=40)
acks = queue.Queue()
ser = None
ser_write_lock = threading.Lock()
cmd_lock = threading.Lock()         # one command/ack exchange at a time


# ---------------------------------------------------------------- database
def db():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY, ts REAL, bin TEXT, dist_mm REAL, fill_pct REAL,
            weight_g REAL, lid TEXT, status TEXT, sent INTEGER DEFAULT 0)""")
        con.execute("""CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, ts REAL, bin TEXT, kind TEXT, detail TEXT, sent INTEGER DEFAULT 0)""")
        con.execute("CREATE INDEX IF NOT EXISTS readings_bin_ts ON readings(bin, ts)")


# ---------------------------------------------------------------- status rule
def rho_min_for(bin_id):
    """Per-bin learned threshold: half the median density of recent genuine FULL readings."""
    seen = full_density.get(bin_id)
    if seen and len(seen) >= 5:
        return 0.5 * statistics.median(seen)
    return RHO_MIN


def classify(r):
    if r.get("lid") == "open":
        return "LID_OPEN"
    fill = r.get("fill_pct")
    if fill is None:
        return "NO_READING"
    if fill < FILLING_PCT:
        return "OK"
    if fill < FULL_PCT:
        return "FILLING"
    w = r.get("weight_g")
    if w is None:                       # bin without a load cell (BIN-02 dummy)
        return "FULL"
    density = max(w, 0) / (fill / 100 * BUCKET_L)
    r["density_g_l"] = round(density, 1)
    if density < rho_min_for(r["bin"]):
        return "CHECK"                  # volume says full, weight says light: bridging
    full_density.setdefault(r["bin"], deque(maxlen=20)).append(density)
    return "FULL"


# ---------------------------------------------------------------- serial
def handle_line(line):
    now = time.time()
    device["last_line"] = now
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        log_lines.append({"ts": now, "text": line})
        return
    kind = msg.get("t")
    if kind == "reading":
        with lock:
            msg["status"] = classify(msg)
            msg["ts"] = now
            latest[msg["bin"]] = msg
        with db() as con:
            con.execute(
                "INSERT INTO readings (ts, bin, dist_mm, fill_pct, weight_g, lid, status) VALUES (?,?,?,?,?,?,?)",
                (now, msg["bin"], msg.get("dist_mm"), msg.get("fill_pct"), msg.get("weight_g"),
                 msg.get("lid"), msg["status"]))
        return
    log_lines.append({"ts": now, "text": line})
    if kind == "info":
        device["info"] = msg
    elif kind == "ack":
        acks.put(msg)
    if kind in ("lid", "boot"):
        with db() as con:
            con.execute("INSERT INTO events (ts, bin, kind, detail) VALUES (?,?,?,?)",
                        (now, msg.get("bin"), kind, line))


def serial_loop():
    global ser
    while True:
        try:
            s = serial.Serial()
            s.port, s.baudrate, s.timeout = PORT, BAUD, 1
            s.dtr = s.rts = False        # don't reset the ESP32 or hold it in the bootloader
            s.open()
            ser = s
            device["connected"] = True
            print(f"connected to {PORT}", flush=True)
            time.sleep(0.5)
            send_line("info")
            while True:
                raw = s.readline()
                if raw:
                    handle_line(raw.decode("utf-8", "replace").strip())
        except (serial.SerialException, OSError) as e:
            if device["connected"]:
                print(f"serial lost: {e}", flush=True)
            device["connected"] = False
            ser = None
            time.sleep(2)


def send_line(text):
    with ser_write_lock:
        if ser is None:
            raise RuntimeError("ESP32 not connected")
        ser.write((text.strip() + "\n").encode())


def run_command(text, wait_s=6.0):
    with cmd_lock:
        while not acks.empty():
            acks.get_nowait()
        send_line(text)
        try:
            return acks.get(timeout=wait_s)
        except queue.Empty:
            return {"t": "ack", "ok": False, "msg": "no reply from ESP32 (is the firmware flashed?)"}


# ---------------------------------------------------------------- cloud forwarder
def cloud_loop():
    while True:
        time.sleep(CLOUD_EVERY_S)
        try:
            with db() as con:
                rows = con.execute(
                    "SELECT id, ts, bin, dist_mm, fill_pct, weight_g, lid, status FROM readings "
                    "WHERE sent=0 ORDER BY id LIMIT 500").fetchall()
            if not rows:
                continue
            keys = ("id", "ts", "bin", "dist_mm", "fill_pct", "weight_g", "lid", "status")
            body = json.dumps({"hub": HUB_ID, "readings": [dict(zip(keys, r)) for r in rows]}).encode()
            req = urllib.request.Request(CLOUD_URL, data=body, method="POST",
                                         headers={"Content-Type": "application/json", "X-API-Key": CLOUD_KEY})
            with urllib.request.urlopen(req, timeout=15) as resp:
                if 200 <= resp.status < 300:
                    with db() as con:
                        con.execute("UPDATE readings SET sent=1 WHERE id BETWEEN ? AND ?", (rows[0][0], rows[-1][0]))
        except Exception as e:  # offline is normal; keep the backlog and retry
            print(f"cloud: {e}", flush=True)


# ---------------------------------------------------------------- HTTP
def state():
    now = time.time()
    with lock:
        bins = {}
        for b, r in latest.items():
            r = dict(r)
            r["age_s"] = round(now - r["ts"], 1)
            if r["age_s"] > OFFLINE_S:
                r["status"] = "OFFLINE"
            r["rho_min_g_l"] = round(rho_min_for(b), 1)
            bins[b] = r
    return {"hub": HUB_ID, "time": now, "bins": bins, "device": device,
            "log": list(log_lines)[-15:], "cloud": bool(CLOUD_URL)}


def history(bin_id, minutes):
    since = time.time() - minutes * 60
    with db() as con:
        rows = con.execute("SELECT ts, fill_pct, weight_g FROM readings WHERE bin=? AND ts>? ORDER BY ts",
                           (bin_id, since)).fetchall()
    step = max(1, len(rows) // 300)
    return [list(r) for r in rows[::step]]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            self.send(200, (HERE / "static" / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif u.path == "/api/state":
            self.send(200, state())
        elif u.path == "/api/history":
            q = parse_qs(u.query)
            self.send(200, history(q.get("bin", ["BIN-01"])[0], float(q.get("minutes", ["60"])[0])))
        else:
            self.send(404, {"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path != "/api/cmd":
            return self.send(404, {"error": "not found"})
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        try:
            text = json.loads(body)["cmd"]
        except (json.JSONDecodeError, KeyError, TypeError):
            text = body
        try:
            self.send(200, run_command(text))
        except RuntimeError as e:
            self.send(503, {"t": "ack", "ok": False, "msg": str(e)})


def main():
    init_db()
    threading.Thread(target=serial_loop, daemon=True).start()
    if CLOUD_URL:
        threading.Thread(target=cloud_loop, daemon=True).start()
    print(f"SmartBin hub: serial {PORT}, dashboard http://0.0.0.0:{HTTP_PORT}, db {DB_PATH}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", HTTP_PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
