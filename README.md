# Unfreeze

Unfreeze is a wearable prototype for exploring cues during freezing of gait. An Arduino UNO Q uses a USB camera to detect doorways and a Modulino Movement sensor to score walking motion. A phone or browser controls the session and displays the model outputs. Inference runs on the board, so the phone hotspot can carry the demo without internet after the board has been provisioned.

**For reviewers and presenters:** open the [code summary and presentation notes](docs/Unfreeze-Code-Summary.html) in a browser. Follow the [60-minute hardware checklist](board/unfreeze-uno-q/QUICKSTART_CHECKLIST.md) for a bench demonstration.

## Try it on a computer

From the repository root, run the following with Python 3.

```sh
python android/serve_web.py
```

Open [the local controller](http://127.0.0.1:8765/), select **Device → Connect demo board**, then **Start session**. Trigger a simulated doorway or motion event and inspect **Diagnostics**. Demo mode uses a simulated peer and the bundled audio tracks.

## Run on the wearable

1. Connect the Movement, Buzzer and Vibro modules over Qwiic. Connect a UVC camera through a powered USB data hub. Use the [wiring table and BOM](board/unfreeze-uno-q/HARDWARE.md).
2. Run `python tools/package_uno_app.py` from the repository root. Import `dist/Unfreeze-UNO-Q-AppLab.zip` in Arduino App Lab. For camera-free bring-up, import `dist/Unfreeze-UNO-Q-hardware-only.zip` instead. The packaging script checks the model hashes and executable permissions.
3. In SSH, change to the imported app directory (normally `~/ArduinoApps/unfreeze-uno-q`) and run `python3 tools/preflight.py --fix-paths`. Select **Run** in App Lab. Allow internet access for first-time platform, library and image downloads.
4. Join the UNO Q and the computer to the phone hotspot. Open `http://<board-ip>:7000/#device` on the computer, or open the Android app on the hotspot phone. Use the address assigned to the board. Read the current code in the app directory with `sudo cat data/pairing-code.txt`. Pair one controller and keep the session idle for **Test Buzzer** and **Test Vibro**.
5. Select **Start session** for live inference. An additional browser can open `http://<board-ip>:7000/preview` for read-only camera, motion-score and cue monitoring. Check `/v1/health` for service availability and `/v1/build` for the running application, MCU cue revision (3) and five-second haptic duration. An output acknowledgement confirms the command reached the firmware. Verify sound and vibration on the hardware.

For an update over SSH to an existing full installation, build the ZIP first, then run `./tools/Update-Unfreeze-Board.ps1 -BoardAddress <board-ip>` in PowerShell. The helper updates Python and sketch files and stops the running session. Use App Lab import for model or dependency changes. The [board manual](board/unfreeze-uno-q/README.md) covers model replacement, model replay and troubleshooting.

## Build the Android app

Use JDK 17, Android SDK Platform 35 and Build Tools 34.0.0. Open `android/` in Android Studio while keeping it inside this repository. From that directory run:

```powershell
.\gradlew.bat assembleDebug testDebugUnitTest
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

On Linux or macOS use `./gradlew`. The debug build supports HTTP on the local demo network and Android 8.0 or newer. Android packages the same web files the UNO Q serves. See the [client manual](android/README.md) for audio routing, settings and the socket protocol.

## How the code fits together

```text
USB camera → video detection runner → door label + bounding box ─┐
                                                                ├→ Linux session controller
Movement → UNO Q MCU → sampled acceleration → movement EIM ─────┘    ├→ Bridge → Buzzer / Vibro
                                                                    └→ LAN → web / Android audio
```

| Directory | Contents |
| --- | --- |
| [board/unfreeze-uno-q/sketch](board/unfreeze-uno-q/sketch/) | MCU entry points, hardware configuration, sampling, actuator timers and Bridge methods |
| [board/unfreeze-uno-q/python](board/unfreeze-uno-q/python/) | Sensor services, inference adapters, cue decisions, API and session state |
| [board/unfreeze-uno-q/python/web](board/unfreeze-uno-q/python/web/) | Shared controller, read-only camera preview, diagnostics and six rhythm tracks |
| [android](android/) | Kotlin client, WebView bridge, local network transport, audio playback and Gradle wrapper |
| [models](board/unfreeze-uno-q/models/) and [wheels](board/unfreeze-uno-q/wheels/) | Exported AArch64 EIMs, SHA-256 checksums and pinned offline board dependencies |
| [hardware](hardware/hack_test_seq/) and [tests/mcu-host](tests/mcu-host/) | Standalone wiring-test sketch and host-side MCU test doubles |
| [training](training/) | Camera dataset preparation and movement orientation experiments |
| [tools](tools/) | App Lab packaging, board updater and shared asset generator |
| [docs](docs/) | Project presentation, cueing research and IMU mounting study |

The camera pipeline verifies the v6 model and filters detections for a stable, central doorway before issuing an audio cue. The motion classifier consumes 128 three-axis accelerometer samples at 64 Hz and produces `freeze` and `normal` scores. The demo uses a 0.70 threshold and two qualifying windows to trigger five seconds of Vibro pulses at the selected drive and cadence. A sustained episode can trigger a separate five-second continuous 2,400 Hz buzzer alarm. Timing, short dips and sensor loss are covered in the [board manual](board/unfreeze-uno-q/README.md). The current demo permits an unverified mounting orientation. The prototype and its thresholds have not been clinically validated.

## Submission verification

The submission build linked for `arduino:zephyr:unoq` with 126,508 bytes of program storage and 57,868 bytes of global data. Both App Lab archives passed packaging checks. The Android debug APK built with all 18 shared web files verified byte-for-byte. All 27 Python tests, nine web unit tests, two Android unit tests and the C++ host checks passed. Physical deployment, mounting orientation and measured five-second actuator timing still require a bench run for this snapshot.

## Verify a checkout

Run from the repository root with Python 3.11+ and Node 22.12+.

```sh
python -m pip install -r board/unfreeze-uno-q/python/requirements-common.txt Pillow
python -m unittest discover -s board/unfreeze-uno-q/tests
npm --prefix android test
python tools/package_uno_app.py
```

To compile the MCU independently, run `arduino-cli compile --profile default sketch` from `board/unfreeze-uno-q/`. The [sketch profile](board/unfreeze-uno-q/sketch/sketch.yaml) pins the platform and libraries. See the [memory audit](board/unfreeze-uno-q/MEMORY_AUDIT.md) for estimates and measurement limits. For end-to-end validation on a board, use the fixed-input model replays and the actuator sequence in the [acceptance checklist](board/unfreeze-uno-q/QUICKSTART_CHECKLIST.md). See [third-party components](THIRD_PARTY.md) for software and model provenance.
