# UNO Q hardware, wiring and deployment

## Parts and power

| Quantity | Part | Role |
|---|---|---|
| 1 | Arduino UNO Q, 2 GB, provisioned Debian image | The STM32U585 runs the Zephyr sketch. The QRB2210 runs Linux, Python and the two AArch64 EIMs. Have the board login available. |
| 1 | Modulino Movement | Attach firmly to the lower back. The current model consumes the primary unit's three acceleration axes. |
| 1 each | Modulino Vibro and Modulino Buzzer | Thigh haptics and local audible cues. Bare motors and two-pin buzzers require different electronics. |
| 3 | Four-wire JST-SH 1.0 mm Qwiic cables | Daisy-chain UNO Q, Movement, Vibro and Buzzer. The order of modules on the bus can vary. |
| Optional | Second Movement and one extra cable | Use a distinct address for a comparison unit. |
| 1 each | UVC camera, USB data cable, externally powered USB-C data hub and supply | Chest camera uses a downstream data port. Provide 5 V / 3 A capability for the board and allow for hub and camera consumption. |
| 1 each | App Lab computer and hotspot phone | Both computer and board join the phone's hotspot. First-time provisioning needs internet. |

## Pin-to-pin wiring

Disconnect power before cabling. The pin numbers refer to the keyed QWIIC1 connector. Verify connector orientation and printed signals.

| UNO Q connector | Signal | Usual cable color | On each module |
|---|---|---|---|
| QWIIC1 pin 1 | GND | Black | GND |
| QWIIC1 pin 2 | 3.3 V out | Red | 3V3 |
| QWIIC1 pin 3 | PD13, I²C4 SDA, Wire1 | Blue | SDA |
| QWIIC1 pin 4 | PD12, I²C4 SCL, Wire1 | Yellow | SCL |
| USB-C | USB host data and board power | Hub upstream cable | Camera on downstream data, external power to PD IN |
| Wi-Fi | Linux network interface | Wireless | Board and laptop join the hotspot; use the board's leased IPv4 address |

The Qwiic bus is 3.3 V. D20/D21 belong to a different bus. RouterBridge and Monitor use the internal connection. D0/D1, external serial wiring, SPI chip selects and MCU PWM pins are unnecessary for this setup. The actuator modules time their own individual pulses.

| Device | Seven-bit address | Identification |
|---|---|---|
| Movement | 0x6A or 0x6B | For two sensors, change one unit using its documented address strap. Devices at the same address cannot be distinguished by scanning. |
| Buzzer | 0x1E | The library's shifted match-table value is 0x3C. |
| Vibro | 0x38 | The library's shifted match-table value is 0x70. |

At startup the sketch prefers 0x6B when both IMUs are present. With one unit it selects the available address. Once assigned, the primary identity survives temporary loss so that the classifier cannot silently switch body sites. Check decimal `imuAddr` 106 or 107 and move only the intended primary. Recheck after repositioning or a reboot.

## Build and bring-up

In App Lab network mode select the board, import the full ZIP, run preflight in the imported directory and select **Run**. **App launch** covers builds and containers, **Serial Monitor** covers MCU diagnostics, and **Python** shows camera and companion state. Check `http://<board-ip>:7000/v1/health` and `/preview`. For isolated sensor tests, stop the full app before running hardware-only.

| Environment | Procedure | Coverage |
|---|---|---|
| Arduino IDE 2 | Install Arduino Zephyr Boards 1.1.0, Arduino_Modulino 0.10.0, Arduino_RouterBridge 0.4.4 and dependencies from the sketch profile. Open sketch/sketch.ino, choose Arduino UNO Q, then Verify. To upload only the MCU, stop the app and connect over USB. | MCU compile/upload. App Lab starts the Linux services. |
| Arduino CLI | From this directory run the commands below. The profile pins FQBN arduino:zephyr:unoq and dependency versions. | Cross-compile without a board. |
| VS Code / PlatformIO workspace | Use the same Arduino CLI commands from the integrated terminal or a task. The verified target uses the UNO Q Zephyr core. A classic AVR UNO target is incompatible. | Reuses the verified board profile. |

```sh
arduino-cli core update-index
arduino-cli compile --profile default sketch
```

If the Zephyr platform is missing, add `https://downloads.arduino.cc/packages/package_zephyr_index.json` to Additional Boards Manager URLs or pass it via `--additional-urls` on the CLI. Arduino.h, Wire.h and zephyr/kernel.h come from the board core. Modulino, LSM6DSOX, RouterBridge, RPClite and MsgPack come from the profile. Other Modulino dependencies in the library manifest do not imply additional installed peripherals. The Linux EIM binaries contain their inference runtimes. The video Brick and Python wheel bundle supply the remaining board services.

## References

- [UNO Q power](https://docs.arduino.cc/tutorials/uno-q/power-specification/)
- [UVC camera wiring](https://docs.arduino.cc/tutorials/usb-camera/user-manual/)
- [Modulino Movement and address strap](https://docs.arduino.cc/tutorials/modulino-movement/how-movement/)
- [UNO Q pinout](https://docs.arduino.cc/resources/pinouts/ABX00162-full-pinout.pdf)
- [Qwiic colors](https://support.arduino.cc/hc/en-us/articles/27742264847260-About-Qwiic)
- [Serial and Serial1](https://support.arduino.cc/hc/en-us/articles/27251870677916-Migrating-to-Zephyr-core-0-55-0-on-UNO-Q)
- [Modulino actuator API](https://github.com/arduino-libraries/Arduino_Modulino/blob/0.10.0/src/Modulino.h)
- [Address utility](https://github.com/arduino-libraries/Arduino_Modulino/blob/0.10.0/examples/Utilities/AddressChanger/AddressChanger.ino)
- [App import](https://docs.arduino.cc/software/app-lab/apps/manage-apps)
- [App launch](https://docs.arduino.cc/software/app-lab/apps/run/)
- [App Lab deployment](https://docs.edgeimpulse.com/hardware/deployments/run-arduino-app-lab)
- [UNO Q manual](https://docs.arduino.cc/tutorials/uno-q/user-manual/)
- [CLI sketch profiles](https://docs.arduino.cc/arduino-cli/sketch-project-file/)
- [PlatformIO board index](https://docs.platformio.org/en/latest/boards/index.html)
- [Modulino 0.10.0](https://github.com/arduino-libraries/Arduino_Modulino/tree/0.10.0)
- [RouterBridge 0.4.4](https://github.com/arduino-libraries/Arduino_RouterBridge/tree/0.4.4)
- [Linux EIM protocol](https://docs.edgeimpulse.com/hardware/deployments/run-linux-eim)
