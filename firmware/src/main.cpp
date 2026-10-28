// SmartBin firmware, one ESP32 for both bins.
//
// Bin 1 (left):  HC-SR04 + HX711/load cell + SG90 lid + FC-51 IR hand sensor
// Bin 2 (right): HC-SR04 + SG90 lid (dummy: no load cell, no IR)
//
// Talks to the Raspberry Pi over the USB cable at 115200 baud, one JSON object per line.
// Commands from the Pi are plain text lines; send "help" for the list.

#include <Arduino.h>
#include <Preferences.h>
#if __has_include(<esp_arduino_version.h>)
#include <esp_arduino_version.h>
#endif
#include "config.h"

#define FW_VERSION "1.0.0"

struct Bin {
  const char *id;
  int trig, echo, servoPin, ledcCh;
  int irPin;            // -1 = no IR sensor
  bool hasScale;
  int closedDeg, openDeg, curDeg;
  bool lidOpen;         // the members below start at zero (not listed in the initialisers)
  bool manual;          // opened by a command, not by a hand
  uint32_t lastHandMs, openedMs, closedMs;
};

Bin bins[2] = {
  {BIN1_ID, BIN1_TRIG, BIN1_ECHO, BIN1_SERVO, 0, BIN1_IR, true,  LID_CLOSED_DEG, LID_OPEN_DEG, LID_CLOSED_DEG},
  {BIN2_ID, BIN2_TRIG, BIN2_ECHO, BIN2_SERVO, 1, -1,      false, LID_CLOSED_DEG, LID_OPEN_DEG, LID_CLOSED_DEG},
};

Preferences prefs;
float tempC = DEFAULT_TEMP_C;
uint32_t reportMs = REPORT_MS;
uint32_t lastReport = 0;
const uint32_t MANUAL_OPEN_MS = 10000;  // a lid opened by command closes itself after 10 s

// ---------------------------------------------------------------- HX711 (bit-banged)
long hxOffset = 0;
float hxScale = 0;               // counts per gram; 0 = not calibrated
const int HX_BUF = 10;
long hxBuf[HX_BUF];
int hxCount = 0, hxHead = 0;
uint32_t hxLastSample = 0;
portMUX_TYPE hxMux = portMUX_INITIALIZER_UNLOCKED;

long hxReadRaw() {               // call only when DT is LOW (data ready)
  uint32_t v = 0;
  portENTER_CRITICAL(&hxMux);    // SCK high > 60 us would power the chip down
  for (int i = 0; i < 24; i++) {
    digitalWrite(HX711_SCK, HIGH);
    delayMicroseconds(1);
    v = (v << 1) | digitalRead(HX711_DT);
    digitalWrite(HX711_SCK, LOW);
    delayMicroseconds(1);
  }
  digitalWrite(HX711_SCK, HIGH);  // 25th pulse: channel A, gain 128
  delayMicroseconds(1);
  digitalWrite(HX711_SCK, LOW);
  portEXIT_CRITICAL(&hxMux);
  if (v & 0x800000) v |= 0xFF000000;
  return (int32_t)v;
}

void hxPoll() {
  if (digitalRead(HX711_DT) != LOW) return;
  hxBuf[hxHead] = hxReadRaw();
  hxHead = (hxHead + 1) % HX_BUF;
  if (hxCount < HX_BUF) hxCount++;
  hxLastSample = millis();
}

void hxClear() { hxCount = 0; hxHead = 0; }
bool hxAlive() { return millis() - hxLastSample < 1000; }

// Trimmed mean of the buffer (drops the min and max).
bool hxAverage(long &out) {
  if (hxCount < 5) return false;
  long mn = LONG_MAX, mx = LONG_MIN;
  int64_t sum = 0;
  for (int i = 0; i < hxCount; i++) {
    sum += hxBuf[i];
    mn = min(mn, hxBuf[i]);
    mx = max(mx, hxBuf[i]);
  }
  out = (long)((sum - mn - mx) / (hxCount - 2));
  return true;
}

// Blocking average for tare/cal: waits for fresh samples.
bool hxAverageFresh(long &out, int n = 16) {
  int64_t sum = 0;
  int got = 0;
  uint32_t t0 = millis();
  while (got < n && millis() - t0 < 4000) {
    if (digitalRead(HX711_DT) == LOW) { sum += hxReadRaw(); got++; }
    delay(1);
  }
  if (got < n) return false;
  out = (long)(sum / n);
  return true;
}

// ---------------------------------------------------------------- Servo (LEDC, 50 Hz)
void servoAttach(Bin &b) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(b.servoPin, 50, 16);
#else
  ledcSetup(b.ledcCh, 50, 16);
  ledcAttachPin(b.servoPin, b.ledcCh);
