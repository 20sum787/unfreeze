"""Optional board-local test input lets a paired phone stay in control during a bench test."""
import json
import logging
import threading
import time


def watch_bench(root, service, shutdown):
    source = root / "data/bench-request.json"
    pending = root / "data/bench-processing.json"
    start = time.time()
    while not shutdown.wait(0.15):
        try:
            source.replace(pending)
        except FileNotFoundError:
            continue
        try:
            request = json.loads(pending.read_text())
            now = time.time()
            if not start <= request["created"] <= now or now - request["created"] > 3:
                continue
            token = service.session_token()
            if not token:
                logging.info("Bench input ignored while idle")
            elif request["kind"] == "door":
                service.door({"bench": True}, "simulated", session_id=token)
            elif request["kind"] in ("prefreeze", "freeze"):
                service.motion(request["kind"], {"bench": True}, "simulated", session_id=token)
        except (ValueError, KeyError, TypeError, OSError) as error:
            logging.warning("Bench request rejected: %s", error)
        finally:
            pending.unlink(missing_ok=True)


def start_bench(root, service):
    shutdown = threading.Event()
    threading.Thread(target=watch_bench, args=(root, service, shutdown), daemon=True).start()
    return shutdown
