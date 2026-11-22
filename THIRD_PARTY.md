# Components and attribution

| Component | Use and source |
| --- | --- |
| Camera model | Edge Impulse project 1170197, deployment v6. The AArch64 EIM and its digest are in [models](board/unfreeze-uno-q/models/). [Studio project](https://studio.edgeimpulse.com/studio/1170197) |
| Movement model | Edge Impulse project 1170229, impulse 1, deployment v4. The [board manual](board/unfreeze-uno-q/README.md) identifies both replay samples and their units. [Studio project](https://studio.edgeimpulse.com/studio/1170229) |
| Arduino platform and modules | The [sketch profile](board/unfreeze-uno-q/sketch/sketch.yaml) pins the UNO Q core, Modulino and Bridge libraries. [Arduino Modulino](https://github.com/arduino-libraries/Arduino_Modulino) |
| Socket.IO browser client | Version 4.8.1 is bundled with its [MIT license](board/unfreeze-uno-q/python/web/vendor/socket.io.LICENSE.txt). |
| Python wheels | The board bundle retains the original wheels, package metadata and upstream license files. See [companion wheels](board/unfreeze-uno-q/wheels/companion/) and the [requirements](board/unfreeze-uno-q/python/requirements-common.txt). |
| Android build and runtime | The repository includes the Gradle wrapper. AndroidX, Kotlin, OkHttp, Media3 and Socket.IO dependencies are declared in the [app build file](android/app/build.gradle.kts). [Gradle license](https://github.com/gradle/gradle/blob/v8.9.0/LICENSE) |

The [audio generator](tools/generate_web_assets.py) synthesizes the six bundled rhythm tracks. Clinical and engineering references are cited in the [cueing report](docs/unfreeze-cueing-report.html). Rights to third-party software, exported models and underlying datasets remain subject to their respective terms.
