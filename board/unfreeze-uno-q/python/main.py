"""Arduino App Lab entry point; camera, IMU and LAN share only the session API."""
import json
import logging
from pathlib import Path
import time

from board import Hardware
from bench import start_bench
from companion import Companion
from door import DoorGate
from movement_service import MovementService

ROOT = Path(__file__).resolve().parent.parent


def main():
    from arduino.app_utils import App, Bridge

    logging.basicConfig(level=logging.INFO)
    config = json.loads((ROOT / "python/runtime.json").read_text(encoding="utf8"))
    board = Hardware(Bridge.call)
    service = Companion(board, ROOT / "data", bench_enabled=config["benchInjection"])
    service.start()
    bench = start_bench(ROOT, service) if config["benchInjection"] else None
    movement = MovementService(board, service, ROOT)
    camera = None
    gate = DoorGate(config["door"])
    current_session = None
    last_raw = 0

    def on_door(box):
        nonlocal current_session, last_raw
        now = time.monotonic()
        token = service.session_token()
        if token != current_session:
            current_session = token
            gate.reset()
        data = {**box, "bboxPx": box["bbox"]}
        if now - last_raw >= 0.5:
            service.telemetry("camera", data)
            last_raw = now
        if token:
            if gate.update(box):
                service.door(data, session_id=token)
            elif gate.stable:
                service.continue_door_buzzer(token, now)

    try:
        movement.start()
        if config["cameraEnabled"]:
            try:
                from camera_adapter import attach_camera
                camera = attach_camera(on_door, on_clear=gate.clear,
                                       on_status=lambda message: service.status(vision=message))
            except Exception as error:
                logging.exception("Camera setup failed; MCU and companion are still running")
                service.status(vision=f"camera setup failed · {error}")
        else:
            service.status(vision="disabled · hardware-only mode")
        App.run()
    finally:
        if bench:
            bench.set()
        if camera:
            camera.close()
        movement.close()
        service.close()


if __name__ == "__main__":
    main()
