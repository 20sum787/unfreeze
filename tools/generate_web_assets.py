import base64
import hashlib
import io
import math
from pathlib import Path
from random import Random
import struct
import sys
import tarfile
import wave
import requests

root = Path(__file__).resolve().parents[1] / "board/unfreeze-uno-q/python/web"

def fetch_vendor():
    vendor = root / "vendor"
    vendor.mkdir(parents=True, exist_ok=True)
    dist = requests.get("https://registry.npmjs.org/socket.io-client/4.8.1", timeout=30).json()["dist"]
    package = requests.get(dist["tarball"], timeout=45).content
    assert "sha512-" + base64.b64encode(hashlib.sha512(package).digest()).decode() == dist["integrity"]
    with tarfile.open(fileobj=io.BytesIO(package)) as archive:
        for source, target in (
            ("package/dist/socket.io.min.js", "socket.io-4.8.1.min.js"),
            ("package/LICENSE", "socket.io.LICENSE.txt"),
        ):
            (vendor / target).write_bytes(archive.extractfile(source).read())


def generate_tracks():
    track_folder = root / "tracks"
    track_folder.mkdir(exist_ok=True)
    rate = 22050
    beats = 16
    profiles = (
        ("piano", 90, (261.63, 329.63, 392, 329.63), 7, 2.0, 0.03),
        ("marimba", 100, (392, 493.88, 587.33, 392), 12, 4.0, 0.02),
        ("woodblock", 85, (760, 630, 690, 630), 28, 1.58, 0.09),
        ("soft-drums", 90, (102, 148, 109, 148), 16, 2.41, 0.24),
        ("bass-pulse", 105, (130.81, 164.81, 146.83, 110), 11, 2.0, 0.05),
        ("hand-percussion", 110, (235, 310, 255, 294), 24, 1.72, 0.36),
    )
    for name, bpm, notes, decay, overtone, noise in profiles:
        rng = Random(name)
        seconds_per_beat = 60 / bpm
        samples = bytearray()
        for beat in range(beats):
            start = round(beat * seconds_per_beat * rate)
            length = round((beat + 1) * seconds_per_beat * rate) - start
            frequency = notes[beat % len(notes)]
            accent = 1.0 if beat % 4 == 0 else 0.82
            for tick in range(length):
                t = tick / rate
                phase = math.tau * frequency * t
                attack = min(1, t / 0.004)
                release = min(1, (length - tick - 1) / (rate * 0.035))
                body = math.exp(-t * decay) * (
                    math.sin(phase) + 0.27 * math.sin(overtone * phase)
                )
                transient = noise * rng.uniform(-1, 1) * math.exp(-t * 90)
                sample = round(16000 * accent * attack * release * (body + transient))
                samples.extend(struct.pack("<h", sample))
        with wave.open(str(track_folder / f"{name}.wav"), "wb") as wav:
            wav.setparams((1, 2, rate, 0, "NONE", ""))
            wav.writeframes(samples)


if __name__ == "__main__":
    if "--tracks-only" not in sys.argv[1:]:
        fetch_vendor()
    generate_tracks()