#endif
}

void servoDuty(Bin &b, uint32_t duty) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(b.servoPin, duty);
#else
  ledcWrite(b.ledcCh, duty);
#endif
}

void servoDeg(Bin &b, int deg) {
  deg = constrain(deg, 0, 180);
  uint32_t us = SERVO_MIN_US + (uint32_t)(SERVO_MAX_US - SERVO_MIN_US) * deg / 180;
  servoDuty(b, us * 65535UL / 20000UL);
  b.curDeg = deg;
}

void servoRelax(Bin &b) { servoDuty(b, 0); }  // no pulses: no jitter, no current, no HX711 noise

// Slow sweep keeps the current spike low (both servos share the Pi's USB port).
void servoSweep(Bin &b, int target) {
  int step = target > b.curDeg ? 2 : -2;
  while (abs(target - b.curDeg) > 2) {
    servoDeg(b, b.curDeg + step);
    delay(12);
    hxPoll();
  }
  servoDeg(b, target);
}

void emitLid(Bin &b, const char *by) {
  Serial.printf("{\"t\":\"lid\",\"bin\":\"%s\",\"state\":\"%s\",\"by\":\"%s\",\"ms\":%lu}\n",
                b.id, b.lidOpen ? "open" : "closed", by, (unsigned long)millis());
}

void openLid(Bin &b, bool manual, const char *by) {
  if (b.lidOpen) { b.manual = b.manual && manual; return; }
  servoSweep(b, b.openDeg);       // stays powered so the lid is held open
  b.lidOpen = true;
  b.manual = manual;
  b.openedMs = millis();
  if (b.hasScale) hxClear();
  emitLid(b, by);
}

void closeLid(Bin &b, const char *by) {
  if (!b.lidOpen) return;
  servoSweep(b, b.closedDeg);
  delay(300);
  servoRelax(b);
  b.lidOpen = false;
  b.manual = false;
  b.closedMs = millis();
  if (b.hasScale) hxClear();
  emitLid(b, by);
}

void updateLid(Bin &b) {
  uint32_t now = millis();
  if (b.irPin >= 0 && digitalRead(b.irPin) == LOW) {
    b.lastHandMs = now;
    if (!b.lidOpen) openLid(b, false, "ir");
    b.manual = false;
  }
  if (!b.lidOpen) return;
  if (b.manual) {
    if (now - b.openedMs > MANUAL_OPEN_MS) closeLid(b, "timeout");
  } else if (now - b.lastHandMs > LID_HOLD_MS) {
    closeLid(b, "ir");
  }
}

// ---------------------------------------------------------------- Ultrasonic
float pingOnce(const Bin &b) {
  digitalWrite(b.trig, LOW);
  delayMicroseconds(4);
  digitalWrite(b.trig, HIGH);
  delayMicroseconds(10);
  digitalWrite(b.trig, LOW);
  unsigned long us = pulseIn(b.echo, HIGH, ECHO_TIMEOUT_US);
  if (us == 0) return -1;
  float mmPerUs = (331.3f + 0.606f * tempC) / 1000.0f;
  return us * mmPerUs / 2.0f;
}

// Median of PINGS readings; -1 if most pings failed.
float distanceMm(const Bin &b) {
  float v[PINGS];
  int n = 0;
  for (int i = 0; i < PINGS; i++) {
    float d = pingOnce(b);
    if (d > 0) v[n++] = d;
    delay(15);                    // let echoes die out (the other bin is right next door)
    hxPoll();
  }
  if (n < PINGS / 2 + 1) return -1;
  for (int i = 1; i < n; i++)     // insertion sort, n <= 7
    for (int j = i; j > 0 && v[j - 1] > v[j]; j--) { float t = v[j]; v[j] = v[j - 1]; v[j - 1] = t; }
  return v[n / 2];
}

// ---------------------------------------------------------------- Reporting
// Writes a number or null into buf.
const char *num(char *buf, size_t n, float v, bool ok, int dec = 1) {
  if (!ok) snprintf(buf, n, "null");
  else snprintf(buf, n, "%.*f", dec, v);
  return buf;
}

