import json
import queue
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from board import Hardware
from door import DoorGate
from motion import MotionWindows, RiskGate, SustainedFreeze
from movement_service import MovementService


def contract():
    return dict(enabled=True, modelFile="models/test.eim", sampleRateHz=64, windowSamples=4,
                hopSamples=2, axes=[{"source":"az_g","scale":9.80665},{"source":"gx_dps","scale":-1}],
                riskLabels={"FOG":"freeze"}, normalLabels=["walking"], mount="bench",
                minimumScore=.75, confirmWindows=2, clearWindows=2, enableLiveCues=True, mountVerified=True)


def row(i):
    return [i, round(i*1000/64), 0, 0, 1, 10, 0, 0]


class Policies(unittest.TestCase):
    def test_live_sampling_alarms_during_freeze_hold_and_never_retriggers_motor(self):
        cfg = dict(contract(), windowSamples=128, hopSamples=16, riskMinimumScore=.70)
        board = Hardware(Mock(return_value=5000))
        client = Mock()
        client.session_token.return_value = "demo"
        service = MovementService(board, client, ROOT)
        service.cfg, service.gate, service.windows = cfg, RiskGate(cfg), MotionWindows(cfg)
        service.engine = Mock()
        clock = [0.]
        onset, alarms = [], []
        def freeze(*args, **kwargs):
            onset.append(clock[0])
            self.assertTrue(board.freeze_pulses(40, 90))
        client.motion.side_effect = freeze
        client.freeze_alarm.side_effect = lambda *a, **k: alarms.append(clock[0])
        def classify(features):
            p = .4 if 4 <= clock[0] < 4.5 else .85
            return {"FOG":p, "walking":1-p}
        service.engine.classify.side_effect = classify
        pending = service.pending
        def next_window(timeout):
            while pending.empty() and clock[0] < 9:
                clock[0] += 1/64
                service._sample(row(round(clock[0]*64)), "demo", clock[0])
            if pending.empty():
                service.stop.set()
                raise queue.Empty()
            return pending.get_nowait()
        with patch("movement_service.time.monotonic", side_effect=lambda:clock[0]), patch.object(
                pending, "get", side_effect=lambda *a, **k: next_window(k["timeout"])
                if "timeout" in k else queue.Queue.get(pending, False)):
            service._infer()
        self.assertEqual(onset, [2.25])
        self.assertEqual(alarms, [7.0])  # five seconds after first positive, next fresh window

    def test_sustained_freeze_with_dips_recovery_and_new_episode(self):
        gate = SustainedFreeze(contract())
        def feed(i, p):
            return gate.update({"FOG":p, "walking":1-p}, i/4, "session")
        hits = [i for i in range(32) if feed(i, .4 if i in (4, 5, 12, 20) else .8)]
        self.assertEqual(hits, [21])
        for i in range(32, 38):
            self.assertFalse(feed(i, .1))
        self.assertEqual([i for i in range(38, 61) if feed(i, .85)], [58])

    def test_missing_or_motor_only_evidence_cannot_start_an_alarm(self):
        cfg = dict(contract(), windowSamples=128)
        scores = {"FOG":.85, "walking":.15}
        for context, resume in [("A", 7.9), ("B", 7.9), ("A", 12.)]:
            gate = SustainedFreeze(cfg)
            self.assertFalse(gate.update(scores, 0., "A"))
            self.assertFalse(gate.update(scores, .25, "A"))
            for i in range(32):
                self.assertFalse(gate.update(scores, resume+i/4, context, allow_start=False))
        gate = SustainedFreeze(cfg)
        for i in range(48):
            p = .8 if i % 2 else .3
            self.assertFalse(gate.update({"FOG":p, "walking":1-p}, i/4, "A"))

    def test_bridge_freeze_hold_sets_mask_only_on_duration_ack(self):
        for ack in (0, True, 5000):
            hw = Hardware(lambda name, level, bpm: ack if (name, level, bpm) == ("uf_freeze_pulses", 40, 90) else 0)
            with patch("board.time.monotonic", return_value=10):
                self.assertEqual(hw.freeze_pulses(40, 90), ack == 5000)
                self.assertEqual(hw.vibro_until, 15.5 if ack == 5000 else 0)

    def test_deployed_model_and_provisional_mapping(self):
        cfg = json.loads((ROOT / "python/motion.json").read_text())
        win = MotionWindows(cfg)
        self.assertFalse(cfg["mountVerified"])
        self.assertTrue(win.cues_enabled)
        self.assertFalse(MotionWindows(dict(cfg, allowUnverifiedMountForDemo=False)).cues_enabled)
        self.assertFalse(MotionWindows(dict(cfg, enableLiveCues=False)).cues_enabled)
        params = dict(model_type="classification", axis_count=3, frequency=64,
                      input_features_count=384, labels=["freeze", "normal"])
        win.verify_model(params, cfg["project"])
        with self.assertRaises(ValueError):
            win.verify_model(params, dict(cfg["project"], deploy_version=3))

    def test_deployed_freeze_threshold_and_rearm(self):
        cfg = json.loads((ROOT / "python/motion.json").read_text())
        gate = RiskGate(cfg)
        def classify(p):
            return gate.classify({"freeze": p, "normal": 1 - p})
        self.assertEqual([classify(p) for p in [.69, .69, .70, .70, .90]],
                         [None, None, None, "freeze", None])
        self.assertEqual([classify(p) for p in [.29, .29, .90, .90]], [None] * 4)
        self.assertEqual([classify(p) for p in [.25, .25, .90, .90]],
                         [None, None, None, "freeze"])

    def test_training_order_units_and_no_window_across_loss(self):
        window = MotionWindows(contract())
        actual = [window.add(row(i)) for i in [1,2,4,5,6,7,8,9]]
        self.assertEqual([v for v in actual if v], [[9.80665, -10]*4]*2)
        self.assertIsNone(actual[4])

    def test_eim_metadata_must_match(self):
        win = MotionWindows(contract())
        meta = dict(model_type="classification", axis_count=2, input_features_count=8,
                    frequency=64, labels=["FOG","walking"])
        win.verify_model(meta)
        for k, v in [("frequency",50),("labels",["door"]),("input_features_count",16)]:
            with self.assertRaises(ValueError):
                win.verify_model(dict(meta, **{k:v}))

    def test_fresh_risk_then_normal_required_to_rearm(self):
        gate = RiskGate(contract())
        risk, normal = {"FOG":.85,"walking":.15}, {"FOG":.1,"walking":.9}
        self.assertEqual([gate.classify(x) for x in [risk,risk,risk,normal,normal,risk,risk]],
                         [None,"freeze",None,None,None,None,"freeze"])

    def test_door_dedup_and_reentry(self):
        now = [1.0]
        cfg = json.loads((ROOT/"python/runtime.json").read_text())["door"]
        gate = DoorGate(cfg, lambda: now[0])
        front = dict(label="door",confidence=.81,bbox=[51,0,88,150],inputSize=[192,192])
        side = dict(front, bbox=[0,0,25,120])
        self.assertFalse(gate.update(side))
        self.assertFalse(gate.update(front))
        self.assertTrue(gate.update(front))
        self.assertFalse(gate.update(front))
        gate.clear()
        now[0] += 2
        self.assertFalse(gate.update(front))
        self.assertTrue(gate.update(front))

    def test_bridge_protocol_and_ack(self):
        def rpc(name,*args,timeout=None):
            self.assertGreater(timeout,0)
            return {"uf_samples":json.dumps({"rows":[row(4)],"dropped":0}),
                    "uf_status":'{"version":1}',"uf_buzzer":0,"uf_stop":1}[name]
        hw = Hardware(rpc)
        self.assertEqual(hw.samples(),([row(4)],0))
        self.assertFalse(hw.buzzer(440,90))
        self.assertTrue(hw.stop_vibro())

    def test_end_to_end_sampling_to_risk_is_once(self):
        # Simulated MCU clock advances at the requested rate. No patient data.
        class Board:
            vibro_until = 0
            start = time.monotonic()
            cursor = 0
            def stamp(self):
                return round((time.monotonic()-self.start)*1000)
            def status(self):
                return dict(hz=64,imu=True,buzzer=True,vibro=True,mcuMs=self.stamp(),missed=0)
            def samples(self):
                end = min(int(self.stamp()*64/1000), self.cursor+2)
                rows = [row(i) for i in range(self.cursor+1,end+1)]
                self.cursor=end
                return rows,0
        class Engine:
            def __init__(self,file):
                self.info = {"model_parameters":dict(model_type="classification",frequency=64,
                               axis_count=2,input_features_count=8,labels=["FOG","walking"])}
            def classify(self, features):
                assert features == [9.80665,-10]*4
                return {"FOG":.90,"walking":.1}
            def close(self):
                pass
        service = Mock()
        service.session_token.return_value = "session-1"
        done = threading.Event()
        service.motion.side_effect = lambda *a,**k: done.set()
        with tempfile.TemporaryDirectory() as directory, patch("movement_service.Eim", Engine):
            root = Path(directory)
            (root/"python").mkdir()
            (root/"python/motion.json").write_text(json.dumps(contract()))
            controller = MovementService(Board(), service, root)
            controller.start()
            try:
                self.assertTrue(done.wait(3))
                time.sleep(.2)
            finally:
                controller.close()
            self.assertEqual(service.motion.call_count, 1)
            self.assertEqual(service.motion.call_args.kwargs["session_id"],"session-1")


class DoorBuzzerTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeat_four_beats_only_on_confirmed_door(self):
        from cue_session import CueSession
        from unittest.mock import AsyncMock
        gate = DoorGate(dict(centerFraction=[.3,.7], confirmFrames=2,
                             maxFrameGapSeconds=3, clearSeconds=1.5))
        front = dict(label="door", confidence=.9, bbox=[51,0,88,150], inputSize=[192,192])
        files = Mock(settings={"settingsRevision": 1, "audio": {"mode": "board_only"},
                               "buzzer": {"toneHz": 800, "cadenceBpm": 120}})
        files.credentials = {"deviceId": "test"}
        hardware = Mock()
        hardware.buzzer.return_value = hardware.stop_buzzer.return_value = True
        session = CueSession(hardware, files, AsyncMock())
        session.buzzer_supported = True
        await session.start()
        with patch("cue_session.time") as session_time:
            clock = session_time.monotonic
            for instant in [1, 1.1, 1.5, 2.8, 3.2, 3.3, 5.3]:
                clock.return_value = instant
                await session.tick()
                if gate.update(front):
                    await session.door(front, "live")
                elif gate.stable:
                    await session.repeat_door_buzzer()
            self.assertEqual(hardware.buzzer.call_count, 3)
            gate.clear()
            self.assertFalse(gate.stable)
            clock.return_value = 10
            await session.tick()
            self.assertEqual(hardware.buzzer.call_count, 3)
            await session.stop()
            await session.repeat_door_buzzer()
            self.assertEqual(hardware.buzzer.call_count, 3)


if __name__ == "__main__":
    unittest.main()
