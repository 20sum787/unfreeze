# Unfreeze on the UNO Q

The board runs a camera detector and a movement classifier on Linux. The MCU handles Qwiic sensors and actuator timing. A chest-mounted USB camera can trigger a doorway rhythm while the primary Movement module measures three-axis acceleration at the lower back. The Vibro module is worn on the thigh. A laptop browser or an Android phone can control a session over the phone hotspot.

Start with the [60-minute bench checklist](QUICKSTART_CHECKLIST.md), [pin-to-pin wiring and dependencies](HARDWARE.md), and [resource measurements](MEMORY_AUDIT.md).

## Installation and offline operation

From the repository root run `python tools/package_uno_app.py`. Import the full ZIP into App Lab. In SSH, change to the imported app directory and run `python3 tools/preflight.py --fix-paths` before selecting **Run**. App Lab compiles/uploads the MCU sketch and starts the Linux application. Keep internet available for the first platform, library and container downloads. After provisioning, verify operation with the hotspot still active and mobile data switched off.

Fifteen pinned wheels in `wheels/companion/` target Linux AArch64 and CPython 3.13. If the runtime has changed and pip reports incompatible wheels, check the Python version first. With internet access, a compatible alternative is to install from `python/requirements-common.txt` by setting `python/requirements.txt` to `-r requirements-common.txt` and restarting the app. This changes the dependency provisioning assumptions.

When the camera is unavailable, stop the full app and import the hardware-only ZIP. It omits the video Brick and keeps the movement classifier, companion and actuators. Both apps use port 7000. Run one at a time and read its own pairing file.

## Connect, observe and test

1. Power the UNO Q independently. Join it and the browser computer to the phone hotspot. Use the board’s assigned IP. Replace the example address below if DHCP changes it.
2. Open the board controller at `http://10.105.16.241:7000/#device`. An Android phone hosting the hotspot can connect directly. Pair with the six-digit code in the board app directory.
3. Keep the session idle to use **Test Buzzer** and **Test Vibro** with the current settings. Each manual test plays four beats. Select **Start session** to enable real event routing. A session expires after 15 minutes.
4. Open `/preview` for the read-only English camera and cue display. It polls every 400 ms while visible and shows the latest fresh freeze score and output acknowledgements. A second device can view this page while the first controls the session. The runner feed is available on port 4912 at `/embed` when the runner is running.
5. Use App Lab **Serial Monitor** for raw MCU readings, **Python** for services/model status and **App launch** for build or container failures. Open **Diagnostics** on the controller for labeled events and telemetry.

```sh
ssh arduino@10.105.16.241
cd ~/ArduinoApps/unfreeze-uno-q
sudo cat data/pairing-code.txt
curl -fsS http://127.0.0.1:7000/v1/health
curl -fsS http://127.0.0.1:7000/v1/build
```

For this implementation check `appBuild=freeze-pulse-alarm-v3`, `mcuCueRevision=3` and `mcuFreezeHoldMs=5000`. The build endpoint can respond before the MCU has reported its capabilities.

## From detections to physical output

| Observation | Decision | Output |
|---|---|---|
| Camera returns a door box | Confidence ≥0.50, center between 30% and 70% of image width, two consistent detections. Leaving the qualifying view for about 1.5 s rearms the gate. | One track for a new approach when the foreground client is ready. Board-only and phone-fallback routes use four-beat buzzer groups that can repeat while the door stays confirmed. |
| Movement returns freeze | During an active session, two consecutive eligible clean windows have winning label freeze and score ≥0.70. Haptics and live cueing must be enabled. | Five-second pulse train. Each pulse lasts up to 180 ms at the configured cadence and drive level. At 90 BPM, onsets are about 667 ms apart. The MCU clips any pulse that would cross the deadline. |
| Freeze evidence persists | At least five seconds since the first eligible positive reading. The latest reading qualifies and ≥75% of readings in the trailing five seconds qualify. A full second of low readings resets the episode. | One continuous five-second, 2,400 Hz buzzer alarm per episode. It takes priority over doorway audio. The module API controls pitch and duration; actual loudness must be measured. |

The alarm clock starts with the first qualifying score. The motor starts after confirmation. An example with clean 250 ms updates has first positive at 0.00 s, motor start at 0.25 s, earliest alarm at 5.00 s, end of the motor train at 5.25 s, and end of that alarm at 10.00 s. Stop can cancel both channels early. Motor-affected windows can extend an established episode. Only clean windows can start a new one. The preview reports MCU acceptance and client playback acknowledgements.

## Verify the models independently

Run these commands inside the installed app directory on AArch64 Linux. Stop the app first on a memory-constrained board to avoid loading an extra model alongside the live services.

```sh
python3 tools/check_motion.py tools/movement-freeze.json --expected-label freeze
python3 tools/check_motion.py tools/movement-normal.json --expected-label normal
python3 tools/check_camera.py
```

