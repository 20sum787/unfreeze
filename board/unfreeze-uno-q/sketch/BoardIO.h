#pragma once

#include <Arduino_Modulino.h>
#include <zephyr/kernel.h>
#include "config.h"

namespace BoardIO {

// Keep the bus and the sample/cue state serialized even on RouterBridge versions
// whose generic dispatcher can service a registered callback on a worker thread.
extern struct k_mutex mutex;
class Lock {
public:
  Lock() { k_mutex_lock(&mutex, K_FOREVER); }
  ~Lock() { k_mutex_unlock(&mutex); }
  Lock(const Lock &) = delete;
  Lock &operator=(const Lock &) = delete;
};

inline bool present(uint8_t address) {
  UNFREEZE_QWIIC.beginTransmission(address);
  return UNFREEZE_QWIIC.endTransmission() == 0;
}

inline bool due(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}
}