void report(Bin &b) {
  uint32_t now = millis();
  bool settled = !b.lidOpen && now - b.closedMs > SETTLE_MS;
  float d = settled ? distanceMm(b) : -1;
  bool dOk = d > 0;
  float fill = (BIN_H_MM - d) / (BIN_H_MM - BIN_DFULL_MM) * 100.0f;
  fill = constrain(fill, 0.0f, 100.0f);

  bool wOk = false;
  float w = 0;
  long avg;
  if (b.hasScale && settled && hxScale != 0 && hxAverage(avg)) {
    w = (avg - hxOffset) / hxScale;
    wOk = true;
  }

  char sd[16], sf[16], sw[16];
  Serial.printf("{\"t\":\"reading\",\"bin\":\"%s\",\"ms\":%lu,\"dist_mm\":%s,\"fill_pct\":%s,"
                "\"weight_g\":%s,\"lid\":\"%s\",\"hand\":%s,\"temp_c\":%.1f}\n",
                b.id, (unsigned long)now, num(sd, 16, d, dOk), num(sf, 16, fill, dOk),
                num(sw, 16, w, wOk), b.lidOpen ? "open" : "closed",
                (b.irPin >= 0 && digitalRead(b.irPin) == LOW) ? "true" : "false", tempC);
}

void printInfo() {
  Serial.printf("{\"t\":\"info\",\"fw\":\"%s\",\"bins\":[\"%s\",\"%s\"],\"h_mm\":%.1f,\"dfull_mm\":%.1f,"
                "\"hx_alive\":%s,\"hx_offset\":%ld,\"hx_scale\":%.4f,\"calibrated\":%s,"
                "\"lid1\":[%d,%d],\"lid2\":[%d,%d],\"temp_c\":%.1f,\"rate_ms\":%lu}\n",
                FW_VERSION, bins[0].id, bins[1].id, BIN_H_MM, BIN_DFULL_MM,
                hxAlive() ? "true" : "false", hxOffset, hxScale, hxScale != 0 ? "true" : "false",
                bins[0].closedDeg, bins[0].openDeg, bins[1].closedDeg, bins[1].openDeg,
                tempC, (unsigned long)reportMs);
}

void ack(const char *cmd, bool ok, const char *msg = "") {
  Serial.printf("{\"t\":\"ack\",\"cmd\":\"%s\",\"ok\":%s,\"msg\":\"%s\"}\n", cmd, ok ? "true" : "false", msg);
}

// ---------------------------------------------------------------- Settings in flash
void loadPrefs() {
  prefs.begin("smartbin", true);
  hxOffset = prefs.getLong("hx_off", 0);
  hxScale = prefs.getFloat("hx_scale", 0);
  bins[0].closedDeg = prefs.getInt("l1c", LID_CLOSED_DEG);
  bins[0].openDeg = prefs.getInt("l1o", LID_OPEN_DEG);
  bins[1].closedDeg = prefs.getInt("l2c", LID_CLOSED_DEG);
  bins[1].openDeg = prefs.getInt("l2o", LID_OPEN_DEG);
  tempC = prefs.getFloat("temp", DEFAULT_TEMP_C);
  prefs.end();
}

void savePrefs() {
  prefs.begin("smartbin", false);
  prefs.putLong("hx_off", hxOffset);
  prefs.putFloat("hx_scale", hxScale);
  prefs.putInt("l1c", bins[0].closedDeg);
  prefs.putInt("l1o", bins[0].openDeg);
  prefs.putInt("l2c", bins[1].closedDeg);
  prefs.putInt("l2o", bins[1].openDeg);
  prefs.putFloat("temp", tempC);
  prefs.end();
}

// ---------------------------------------------------------------- Commands
const char *HELP =
  "{\"t\":\"help\",\"cmds\":[\"info\",\"tare\",\"cal <grams>\",\"raw\",\"open <1|2>\",\"close <1|2>\","
  "\"lid <1|2> open|closed <deg>\",\"servo <1|2> <deg>\",\"temp <C>\",\"rate <ms>\",\"reset\"]}";

Bin *binArg(const char *s) {
  int n = atoi(s);
  return (n == 1 || n == 2) ? &bins[n - 1] : nullptr;
}