The included movement model is the float32 UNO Q CPU export for project 1170229, impulse 1, deployment 4. At 64 Hz it uses 128 samples per window, three acceleration axes in g and a 16-sample hop. The first fresh prediction needs roughly two seconds of continuous samples. Daphnet reference recordings trace to the lower back. Physical axis order and sign still require verification on the wearer. The shipped demonstration permits cues with `allowUnverifiedMountForDemo=true`; set it false to require a verified mount. The model has two labels, freeze and normal. The bench interface can separately inject a simulated prefreeze event.

| Fixed input | Expected replay |
|---|---|
| Freeze sample 3233555685, first 128 observations | freeze 0.973963, normal 0.026037 |
| Normal sample 3233556955, first 128 observations | freeze 0.000111, normal 0.999889 |
| 192 × 192 RGB frame from 88.25 s of the source clip | Camera project 1170197, v6, label door, box approximately (100, 43, 52, 105), score 0.908 |

Reference scores came from running the actual EIM in a Cortex-A53 emulator. In one historical check 26 of 29 source frames produced door boxes, including a clear-ahead scene. These frames share recorded material and cannot establish accuracy on a new site. The [SHA-256 manifest](models/checksums.json) identifies both binaries.

## Bench injection and diagnosis

For deliberate tests, enable `benchInjection` in `python/runtime.json`, restart, pair, and start a session. From the board app directory run `python3 tools/bench.py door`, `python3 tools/bench.py prefreeze` or `python3 tools/bench.py freeze`. Wait for each cue to finish. Events carry `origin=simulated`. Restore the default false setting after the test. A single injected freeze tests the motor path; the sustained alarm requires a sequence of qualifying scores.

| Symptom | First check |
|---|---|
| Connection refused | Test port 22, confirm the board IP, and query local port 7000 over SSH. If local health fails, inspect app/container status before changing hotspot settings. |
| Pair fails or controls stay disabled | Read the current code, verify the authenticated snapshot and hardware capability flags, and stop the active session before manual tests. |
| Blank camera feed or no boxes | Check `ls -l /dev/v4l/by-id/ /dev/video*`, power, competing camera apps, the model hash and fixed-frame replay. Use the hardware-only app for independent MCU bring-up. |
| Box but no cue | Check session state, centrality, consecutive observations, selected route and client audio readiness. Audition a track to unlock browser audio. |
| Raw IMU data but no vibration | Check sequence continuity, 64 Hz, mount gating, winner, threshold, two clean windows, haptics enabled and MCU acknowledgement. Test Vibro while idle. |
| Motor pulses, no alarm | Inspect fresh scores, the five-second ratio, `vibroWindow`, gaps, `motion.freeze_alarm` and the Buzzer acknowledgement. Time both physical outputs independently. |
| Settings revert or Stop reports FAULT | Compare settings revision and reload conflicting fields. Check which output failed to stop, restore that module and retry Stop. |

## Configuration and model replacement

- `sketch/config.h` owns module addresses, buffer sizes, pulse duration, alarm tone and MCU limits. `sketch/deployment_config.h` owns shared endpoints, baseline thresholds and Bridge timeout. Run `python3 tools/sync_config.py --write` after editing the shared header. Without the flag it checks for drift. The movement risk override lives in `python/motion.json`.
- For a replacement movement EIM, update its project identity, frequency, feature count, axes, units, hop and labels in `motion.json`. Begin in scores-only mode and supply at least one labeled replay window.
- For a replacement camera EIM, check the export identity, label, dimensions, resizing and coordinate conversion in `python/camera_adapter.py`. Update the fixed frame and `tools/check_camera.py` when the input shape changes. Check both path overrides in `app.yaml`; repeated imports may change the directory name.
- Update the SHA-256 manifest, give the EIM executable permissions on Linux, and run preflight plus both replay checks. Reimport the full package when models or dependencies change. The SSH updater only replaces Python and sketch files.
- For host regressions install `python -m pip install -r python/requirements-common.txt Pillow` and run `python -m unittest discover -s tests -v` from this directory. Include Node 22.12+ for the real browser-module transport tests.

## References

- [App launch and startup](https://docs.arduino.cc/software/app-lab/apps/run)
- [UNO Q user manual](https://docs.arduino.cc/tutorials/uno-q/user-manual/)
- [Hotspot configuration](https://docs.arduino.cc/software/app-lab/configure/network-configuration/)
- [Studio input window](https://studio.edgeimpulse.com/public/1170229/live/impulse/1/create-impulse)
- [Edge Impulse Linux SDK](https://docs.edgeimpulse.com/tools/libraries/sdks/inference/linux/python)
- [Custom classification example](https://github.com/edgeimpulse/linux-sdk-python/blob/master/examples/custom/classify.py)
- [Linux EIM protocol](https://docs.edgeimpulse.com/hardware/deployments/run-linux-eim)
- [App Lab deployment](https://docs.edgeimpulse.com/hardware/deployments/run-arduino-app-lab)
- [Camera Brick container configuration](https://github.com/arduino/app-bricks-py/blob/main/src/arduino/app_bricks/video_objectdetection/brick_compose.yaml)
- [Modulino library](https://github.com/arduino-libraries/Arduino_Modulino)
- [Bridge API](https://docs.arduino.cc/software/app-lab/bridge/bridge-api)
- [App format](https://github.com/arduino/arduino-app-cli/blob/main/docs/app-specification.md)
