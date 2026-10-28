// SmartBin pin map and defaults. Keep in sync with docs/wiring.md.
#pragma once

// ---- Bin 1 (LEFT, fully wired) ----
#define BIN1_ID          "BIN-01"
#define BIN1_TRIG        32   // HC-SR04 TRIG (3.3 V out is enough to trigger)
#define BIN1_ECHO        33   // HC-SR04 ECHO through the 1k/2k divider (5 V -> 3.3 V)
#define BIN1_SERVO       19   // SG90 signal (orange)
#define BIN1_IR          23   // FC-51 OUT, LOW = hand detected (module powered from 3V3)
#define HX711_DT         22   // HX711 DT / DOUT
#define HX711_SCK        21   // HX711 SCK / PD_SCK

// ---- Bin 2 (RIGHT, dummy: no load cell, no IR) ----
#define BIN2_ID          "BIN-02"
#define BIN2_TRIG        25
#define BIN2_ECHO        26   // through its own 1k/2k divider
#define BIN2_SERVO       18

#define STATUS_LED       2    // on-board blue LED

// ---- Geometry (v2 bin, mm). Fill % = (H - d) / (H - D_FULL) * 100 ----
#define BIN_H_MM         80.4f   // sensor face -> empty bucket floor
#define BIN_DFULL_MM     22.0f   // sensor face -> bucket rim (reading when full)

// ---- Timing ----
#define REPORT_MS        2000    // one reading per bin every 2 s
#define LID_HOLD_MS      3000    // lid stays open this long after the hand leaves
#define SETTLE_MS        1500    // wait after the lid closes before trusting weight/distance
#define ECHO_TIMEOUT_US  12000   // ~2 m round trip; the bin is only 8 cm deep
#define PINGS            7       // median of this many pings per bin

// ---- Servo defaults (change at runtime with "lid <n> open|closed <deg>", saved to flash) ----
#define LID_CLOSED_DEG   10
#define LID_OPEN_DEG     100
#define SERVO_MIN_US     500     // SG90 pulse at 0 deg
#define SERVO_MAX_US     2400    // SG90 pulse at 180 deg

#define DEFAULT_TEMP_C   25.0f   // no temperature sensor yet; set with "temp <C>"
