"""Consume one Edge Impulse runner. The Arduino Brick owns the physical camera."""

import base64
import io
import inspect
import json
import math
import threading
import time
from deployment_defaults import CAMERA_HOST, CAMERA_PORT, DOOR_CONFIDENCE

PROJECT_ID = 1170197
DEPLOY_VERSION = 6
INPUT_SIZE = (192, 192)
LABEL = "door"
CONFIDENCE = DOOR_CONFIDENCE
MODEL_VERSION = "Unfreeze-Camera v6"
RUNNER_WS = f"ws://{CAMERA_HOST}:{CAMERA_PORT}"


def check_model(hello):
    project = hello.get("project", {})
    model = hello.get("modelParameters", {})
    observed = (project.get("id"), project.get("deploy_version"), model.get("model_type"),
                model.get("image_input_width"), model.get("image_input_height"),
                model.get("image_channel_count"), model.get("image_resize_mode"), model.get("labels"))
    expected = (PROJECT_ID, DEPLOY_VERSION, "object_detection", *INPUT_SIZE, 3, "fit-longest", [LABEL])
    if observed != expected:
        raise ValueError(f"Unexpected model {observed!r}; check app.yaml and the installed .eim")


def preview_size(data_url):
    """Read JPEG dimensions without decompressing pixels. Pillow is bundled with App Bricks."""
    from PIL import Image

    prefix = "data:image/jpeg;base64,"
    if not isinstance(data_url, str) or not data_url.startswith(prefix):
        raise ValueError("Runner sent a preview in an unexpected format")
    # libvips/Sharp places the JPEG SOF near the beginning. Try the complete JPEG
    # only if unusually large metadata prevents Pillow from opening the header.
    start = len(prefix)
    try:
        with Image.open(io.BytesIO(base64.b64decode(data_url[start:start + 8192]))) as image:
            return image.size
    except OSError:
        with Image.open(io.BytesIO(base64.b64decode(data_url[start:]))) as image:
            return image.size


def strongest_door(boxes, preview):
    """Undo the runner's preview projection, including the v6 fit-longest letterbox."""
    src_width, src_height = preview
    dst_width, dst_height = INPUT_SIZE
    scale = min(dst_width / src_width, dst_height / src_height)
    pad_x = (dst_width - src_width * scale) / 2
    pad_y = (dst_height - src_height * scale) / 2
    best = None
    for box in boxes:
        if not isinstance(box, dict) or box.get("label") != LABEL:
            continue
        fields = [box.get(key) for key in ("x", "y", "width", "height", "value")]
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in fields):
            continue
        x, y, width, height, confidence = fields
        if width <= 0 or height <= 0 or not CONFIDENCE <= confidence <= 1:
            continue
        x1 = round(max(0, min(src_width, x)) * scale + pad_x)
        y1 = round(max(0, min(src_height, y)) * scale + pad_y)
        x2 = round(max(0, min(src_width, x + width)) * scale + pad_x)
        y2 = round(max(0, min(src_height, y + height)) * scale + pad_y)
        if x2 <= x1 or y2 <= y1:
            continue
        if best is None or confidence > best["confidence"]:
            best = {"label": LABEL, "confidence": confidence, "bbox": [x1, y1, x2 - x1, y2 - y1],
                    "inputSize": list(INPUT_SIZE), "modelVersion": MODEL_VERSION}
    return best


class CameraObserver:
    """Read-only observer of the runner's classification stream; reconnects after runner restarts."""

    def __init__(self, detector, on_door, on_clear, on_status):
        self.detector = detector
        self.on_door = on_door
        self.on_clear = on_clear
        self.on_status = on_status
        self.last_status = None
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, name="unfreeze-camera", daemon=True)

    def status(self, message):
        if self.last_status != message:
            self.last_status = message
            print(f"[camera] {message}", flush=True)
            if self.on_status:
                self.on_status(message)

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=2)

    def _run(self):
        from websockets.sync.client import connect

        # Older Brick images have no configurable sync-client frame queue.
        queue_limit = {"max_queue": 1} if "max_queue" in inspect.signature(connect).parameters else {}
        while not self.stopped.is_set():
            try:
                with connect(RUNNER_WS, open_timeout=2, close_timeout=1, max_size=8 * 1024 * 1024,
                             **queue_limit) as socket:
                    self._read(socket)
            except Exception as error:
                if not self.stopped.is_set():
                    self.status(f"Runner unavailable: {error}")
                    if self.on_clear:
                        self.on_clear()
                    self.stopped.wait(2)

    def _read(self, socket):
        hello = json.loads(socket.recv(timeout=5))
        check_model(hello)
        socket.send(json.dumps({"type": "toggle-camera-preview", "enabled": True}))
        self.status(f"{MODEL_VERSION} verified; waiting for frames")
        preview = None
        last_classification = last_preview = time.monotonic()
        stale = False
        while not self.stopped.is_set():
            try:
                message = json.loads(socket.recv(timeout=1))
            except TimeoutError:
                message = {}
            now = time.monotonic()
            if message.get("type") == "camera-preview":
                preview = preview_size(message.get("image"))
                last_preview = now
            elif message.get("type") == "classification" and preview and now - last_preview < 5:
                last_classification = now
                stale = False
                self.status(f"{MODEL_VERSION} live; preview {preview[0]}x{preview[1]}")
                best = strongest_door(message.get("result", {}).get("bounding_boxes") or [], preview)
                if best:
                    self.on_door(best)
                elif self.on_clear:
                    self.on_clear()
            if not stale and now - min(last_classification, last_preview) >= 5:
                stale = True
                self.status("Waiting for fresh camera frames and inference; check camera and :4912/embed")
                if self.on_clear:
                    self.on_clear()


def attach_camera(on_door, *, on_status=None, on_clear=None):
    """Call once before App.run(). Callbacks run on an observer thread; keep them short."""
    from arduino.app_bricks.video_objectdetection import VideoObjectDetection

    detector = VideoObjectDetection(confidence=CONFIDENCE, debounce_sec=0.0)
    observer = CameraObserver(detector, on_door, on_clear, on_status)
    observer.thread.start()
    return observer
