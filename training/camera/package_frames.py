from collections import Counter
import csv
import io
import json
from pathlib import Path
import zipfile

from PIL import Image, ImageDraw, ImageFont


WORK = Path(__file__).resolve().parent
OUTPUTS = WORK.parents[1] / "outputs"
OUTPUTS.mkdir(exist_ok=True)
SOURCE_ID = "ips_20261121_152942"
SITE_ID = "gallery_glass_door_01"


with (WORK / "selection.csv").open(encoding="utf-8", newline="") as file:
    selection = list(csv.DictReader(file))

assert len(selection) == len({row["seconds"] for row in selection})
selection.sort(key=lambda row: (row["usage"] != "training", float(row["seconds"])))
labels = []
manifest = []
items = []
for row in selection:
    timestamp_ms = round(float(row["seconds"]) * 1000)
    frame = WORK / "final_frames" / f"t{timestamp_ms:06d}.jpg"
    training = row["usage"] == "training"
    label = "clear_ahead" if training else ""
    basename = f"{label or row['usage']}.{SOURCE_ID}.{timestamp_ms:06d}.jpg"
    relative_path = f"training/{basename}" if training else f"review/{row['usage']}/{basename}"
    archive_path = f"edge_impulse/{relative_path}" if training else relative_path
    if training:
        labels.append({
            "path": relative_path,
            "name": basename,
            "category": "training",
            "label": {"type": "label", "label": label},
            "metadata": {"site_id": SITE_ID, "clip_id": SOURCE_ID,
                         "source_ms": str(timestamp_ms), "subtype": row["subtype"]},
        })
    manifest.append({"image_path": archive_path, "source_seconds": f"{timestamp_ms/1000:.3f}",
                     "usage": row["usage"], "suggested_label": label,
                     "site_id": SITE_ID, "clip_id": SOURCE_ID,
                     "subtype": row["subtype"], "note": row["note"]})
    with Image.open(frame) as image:
        assert image.format == "JPEG" and image.size == (960, 540)
        image.verify()
    items.append((row, frame, archive_path))

counts = Counter(row["usage"] for row in selection)
assert counts["training"] and counts["open_passage"]
archive = OUTPUTS / "door-side-pass-frames.zip"
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
    for row, frame, path in items:
        output.write(frame, path)
    output.writestr("edge_impulse/info.labels", json.dumps({"version": 1, "files": labels}, indent=2))
    manifest_out = io.StringIO(newline="")
    writer = csv.DictWriter(manifest_out, fieldnames=list(manifest[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(manifest)
    output.writestr("frame_manifest.csv", manifest_out.getvalue().encode("utf-8-sig"))
    output.writestr("README.txt", f"""Frames from a doorway pass
Source: IPS_2026-11-21.15.29.42.1650.mp4. Full 16:9 frames are 960 x 540. Requested source timestamps have approximately one frame of uncertainty.
edge_impulse/ contains {counts['training']} clear_ahead training negatives and info.labels. Upload this folder to Training in Studio. Combine with narrow_ahead data from other sites and use consistent resizing for a 160 x 160 model.
review/open_passage/ contains {counts['open_passage']} candidate passages. Verify direction, passability and clear width.
review/closed_or_ambiguous/ contains {counts['closed_or_ambiguous']} uncertain or closed doors. Review before labeling. Both review sets are excluded from info.labels.
frame_manifest.csv records source times and observations. Site {SITE_ID}, clip {SOURCE_ID}. Keep the entire clip in one split and evaluate generalization at another site. Similar adjacent frames and obvious visual interference were screened out.

""".encode("utf-8-sig"))

columns = 5
width, height = 240, 159
rows = (len(items) + columns - 1) // columns
sheet = Image.new("RGB", (columns * width, rows * height), "#11171e")
draw = ImageDraw.Draw(sheet)
font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 15)
for index, (row, frame, path) in enumerate(items):
    x = index % columns * width
    y = index // columns * height
    with Image.open(frame) as image:
        image.thumbnail((width - 8, 132))
        sheet.paste(image, (x + (width - image.width) // 2, y + 2))
    category = {"training": "TRAIN NEG", "open_passage": "CHECK WIDTH",
                "closed_or_ambiguous": "CHECK DOOR"}[row["usage"]]
    color = "#a4e5ca" if row["usage"] == "training" else "#ffcf8d"
    caption = f"{index+1:02d}  {float(row['seconds']):6.2f}s  {category}"
    draw.text((x + 7, y + 137), caption, font=font, fill=color)
preview = OUTPUTS / "door-side-pass-preview.jpg"
sheet.save(preview, quality=91)

with zipfile.ZipFile(archive) as output:
    assert output.testzip() is None
    packed_labels = json.loads(output.read("edge_impulse/info.labels"))["files"]
    assert all(f"edge_impulse/{record['path']}" in output.namelist() for record in packed_labels)
    assert len(output.namelist()) == len(items) + 3
print(f"Selected {len(items)} frames: {dict(counts)}. Archive {archive.stat().st_size:,} bytes.")
