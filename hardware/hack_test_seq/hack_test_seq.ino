// This is a hardware test script for all of our chosen sensors for this Hackathon

// NOTES
// accelerometer readings are in gs - 1g is 9.8, and the typical range is -2g to +2g

#include <Arduino.h>
#include <Wire.h>
#include <Modulino.h>

// --- Tunable hardware & fixed test settings ---
#define WIRE_BUS              Wire1
const uint8_t  IMU_ADDR     = 0x6B; // Confirmed physical IMU address
const uint16_t SAMPLE_HZ    = 64;
const uint16_t PRINT_MS     = 250;
const uint16_t START_DELAY  = 1500; // Wait after boot before fixed sequence (ms)
const uint16_t STEP_GAP_MS  = 600;  // Pause between test steps (ms)

const uint16_t BPM          = 90;     // Runbook bench cadence
const uint8_t  BEATS        = 4;      // Runbook bench beats[cite: 1]
const uint16_t BUZZ_HZ      = 440;   // Runbook bench tone[cite: 1]
const uint16_t BUZZ_MS      = 1000;    // Runbook bench buzzer pulse[cite: 1]
const uint16_t VIBRO_MS     = 1000;    // Runbook bench vibro pulse[cite: 1]
const uint8_t  VIBRO_PWR    = 40;
// ----------------------------------------------

ModulinoMovement movement;
ModulinoVibro vibro;
ModulinoBuzzer buzzer;

const uint32_t SAMPLE_US = 1000000UL / SAMPLE_HZ;
const uint32_t BEAT_MS   = (60000UL + (BPM / 2)) / BPM;

bool okMov = false, okVib = false, okBuz = false;
uint32_t lastSampleUs = 0;
uint32_t lastPrintMs = 0;

void stopAll() {
  buzzer.noTone(); // Stop any active buzzer tone
  vibro.off();     // Stop any active vibration
}

void runFixedTestSequence() {
  Serial.println("Seq 1/3: Buzzer pulse");
  buzzer.tone(BUZZ_HZ, BUZZ_MS); // Play single buzzer pulse
  delay(BUZZ_MS + STEP_GAP_MS);
  buzzer.noTone();

  Serial.println("Seq 2/3: Vibro pulse");
  vibro.on(VIBRO_MS, false, VIBRO_PWR); // Non-blocking vibro pulse with drive level
  delay(VIBRO_MS + STEP_GAP_MS);
  vibro.off();

  Serial.println("Seq 3/3: 4-beat train");
  uint32_t nextBeatMs = millis();
  for (uint8_t i = 0; i < BEATS; i++) {
    while ((int32_t)(millis() - nextBeatMs) < 0) {
      delay(5);
    }
    buzzer.tone(BUZZ_HZ, BUZZ_MS);
    vibro.on(VIBRO_MS, false, VIBRO_PWR);
    nextBeatMs += BEAT_MS;
  }
  delay(VIBRO_MS + STEP_GAP_MS);
  stopAll();
  Serial.println("Fixed test sequence complete");
}

void setup() {
  Serial.begin(115200);
  delay(START_DELAY);

  WIRE_BUS.begin();
  Modulino.begin(WIRE_BUS); // Initialize Modulino bus on Wire1[cite: 1]

  okMov = movement.begin();
  okVib = vibro.begin();
  okBuz = buzzer.begin();

  Serial.print("Init (IMU 0x");
  Serial.print(IMU_ADDR, HEX);
  Serial.print("): mov=");
  Serial.print(okMov);
  Serial.print(" vib=");
  Serial.print(okVib);
  Serial.print(" buz=");
  Serial.println(okBuz);

  runFixedTestSequence();

  lastSampleUs = micros();
  lastPrintMs = millis();
}

void loop() {
  uint32_t nowUs = micros();
  if ((uint32_t)(nowUs - lastSampleUs) >= SAMPLE_US) {
    lastSampleUs += SAMPLE_US;
    if (okMov) {
      movement.update(); // Refresh IMU sensor readings
      uint32_t nowMs = millis();
      if ((uint32_t)(nowMs - lastPrintMs) >= PRINT_MS) {
        lastPrintMs = nowMs;
        Serial.print("g=");
        Serial.print(movement.getX(), 2); Serial.print(",");
        Serial.print(movement.getY(), 2); Serial.print(",");
        Serial.print(movement.getZ(), 2);
        Serial.print(" dps=");
        Serial.print(movement.getRoll(), 1); Serial.print(",");
        Serial.print(movement.getPitch(), 1); Serial.print(",");
        Serial.println(movement.getYaw(), 1); // Accel in g, gyro in deg/s[cite: 1]
      }
    }
  }
}