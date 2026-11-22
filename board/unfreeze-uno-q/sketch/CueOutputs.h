#pragma once

#include "BoardIO.h"

// The module firmware limits every individual pulse; loop() schedules future beats.
class CueOutputs {
public:
  bool hasVibro = false, hasBuzzer = false;

  void refresh() {
    const bool vib = BoardIO::present(Config::Vibro);
    const bool buzz = BoardIO::present(Config::Buzzer);
    if (!vib) haptic = {};
    if (!buzz) audio = {};
    if (vib && !hasVibro) { vibro.begin(); vibro.off(); }
    if (buzz && !hasBuzzer) { buzzer.begin(); buzzer.noTone(); }
    hasVibro = vib;
    hasBuzzer = buzz;
  }

  int startVibro(int level, int bpm) {
    if (level < Config::DriveMin || level > Config::DriveMax || level % Config::DriveStep || !hasVibro ||
        !BoardIO::present(Config::Vibro)) return 0;
    return start(haptic, level, bpm, true);
  }

  int startBuzzer(int hz, int bpm) {
    if (hz < Config::ToneMin || hz > Config::ToneMax || !hasBuzzer ||
        !BoardIO::present(Config::Buzzer)) return 0;
    return start(audio, hz, bpm, false);
  }

  int freezePulses(int level, int bpm) {
    if (level < Config::DriveMin || level > Config::DriveMax || level % Config::DriveStep ||
        bpm < Config::BpmMin || bpm > Config::BpmMax ||
        !hasVibro || !BoardIO::present(Config::Vibro)) return 0;
    const uint32_t now = millis();
    haptic = {};
    haptic.active = true;
    haptic.setting = level;
    haptic.interval = (60000UL + bpm / 2) / bpm;
    haptic.next = now;
    haptic.finish = now + Config::FreezeHoldMs;
    haptic.remaining = (Config::FreezeHoldMs + haptic.interval - 1) / haptic.interval;
    tickTrain(haptic, now, true);
    return Config::FreezeHoldMs;
  }

  int freezeAlarm() {
    if (!hasBuzzer || !BoardIO::present(Config::Buzzer)) return 0;
    audio = {};
    audio.active = true;
    audio.finish = millis() + Config::FreezeAlarmMs;
    buzzer.tone(Config::FreezeAlarmHz, Config::FreezeAlarmMs);
    return Config::FreezeAlarmMs;
  }

  // Local bring-up only. Explicitly requested single pulses from hack_test_seq.ino.
  // Both channels must be idle; the normal stop mask can cancel a test pulse.
  int benchPulse(int channel) {
    if (haptic.active || audio.active) return 0;
    if (channel == 1 && hasVibro && BoardIO::present(Config::Vibro)) {
      vibro.on(Config::BenchPulseMs, false, Config::BenchDrive);
      haptic.active = true;
      haptic.remaining = 0;
      haptic.finish = millis() + Config::BenchPulseMs;
      return 1;
    }
    if (channel == 2 && hasBuzzer && BoardIO::present(Config::Buzzer)) {
      buzzer.tone(Config::BenchHz, Config::BenchPulseMs);
      audio.active = true;
      audio.remaining = 0;
      audio.finish = millis() + Config::BenchPulseMs;
      return 1;
    }
    return 0;
  }

  int stop(int mask) {
    if (mask < 1 || mask > 3) return 0;
    bool ok = true;
    if (mask & 1) {
      if (hasVibro && BoardIO::present(Config::Vibro)) vibro.off();
      else if (haptic.active) ok = false;
      haptic = {};
    }
    if (mask & 2) {
      if (hasBuzzer && BoardIO::present(Config::Buzzer)) buzzer.noTone();
      else if (audio.active) ok = false;
      audio = {};
    }
    return ok ? 1 : 0;
  }

  bool vibroActive() const { return haptic.active; }
  bool buzzerActive() const { return audio.active; }

  void tick(uint32_t now) {
    tickTrain(haptic, now, true);
    tickTrain(audio, now, false);
  }

private:
  struct Train {
    bool active = false;
    int setting = 0;
    uint32_t interval = 0, next = 0, finish = 0;
    uint8_t remaining = 0;
  };
  Train haptic, audio;
  ModulinoVibro vibro{Config::Vibro};
  ModulinoBuzzer buzzer{Config::Buzzer};

  void tickTrain(Train &t, uint32_t now, bool isVibro) {
    if (!t.active) return;
    if (BoardIO::due(now, t.finish)) { t.active = false; return; }
    while (t.remaining && BoardIO::due(now, t.next)) {
      const uint32_t lateness = now - t.next;
      --t.remaining;
      t.next += t.interval;
      if (lateness > Config::LateBeatMs) continue;
      if (isVibro) {
        const uint32_t left = t.finish - now;
        vibro.on(left < Config::VibroPulseMs ? left : Config::VibroPulseMs, false, t.setting);
      }
      else buzzer.tone(t.setting, Config::BuzzerPulseMs);
    }
  }

  int start(Train &t, int setting, int bpm, bool isVibro) {
    if (bpm < Config::BpmMin || bpm > Config::BpmMax || t.active) return 0;
    const uint32_t now = millis();
    t = {};
    t.active = true;
    t.setting = setting;
    t.interval = (60000UL + bpm / 2) / bpm;
    t.next = now;
    t.finish = now + (Config::BeatCount - 1) * t.interval + (isVibro ? Config::VibroPulseMs : Config::BuzzerPulseMs) + Config::LateBeatMs;
    t.remaining = Config::BeatCount;
    tickTrain(t, now, isVibro);
    return 1;
  }
};
