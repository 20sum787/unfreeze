#include <Arduino_RouterBridge.h>
#include "CueOutputs.h"
#include "MovementStream.h"

struct k_mutex BoardIO::mutex;
MovementStream preferred(Config::Movement), alternate(Config::Movement2);
MovementStream *primary = nullptr, *secondary = nullptr;
int primaryAddress = 0;
CueOutputs cues;
int sampleHz = Config::DefaultSampleHz;
uint32_t nextReadUs, nextProbeMs, sequence = 0;

void refreshModules() {
  preferred.refresh();
  alternate.refresh();
  // Assign once per MCU boot so removal of a body-worn sensor cannot silently
  // substitute a sensor from another body site in the model input.
  if (!primary && (preferred.online || alternate.online)) {
    primary = preferred.online ? &preferred : &alternate;
    secondary = preferred.online ? &alternate : &preferred;
    primaryAddress = preferred.online ? Config::Movement : Config::Movement2;
  }
  cues.refresh();
}

String statusJson() {
  BoardIO::Lock lock;
  char buf[Config::RpcTextBytes];
  snprintf(buf, sizeof(buf),
           "{\"version\":1,\"cueRev\":3,\"holdMs\":%d,\"mcuMs\":%lu,\"hz\":%d,\"imuAddr\":%d,\"imu\":%s,\"imu2\":%s,\"vibro\":%s,\"buzzer\":%s,"
           "\"samples\":%lu,\"missed\":%lu,\"vibroActive\":%s,\"buzzerActive\":%s}",
           Config::FreezeHoldMs, (unsigned long)millis(), sampleHz, primaryAddress,
           primary && primary->online ? "true" : "false", secondary && secondary->online ? "true" : "false",
           cues.hasVibro ? "true" : "false", cues.hasBuzzer ? "true" : "false",
           (unsigned long)(primary ? primary->samples : 0), (unsigned long)(primary ? primary->missed : 0),
           cues.vibroActive() ? "true" : "false", cues.buzzerActive() ? "true" : "false");
  return String(buf);
}

String readPrimary() {
  BoardIO::Lock lock;
  return primary ? primary->drain() : String("{\"rows\":[],\"dropped\":0}");
}
String readSecondary() {
  BoardIO::Lock lock;
  return secondary ? secondary->drain() : String("{\"rows\":[],\"dropped\":0}");
}
int startVibro(int level, int bpm) { BoardIO::Lock lock; return cues.startVibro(level, bpm); }
int freezeHold(int level) { BoardIO::Lock lock; return cues.freezePulses(level, 90); }  // Legacy RPC
int freezePulses(int level, int bpm) { BoardIO::Lock lock; return cues.freezePulses(level, bpm); }
int freezeAlarm() { BoardIO::Lock lock; return cues.freezeAlarm(); }
int startBuzzer(int hz, int bpm) { BoardIO::Lock lock; return cues.startBuzzer(hz, bpm); }
int stopOutputs(int mask) { BoardIO::Lock lock; return cues.stop(mask); }
int benchPulse(int channel) { BoardIO::Lock lock; return cues.benchPulse(channel); }
int setRate(int hz) {
  BoardIO::Lock lock;
  if (!Config::supportedRate(hz)) return 0;
  if (hz != sampleHz) {
    preferred.clear();
    alternate.clear();
    ++sequence;
    sampleHz = hz;
    nextReadUs = micros() + 1000000UL / sampleHz;
  }
  return 1;
}

