# Unfreeze companion

Unfreeze is a foreground controller for the UNO Q wearable. Android and desktop/mobile browsers ship the same five pages, shared state machine, settings editor, diagnostics and six offline rhythm tracks. A demo board runs entirely inside either client. Live vision and motion inference run on the wearable.

The shared UI source is [the board web directory](../board/unfreeze-uno-q/python/web/). All `web/` paths below refer to that directory.

## Run

**Web.** Run `python serve_web.py` in this directory and open [the local companion](http://127.0.0.1:8765/). Choose **Device → Connect demo board → Start session → Approach doorway**. Try **Simulate motion risk**, then open Diagnostics and expand an event. A local browser can play the selected 16-beat track. Demo Buzzer and Vibro output appears on screen. The server serves only the `web/` directory and binds to loopback. For hosting elsewhere, copy the contents of `web/` unchanged to a static HTTP(S) server. Use an HTTP(S) origin so JavaScript modules and audio can load.

**Android.** The Device page defaults to `10.105.16.241:7000` on the phone hotspot. A previously saved address can be edited here. Build and install the debug APK on Android 8 or later with a current Android System WebView, or open the project containing `settings.gradle.kts` in Android Studio. The default debug build permits HTTP on a private demo LAN. A release build uses the platform's HTTPS policy. The APK bundles all five pages, the Socket.IO library and the audio tracks. Open Device and choose the demo or pairing flow.

**Build on Windows.** Use JDK 17, Android SDK Platform 35 and Build Tools 34.0.0. Set `ANDROID_HOME` to the SDK or use Android Studio's SDK location. The checked-in Gradle wrapper pins version 8.9 and verifies its distribution hash.

```powershell
.\gradlew.bat assembleDebug testDebugUnitTest
adb devices -l
adb -s <phone-serial> install -r app/build/outputs/apk/debug/app-debug.apk
```

## Connect the wearable

1. Turn on the phone's Wi-Fi hotspot and use Arduino App Lab's network settings to connect the UNO Q to it. For the browser companion, connect the computer to the same hotspot, then open the companion on that computer. For the Android companion, open the app on the phone that is hosting the hotspot.
2. Find the UNO Q's assigned Wi-Fi IP in App Lab and enter it with the App's published port, typically `7000`. The address shown in the form is an example. **Test connection** checks `/v1/health` and its API version before pairing. Pair with the code from the board. An authenticated Socket.IO snapshot enables controls. The visible status distinguishes HTTP reachability from a working event connection.
3. On the web, serve the companion from the board's origin when possible. For a separate origin, allow that exact origin on both the board's REST and Socket.IO endpoints, including CORS preflight for `Authorization`, `Content-Type`, POST and PUT. An HTTPS page needs an HTTPS-compatible board endpoint and browser LAN permission where applicable. If the computer cannot reach the board address at all, check the hotspot's client isolation or try a shared private router. Native Android uses its own network client.
4. Start a session. Keep the companion visible and the selected track audible. Sound controls local track/volume and the board's route, Buzzer pitch and cadence. Vibration edits supported drive levels and pulse cadence. Draft preview is available while idle. The board owns session expiry and Buzzer fallback. A client that loses the transport silences its audio, labels the gap and waits for a new snapshot. Offline Stop reports the board state as unconfirmed.
5. Use Diagnostics to inspect event IDs, source, origin, raw telemetry, cue reasons and sequence gaps. The 100-entry timeline and raw JSON are bounded. Simulated/replayed risk is labelled by origin. A real model's status and output come only from board messages. The phone and browser can each control the wearable. The board contract assigns one authenticated controller at a time.

## Rhythm tracks and demo settings

- Tracks are Piano and Soft Drums (90 BPM), Marimba (100 BPM), Woodblock (85 BPM), Bass Pulse (105 BPM) and Hand Percussion (110 BPM). Each has 16 clearly marked beats and lasts 8.7–11.3 seconds. Both clients can audition the complete track offline. A live cue still stops when the board cancels it or the client disconnects.
- The Sound and Vibration pages each have **Load demo defaults**. Buzzer starts from **90 BPM and 1,000 Hz**. Vibro starts from **90 BPM and 40% drive**. The app respects the board's advertised range and selects the nearest supported drive level, with ties going to the lower level. The button updates the draft. **Apply settings** sends it to the board. The preset keeps the chosen audio route and the vibration enable switch. The simulated board starts with these values. A real board supplies its own saved settings on connect.
- Studies adjust cues relative to the person's own walking cadence. One auditory study used 10% above the preferred cadence during walking. The DeFOG protocol started 10% below preferred cadence when testing gait re-initiation. The prototype uses 90 BPM as an adjustable starting point. Buzzer pitch and Vibro drive are device settings to check on the bench. Clinical benefit from this thigh-worn setup remains unverified. [Arias and Cudeiro](https://doi.org/10.1371/journal.pone.0009675) · [DeFOG study protocol](https://lirias.kuleuven.be/bitstream/123456789/684359/2/Zoetewei_2021-DeFOG%20protocol.pdf) · [Responsive lower-leg cueing feasibility study](https://doi.org/10.1186/s12938-023-01167-y)

## Source map

| Location | Responsibility |
| --- | --- |
| `web/index.html`, `style.css`, `ui.js` | Shared accessible pages, responsive layout, settings drafts, navigation and local preferences. |
| `web/controller.js` | Device connection, session snapshots, stale connection suppression, settings conflicts and bounded diagnostics. |
| `web/cues.js` | Session-scoped offer/play/cancel, deduplication, expiry and confirmation. |
| `web/platform.js` | Browser Fetch/Socket.IO/Web Audio and Android bridge adapter. Browser pairing lasts for the tab session. |
| `web/demo.js` | In-process v1 fixture, simulated board cues and fallback timing. |
| `app/src/main/java/org/medmech/unfreeze/` | Android asset-only WebView, origin-restricted native messaging, scoped LAN client, Keystore-backed credential and Media3 playback. |
| `tests/`, `integration/`, `app/src/test/` | Shared behavior, browser end-to-end and native HTTP adapter regressions. |

## v1 wire decisions for the board team

The runbooks specified the route names. These concrete inner field names let both clients decode the same payload. Confirm them against the actual firmware. All JSON examples also have executable equivalents in the demo peer.

- `GET /v1/health` returns `{"ok":true,"apiVersion":1}`. `POST /v1/pair` accepts `{"code":"…"}` and returns `deviceId` and `token`. Protected REST uses a Bearer credential. Socket.IO 4 connects at the standard path. `client.hello` sends token, device ID and API version. Return `status.snapshot` after authentication.
- `GET /v1/capabilities` exposes `firmwareVersion`, `audioModes`, support flags, `buzzerLimits.{toneHz,cadenceBpm}` and `hapticsLimits.{cadenceBpm,levelsPercent}`. Ranges are two-element inclusive arrays, levels are a list of valid numbers.
- `GET /v1/settings` returns `settingsRevision`, `audio.mode`, `buzzer.{toneHz,cadenceBpm}`, `haptics.{enabled,levelPercent,cadenceBpm}`. PUT sends `baseRevision` and settings. On conflict the draft retains edited fields while untouched fields adopt the new board values. The user reviews and applies again.
- `GET /v1/state` and `status.snapshot` share `bootId`, `deviceId`, `sessionId`, `sessionState`, `sessionExpiresInMs`, `settingsRevision`, `faultCode`, `visionStatus`, `motionStatus`, `doorAudio` and `hapticsOutput`. Start takes an empty object. Stop sends the intended session ID. Preview sends `requestId`, `cadenceBpm`, `levelPercent`. Stop vibration uses `/v1/haptics/stop`.
- Offer carries `sessionId`, `cueId` and `ttlMs`. Ready, Play, Started, Failed and Cancel carry the same IDs. The client acknowledges Started only after Media3's playback transition or Web Audio rendering-clock progress. Playback is foreground and finite. The board applies the offer/start timeouts and fallback. Diagnostic output state `applied` records board acceptance. Physical cue timing requires instrumentation.
- Add a new capability with a default for prior firmware, extend the fixture and tests, then add it to the shared UI. Breaking wire changes require a new API version. Add a WAV to the shared tracks directory and one entry to the shared track catalog. Both clients discover the addition from those files.

## Tests and debugging

```powershell
npm test
npm ci
npm run test:browser
.\gradlew.bat testDebugUnitTest assembleDebug
```

The dependency-free unit suite uses Node 22+ with glob support. Browser integration uses a separately installed Google Chrome, a temporary profile, two ephemeral loopback servers, and a silent audio-rendering sink. It exercises real HTTP/Socket.IO with a simulated peer, both display widths, revision handling, replay prevention and the foreground audio handshake. Runtime web assets require no npm install. For an Android transport issue run `adb logcat` filtered to the app process and check the UI timeline. Do not include pairing codes or bearer credentials in shared logs. The original PCM tracks are bundled under `web/tracks/`. Socket.IO 4.8.1 and its license are under `web/vendor/`.

**Physical acceptance still required.** Pair with a real board, approach a held-out door, confirm audible music, force a disconnect, and confirm the board's fallback Buzzer. Preview and stop the actual Vibro, reconnect, then ensure an earlier cue does not replay. Check latency and physical output separately from fixture results.
