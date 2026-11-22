# 60-minute hardware acceptance checklist

Prepare the full and hardware-only App Lab ZIPs, board login, charged hotspot phone, external power, and an App Lab computer. First-time downloads and network isolation can extend the schedule. Record each observed result.

| Minutes | Action | Acceptance check |
|---|---|---|
| 00–05 | Power off. Connect one Movement, Vibro and Buzzer to Qwiic. Verify keyed connectors, ground, 3.3 V, SDA and SCL. Connect the hub upstream to UNO Q, camera downstream and supply to PD IN. | No 5 V on Qwiic. Two Movements must have distinct addresses. Use the [pin table](HARDWARE.md). |
| 05–10 | Power on. Join the board and computer to the phone hotspot, select network mode in App Lab and SSH to the board. | Record the board address from hostname -I and the camera device from ls -l /dev/v4l/by-id/ /dev/video*. |
| 10–18 | Import the full ZIP. Run check A below in the imported directory. Select Run. Keep internet available during first startup. | Preflight verifies both model hashes and application paths. App launch shows sketch compilation/upload and container start. If the video service blocks startup, use hardware-only. |
| 18–26 | Open Serial Monitor and gently rotate the primary Movement module. | Look for MCU ready, sequence, address, a_mg and missed roughly every two seconds. At rest the combined acceleration should be close to 1,000 mg. |
| 26–34 | Stop the app if necessary to reduce peak RAM. Execute check B, then Run again. | The two fixed windows classify as freeze and normal. The camera frame produces a door box. Skip camera replay for the hardware-only package. |
| 34–43 | Run check C. Open the controller on port 7000. Pair, enable Diagnostics and test each actuator while idle. Then start a session. | Observe HTTP health, authenticated state, raw samples, and motion-model scores after the first two-second window. |
| 43–52 | Open /preview. Approach a frontal door, then pass one sideways. Audition the phone track and try board-only audio. On the bench, time an actual freeze pulse train and sustained alarm separately. | Record boxes, event, audible playback and motor response. A manual four-beat test verifies the actuator path. Sustained alarm acceptance requires sustained qualifying model evidence. |
| 52–60 | Stop the session. Keep Wi-Fi active, disable mobile data and restart the provisioned app. Collect check D. If startup on power-up is required, enable Run at startup and test a reboot. | Record model outputs, sound, reconnection, resource use and any outstanding hardware checks. |

### A. Verify import paths in board SSH

```sh
ls -dt ~/ArduinoApps/unfreeze-uno-q*
cd ~/ArduinoApps/unfreeze-uno-q
python3 tools/preflight.py --fix-paths
```

Use the actual imported directory for duplicate imports or hardware-only. Preflight checks wheels, EIMs, configuration and permissions. If needed, run chmod +x models/*.eim and repeat.

### B. Replay fixed inputs

```sh
python3 tools/check_motion.py tools/movement-freeze.json --expected-label freeze
python3 tools/check_motion.py tools/movement-normal.json --expected-label normal
python3 tools/check_camera.py
```

Reference freeze scores are about 0.974 and 0.000111. The camera reference box is approximately x=100, y=43, width=52, height=105.

### C. Identify services and pairing code

```sh
curl -fsS http://127.0.0.1:7000/v1/health
curl -fsS http://127.0.0.1:7000/v1/build
sudo cat data/pairing-code.txt
```

### D. Record resources

```sh
free -m
docker stats --no-stream
ps -eo pid,rss,comm --sort=-rss | head -15
```

Use sudo for Docker if required. Compare dropped/missed samples, model age and RSS with and without video. See the [memory audit](MEMORY_AUDIT.md).

### Fast fault isolation

| Symptom | Check first | Next action |
|---|---|---|
| Board or page unavailable | Test SSH port 22, then run the local health check on the board. | Check hotspot isolation/IP for a network issue; inspect App launch/Python for a local service failure. |
| Dependency failure | Identify Zephyr core, Python wheel or Docker image in App launch. | Enable internet for first setup. Check Python ABI. Use hardware-only if the camera image cannot start. |
| MCU ready but IMU silent | Try one Movement and watch the next Serial Monitor line. | Power down, check cable/Wire1 and address 0x6A or 0x6B. Add actuators individually. |
| No camera boxes | Verify preflight, device enumeration and fixed-frame replay. | Stop other camera apps; check lens orientation, lighting, camera paths and data hub. |
| Scores but no output | Check ACTIVE, enabled haptics, live versus simulated origin, stable detections and MCU acknowledgement. | Test while idle, verify cue revision 3, and compare fresh scores against both gates. |