void handle(char *line) {
  char *cmd = strtok(line, " \t\r");
  if (!cmd) return;
  char *a1 = strtok(nullptr, " \t\r");
  char *a2 = strtok(nullptr, " \t\r");
  char *a3 = strtok(nullptr, " \t\r");
  char msg[96];

  if (!strcmp(cmd, "help")) {
    Serial.println(HELP);
  } else if (!strcmp(cmd, "info")) {
    printInfo();
  } else if (!strcmp(cmd, "tare")) {
    long avg;
    if (!hxAverageFresh(avg)) return ack(cmd, false, "HX711 not responding, check DT/SCK/VCC");
    hxOffset = avg;
    savePrefs();
    hxClear();
    snprintf(msg, sizeof msg, "offset=%ld", hxOffset);
    ack(cmd, true, msg);
  } else if (!strcmp(cmd, "cal")) {
    float g = a1 ? atof(a1) : 0;
    long avg;
    if (g <= 0) return ack(cmd, false, "usage: cal <grams of the weight on the pan>");
    if (!hxAverageFresh(avg)) return ack(cmd, false, "HX711 not responding");
    if (avg == hxOffset) return ack(cmd, false, "no change from tare, is the weight on?");
    hxScale = (avg - hxOffset) / g;
    savePrefs();
    hxClear();
    snprintf(msg, sizeof msg, "scale=%.4f counts/g", hxScale);
    ack(cmd, true, msg);
  } else if (!strcmp(cmd, "raw")) {
    long avg;
    if (!hxAverageFresh(avg, 8)) return ack(cmd, false, "HX711 not responding");
    snprintf(msg, sizeof msg, "raw=%ld offset=%ld", avg, hxOffset);
    ack(cmd, true, msg);
  } else if (!strcmp(cmd, "open") || !strcmp(cmd, "close")) {
    Bin *b = a1 ? binArg(a1) : nullptr;
    if (!b) return ack(cmd, false, "usage: open|close <1|2>");
    if (cmd[0] == 'o') openLid(*b, true, "cmd");
    else closeLid(*b, "cmd");
    ack(cmd, true, b->id);
  } else if (!strcmp(cmd, "lid")) {
    Bin *b = a1 ? binArg(a1) : nullptr;
    if (!b || !a2 || !a3) return ack(cmd, false, "usage: lid <1|2> open|closed <deg>");
    int deg = constrain(atoi(a3), 0, 180);
    if (!strcmp(a2, "open")) b->openDeg = deg;
    else if (!strcmp(a2, "closed")) b->closedDeg = deg;
    else return ack(cmd, false, "second word must be open or closed");
    savePrefs();
    servoSweep(*b, deg);          // show the new position
    b->lidOpen = !strcmp(a2, "open");
    b->manual = b->lidOpen;
    b->openedMs = millis();
    if (!b->lidOpen) { delay(300); servoRelax(*b); b->closedMs = millis(); }
    snprintf(msg, sizeof msg, "%s %s=%d saved", b->id, a2, deg);
    ack(cmd, true, msg);
  } else if (!strcmp(cmd, "servo")) {
    Bin *b = a1 ? binArg(a1) : nullptr;
    if (!b || !a2) return ack(cmd, false, "usage: servo <1|2> <deg>");
    servoSweep(*b, atoi(a2));
    snprintf(msg, sizeof msg, "%s at %d deg (not saved)", b->id, b->curDeg);
    ack(cmd, true, msg);
  } else if (!strcmp(cmd, "temp")) {
    if (!a1) return ack(cmd, false, "usage: temp <C>");
    tempC = atof(a1);
    savePrefs();
    ack(cmd, true, a1);
  } else if (!strcmp(cmd, "rate")) {
    long ms = a1 ? atol(a1) : 0;
    if (ms < 500) return ack(cmd, false, "usage: rate <ms>, minimum 500");
    reportMs = ms;
    ack(cmd, true, a1);
  } else if (!strcmp(cmd, "reset")) {
    ack(cmd, true, "restarting");
    delay(100);
    ESP.restart();
  } else {
    ack(cmd, false, "unknown command, send help");
  }
}

void readCommands() {
  static char buf[96];
  static int len = 0;
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      buf[len] = 0;
      handle(buf);
      len = 0;
    } else if (len < (int)sizeof buf - 1) {
      buf[len++] = c;
    }
  }
}

// ---------------------------------------------------------------- Arduino
void setup() {
  Serial.begin(115200);
  pinMode(STATUS_LED, OUTPUT);
  pinMode(HX711_SCK, OUTPUT);
  digitalWrite(HX711_SCK, LOW);
  pinMode(HX711_DT, INPUT);
  for (Bin &b : bins) {
    pinMode(b.trig, OUTPUT);
    digitalWrite(b.trig, LOW);
    pinMode(b.echo, INPUT);
    if (b.irPin >= 0) pinMode(b.irPin, INPUT_PULLUP);
  }
  loadPrefs();

  // Park both lids closed, one at a time (current), then relax the servos.
  for (Bin &b : bins) {
    servoAttach(b);
    servoDeg(b, b.closedDeg);
    delay(500);
    servoRelax(b);
    b.closedMs = millis();
  }

  uint32_t t0 = millis();         // give the HX711 time to report in
  while (millis() - t0 < 1000) hxPoll();

  Serial.printf("{\"t\":\"boot\",\"fw\":\"%s\"}\n", FW_VERSION);
  printInfo();
}

void loop() {
  readCommands();
  hxPoll();
  for (Bin &b : bins) updateLid(b);

  digitalWrite(STATUS_LED, bins[0].lidOpen || bins[1].lidOpen);

  if (millis() - lastReport >= reportMs) {
    lastReport = millis();
    report(bins[0]);
    report(bins[1]);
  }
}
