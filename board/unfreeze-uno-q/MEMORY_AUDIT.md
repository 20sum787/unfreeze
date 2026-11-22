# UNO Q memory and timing audit

The submission targets one 2 GB UNO Q. The 2 GB belongs to Linux. The MCU linker reports the regions exposed to the sketch by the Zephyr board profile.

| Resource | Evidence | Interpretation |
|---|---|---|
| MCU firmware, pulse-alarm build | 126,508 / 786,432 bytes of program storage; 57,868 / 262,144 bytes of global data; 204,276 bytes remaining | Cross-compiled and linked with the pinned UNO Q profile. Earlier audits measured 123,384 / 56,680 bytes and the continuous-hold build measured 123,800 / 56,868. Remaining space also serves the runtime heap and stacks. |
| MCU inference arena | 0 bytes for both EIMs | Both model processes run on Linux. |
| IMU rings | 2 × 32 rows × 32 bytes = 2,048 bytes; previous object measurement 1,096 bytes per MovementStream | Included in static data. Each ring spans half a second at 64 Hz. |
| RPC and diagnostics | 224-byte formatting buffer, 4,096-byte diagnostic stack and previously measured 256-byte thread object | Two rows per reply. A returned String still owns memory. Monitor output takes a snapshot before releasing the bus lock. |
| Historical single-function stack estimates | Status 320 B, diagnostics 248 B, drain 144 B, acquisition 56 B, loop 32 B | Compiler frame estimates exclude call chains, interrupts and runtime high-water marks. RouterBridge adds a worker stack; the movement driver allocates at initialization. |
| Camera EIM | File 21,477,040 B; shared input 147,456 B; emulator peak RSS 77,400 KiB | 192 × 192 packed RGB values at four bytes each. Excludes camera capture, Python and encoding. |
| Movement EIM | File 13,767,888 B; shared input capacity 1,536 B; emulator peak RSS 54,860 KiB | 128 × 3 float32 values. Live requests use JSON. One inference worker and one pending window bound the backlog. |

## Measurement method

Both exported EIMs ran under Cortex-A53 QEMU with ten inferences per packaged input. Initial RSS was 13,232 KiB for the camera and 13,068 KiB for movement. Summed process high-water marks were about 129.2 MiB; shared pages may be double-counted. The largest identified static symbol in each ELF was a 10 MiB rapidjson_buffer. A complete tensor-arena allocation could not be read from a single symbol. Binary size, interpreter buffers, shared input and RSS measure different resources.

## Timing and on-board checks

At 64 Hz a sample slot lasts 15,625 microseconds. Missed deadlines advance the sequence counter. The LSM6DSOX driver configures a 104 Hz internal ODR and the sketch reads the latest data at 64 Hz. Linux fills the first window after 128 samples and schedules another after 16. Gaps and session changes invalidate old work. The MCU schedules cue pulses independently. I²C and Bridge still have peripheral and transport latency.

Measure idle, dual-model operation and repeated session starts on the board using `free -m`, `docker stats --no-stream` and `ps -eo pid,rss,comm --sort=-rss`. Record available RAM, drops, missed slots, windowAgeMs and behavior after disconnect/reconnect. For measured MCU high-water marks, use a Zephyr build with stack instrumentation and the thread analyzer.

If Linux memory pressure rises, stop competing applications, disable extra video previews and isolate the motion path with the hardware-only app. Run fixed model replays separately. On the MCU, compiling with UNFREEZE_DEBUG=0 removes periodic raw diagnostics and its thread stack. Changing camera preprocessing or model shape requires new reference inputs and timing measurements.

## References

- [UNO Q architecture](https://docs.arduino.cc/hardware/uno-q/)
- [Zephyr thread analyzer](https://docs.zephyrproject.org/latest/services/debugging/thread-analyzer.html)
