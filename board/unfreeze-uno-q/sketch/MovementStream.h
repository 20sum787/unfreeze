#pragma once

#include "BoardIO.h"
#include <math.h>
#include <string.h>

// A slot's sequence advances even when the scheduler skips it or the read fails.
// Both sensors share the slot number; timestamps describe their own read times.
class MovementStream {
public:
  explicit MovementStream(uint8_t address) : sensor(address), address_(address) {}

  void refresh() {
    const bool connected = BoardIO::present(address_);
    if (!connected) {
      if (online) clear();
      online = false;
    } else if (!online) {
      online = sensor.begin();
    }
  }

  void clear() { head = count = 0; hasLatest = false; }

  void readSlot(uint32_t seq, uint32_t skipped) {
    if (!online) return;
    missed += skipped;
    if (!sensor.available() || !sensor.update()) { ++missed; return; }
    Row r = {seq, millis(), {sensor.getX(), sensor.getY(), sensor.getZ(),
                            sensor.getRoll(), sensor.getPitch(), sensor.getYaw()}};
    for (int i = 0; i < 6; ++i) {
      // Reject out-of-range bus values before converting to fixed-point decimals.
      if (!isfinite(r.axes[i]) || fabsf(r.axes[i]) > (i < 3 ? 16.1f : 2100.f)) {
        ++missed;
        return;
      }
    }
    if (count == Capacity) {
      head = (head + 1) % Capacity;
      --count;
      ++dropped;
    }
    rows[(head + count) % Capacity] = r;
    ++count;
    ++samples;
    hasLatest = true;
  }

  String drain() {
    // The caller holds the bus/state mutex. Stage into one shared fixed buffer;
    // the single owning String is required by the RouterBridge return type.
    static char data[Config::RpcTextBytes];
    constexpr char prefix[] = "{\"rows\":[";
    memcpy(data, prefix, sizeof(prefix));
    size_t used = sizeof(prefix) - 1;
    const uint8_t n = count < Config::RowsPerRpc ? count : Config::RowsPerRpc;
    for (uint8_t i = 0; i < n; ++i) {
      const Row &r = rows[(head + i) % Capacity];
      const int written = snprintf(data + used, sizeof(data) - used,
          "%s[%lu,%lu,%lde-4,%lde-4,%lde-4,%lde-2,%lde-2,%lde-2]",
          i ? "," : "", (unsigned long)r.seq, (unsigned long)r.ms,
          lroundf(r.axes[0]*10000), lroundf(r.axes[1]*10000), lroundf(r.axes[2]*10000),
          lroundf(r.axes[3]*100), lroundf(r.axes[4]*100), lroundf(r.axes[5]*100));
      if (written < 0 || (size_t)written >= sizeof(data) - used) return String();
      used += written;
    }
    const int tail = snprintf(data + used, sizeof(data) - used, "],\"dropped\":%lu}", (unsigned long)dropped);
    if (tail < 0 || (size_t)tail >= sizeof(data) - used) return String();
    String result(data);
    if (result.length() == used + (size_t)tail) {
      head = (head + n) % Capacity;
      count -= n;
    }
    return result;
  }

  // Diagnostic tap never consumes the FIFO, even after the client drained it.
  bool latest(uint32_t &seq, float (&accel)[3]) const {
    if (!online || !hasLatest) return false;
    const Row &r = rows[(head + count + Capacity - 1) % Capacity];
    seq = r.seq;
    for (int i = 0; i < 3; ++i) accel[i] = r.axes[i];
    return true;
  }

  bool online = false;
  uint32_t samples = 0;
  uint32_t missed = 0;

private:
  struct Row { uint32_t seq, ms; float axes[6]; };
  static constexpr uint8_t Capacity = Config::FifoRows;
  ModulinoMovement sensor;
  const uint8_t address_;
  Row rows[Capacity]{};
  uint32_t dropped = 0;
  uint8_t head = 0, count = 0;
  bool hasLatest = false;
};