#if UNFREEZE_DEBUG
// Monitor writes may wait for the Linux router. Keep them off the acquisition
// thread and only snapshot state under the bus mutex; no sensor reads here.
static struct k_thread diagnosticThread;
K_THREAD_STACK_DEFINE(diagnosticStack, Config::DiagnosticStackBytes);
static void printDiagnostics(void *, void *, void *) {
  for (;;) {
    k_msleep(Config::DiagnosticMs);
    uint32_t seq = 0, missed = 0;
    int address, rate;
    float accel[3] = {};
    bool fresh, online, vibro, buzzer;
    {
      BoardIO::Lock lock;
      address = primaryAddress;
      rate = sampleHz;
      online = primary && primary->online;
      fresh = online && primary->latest(seq, accel);
      if (primary) missed = primary->missed;
      vibro = cues.hasVibro;
      buzzer = cues.hasBuzzer;
    }
    char line[140];
    if (fresh) {
      snprintf(line, sizeof(line), "imu=0x%02X hz=%d seq=%lu a_mg=[%ld,%ld,%ld] missed=%lu vibro=%d buzzer=%d",
               (unsigned)address, rate, (unsigned long)seq, lroundf(accel[0]*1000), lroundf(accel[1]*1000),
               lroundf(accel[2]*1000), (unsigned long)missed, vibro, buzzer);
    } else {
      snprintf(line, sizeof(line), "imu=%s addr=0x%02X hz=%d missed=%lu vibro=%d buzzer=%d; check Qwiic/Wire1",
               online ? "waiting" : "missing", (unsigned)address, rate, (unsigned long)missed, vibro, buzzer);
    }
    DEBUG_PRINTLN(line);
  }
}
#endif

void setup() {
  k_mutex_init(&BoardIO::mutex);
  Modulino.begin(UNFREEZE_QWIIC);
  refreshModules();
  Bridge.begin(Config::RouterBaud);
  Monitor.begin(Config::MonitorBaud);
  // Register callbacks after hardware initialization. Never call Bridge inside a handler.
  bool registered = Bridge.provide_safe(Config::Rpc::Status, statusJson);
  registered &= Bridge.provide_safe(Config::Rpc::Samples, readPrimary);
  registered &= Bridge.provide_safe(Config::Rpc::Samples2, readSecondary);
  registered &= Bridge.provide_safe(Config::Rpc::Rate, setRate);
  registered &= Bridge.provide_safe(Config::Rpc::Vibro, startVibro);
  registered &= Bridge.provide_safe(Config::Rpc::FreezeHold, freezeHold);
  registered &= Bridge.provide_safe(Config::Rpc::FreezePulses, freezePulses);
  registered &= Bridge.provide_safe(Config::Rpc::FreezeAlarm, freezeAlarm);
  registered &= Bridge.provide_safe(Config::Rpc::Buzzer, startBuzzer);
  registered &= Bridge.provide_safe(Config::Rpc::Stop, stopOutputs);
  registered &= Bridge.provide_safe(Config::Rpc::Bench, benchPulse);
  Monitor.println(registered ? "Unfreeze MCU v1 ready" : "Unfreeze MCU RPC registration failed; restart App");
  Monitor.println(statusJson());
#if UNFREEZE_DEBUG
  k_thread_create(&diagnosticThread, diagnosticStack, K_THREAD_STACK_SIZEOF(diagnosticStack),
                  printDiagnostics, nullptr, nullptr, nullptr, 7, 0, K_NO_WAIT);
#endif
  BoardIO::Lock lock;
  nextReadUs = micros();
  nextProbeMs = millis() + Config::ProbeMs;
}

void loop() {
  BoardIO::Lock lock;
  const uint32_t now = millis();
  cues.tick(now);
  const uint32_t us = micros();
  if (BoardIO::due(us, nextReadUs)) {
    const uint32_t period = 1000000UL / sampleHz;
    const uint32_t skipped = (us - nextReadUs) / period;
    nextReadUs += (skipped + 1) * period;
    sequence += skipped + 1;
    preferred.readSlot(sequence, skipped);
    alternate.readSlot(sequence, skipped);
  }
  if (BoardIO::due(now, nextProbeMs)) {
    nextProbeMs = now + Config::ProbeMs;
    refreshModules();
  }
}
