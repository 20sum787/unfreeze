#pragma once
#include <stdint.h>
#include "deployment_config.h"

// UNO Q Qwiic is the STM32's Wire1. Core variant owns the physical pin mux.
// D0/D1, SPI chip selects and MCU PWM channels are unused by this application.
#define UNFREEZE_QWIIC Wire1
// Set to 0 to remove periodic Serial Monitor work and its dedicated stack.
#define UNFREEZE_DEBUG 1
#if UNFREEZE_DEBUG
#define DEBUG_PRINTLN(message) Monitor.println(message)
#else
#define DEBUG_PRINTLN(message) do {} while (0)
#endif

namespace Config {
// 7-bit I2C. For two Movement boards use distinct SDO strap settings.
constexpr uint8_t Movement = 0x6B;
constexpr uint8_t Movement2 = 0x6A;
constexpr uint8_t Buzzer = 0x1E;
constexpr uint8_t Vibro = 0x38;
constexpr int DefaultSampleHz = 64;
constexpr bool supportedRate(int hz) { return hz == 25 || hz == 50 || hz == 64 || hz == 100; }
constexpr uint8_t FifoRows = 32;     // Per IMU, 500 ms at 64 Hz.
constexpr uint8_t RowsPerRpc = 2;    // Keep response within RouterBridge's 256-byte packet.
constexpr unsigned RpcTextBytes = 224;
constexpr uint32_t ProbeMs = 2000;
constexpr uint32_t DiagnosticMs = 2000;
constexpr unsigned DiagnosticStackBytes = 4096;
constexpr unsigned MonitorBaud = 115200;   // Legacy argument to the virtual App Lab Monitor.
constexpr unsigned RouterBaud = 115200;    // Board-selected internal router UART, independent of D0/D1.

constexpr unsigned BeatCount = 4;
constexpr unsigned VibroPulseMs = 180;
constexpr int FreezeHoldMs = 5000;
constexpr int FreezeAlarmMs = 5000;
constexpr int FreezeAlarmHz = 2400;
constexpr unsigned BuzzerPulseMs = 100;
constexpr unsigned LateBeatMs = 35;
constexpr int BpmMin = 45, BpmMax = 150;
constexpr int DriveMin = 25, DriveMax = 50, DriveStep = 5;
constexpr int ToneMin = 200, ToneMax = 3000;
constexpr int BenchDrive = 40, BenchHz = 440, BenchPulseMs = 1000;

// RPC names form the wire protocol with python/board.py.
namespace Rpc {
constexpr char Status[] = "uf_status", Samples[] = "uf_samples", Samples2[] = "uf_samples2";
constexpr char Rate[] = "uf_rate", Vibro[] = "uf_vibro", Buzzer[] = "uf_buzzer";
constexpr char FreezeHold[] = "uf_freeze_hold", FreezePulses[] = "uf_freeze_pulses", FreezeAlarm[] = "uf_freeze_alarm";
constexpr char Stop[] = "uf_stop", Bench[] = "uf_bench";
}
static_assert(Movement != Movement2 && Movement != Buzzer && Movement != Vibro &&
              Movement2 != Buzzer && Movement2 != Vibro && Vibro != Buzzer,
              "configured Qwiic addresses collide");
static_assert(supportedRate(DefaultSampleHz), "unsupported acquisition rate");
}
