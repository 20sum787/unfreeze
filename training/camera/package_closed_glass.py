from collections import Counter
import csv
from hashlib import sha256
import io
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
from PIL import Image, ImageDraw, ImageFont


work = Path(__file__).resolve().parent
outputs = work.parents[1] / 'outputs'
outputs.mkdir(exist_ok=True)
clip = 'vid_20261121_180441'
site = 'gallery_glass_door_01'
candidate_views = {
    'across_room': [1, 6, 9, 12, 18, 21, 25, 28, 76, 80, 84, 87, 91, 95, 100, 104, 114, 135, 175, 177],
    'oblique_or_edge': [30, 33, 36, 39, 42, 45, 48, 61, 64, 67, 107, 110, 112, 139, 142, 145, 148,
                        163, 166, 171, 173],
    'near_glass': [50, 52, 55, 58, 69, 72, 74, 151, 154, 157, 159, 161],
}
candidates = sorted((index, view) for view, indices in candidate_views.items() for index in indices)
assert len(candidates) == len(set(index for index, _ in candidates))
entries = []
records = []
frames = []
thumbnail_history = []
hashes = set()
rejections = Counter()


def distance(left, right):
    return min(float(np.mean(np.abs(left[1:-1, 1:-1] - right[y:y + 42, x:x + 22])))
               for y in range(3) for x in range(3))


for index, view in candidates:
    source_file = work / 'third_4fps' / f'{index:04d}.jpg'
    data = source_file.read_bytes()
    with Image.open(io.BytesIO(data)) as photo:
        assert photo.format == 'JPEG' and photo.size == (540, 960) and not photo.getexif()
        photo.load()
        pixels = np.asarray(photo)
        neutral_gray = ((pixels >= 126) & (pixels <= 130)).all(axis=2)
        luminance = np.asarray(photo.convert('L').resize((24, 44), Image.Resampling.BOX), dtype=np.float32)
        digest = sha256(photo.tobytes()).digest()
    if np.count_nonzero(neutral_gray.mean(axis=1) > 0.75) >= 4 or luminance.std() < 13:
        rejections['decoder_artifact'] += 1
        continue
    if digest in hashes or any(distance(luminance, previous) < (5.7 if abs(index - prior_index) <= 8 else 4.2)
                               for prior_index, previous in thumbnail_history):
        rejections['near_duplicate'] += 1
        continue
    hashes.add(digest)
    thumbnail_history.append((index, luminance))
    source_ms = index * 250
    basename = f'{clip}.{source_ms:06d}.jpg'
    name = f'training/{basename}'
    metadata = {'site_id': site, 'clip_id': clip, 'source_ms': str(source_ms),
                'scene_type': 'closed_glass_door', 'view': view, 'label_basis': 'closed_glass_no_passable_opening'}
    entries.append({'path': name, 'name': basename, 'category': 'training', 'label': {'type': 'unlabeled'},
                    'metadata': metadata, 'boundingBoxes': []})
    records.append({'file': name, 'source_seconds': f'{source_ms/1000:.2f}', 'bounding_box_count': 0, **metadata})
    frames.append((index, data))

archive = outputs / 'door-video-180441-closed-glass.zip'
upload_folder = 'edge_impulse_train'
with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as package:
    for entry, (_, data) in zip(entries, frames, strict=True):
        package.writestr(f'{upload_folder}/{entry["path"]}', data)
    package.writestr(f'{upload_folder}/info.labels', json.dumps({'version': 1, 'files': entries}, indent=2))
    manifest = io.StringIO(newline='')
    writer = csv.DictWriter(manifest, fieldnames=list(records[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(records)
    package.writestr('frame_manifest.csv', manifest.getvalue().encode('utf-8-sig'))
    package.writestr('README.txt', f'''Closed glass door: YOLO-Pro negative examples
Source: VID20261121180441.mp4, about 44.5 seconds at 4 Hz. Retained {len(frames)} out of 178 candidate frames. Full portrait JPEGs are 540 x 960; source location metadata is removed. frame_manifest.csv records time and viewpoint.
For a passable-opening target, the observed door stayed closed. Openings visible beyond the glass cannot be entered from the camera position. These reviewed negatives have explicit empty boundingBoxes arrays. Keep this recording in one split. The gallery shares site_id gallery_glass_door_01 with the earlier clip but has a different clip_id.
Confirm the project's target definition before appending the negatives. Upload edge_impulse_train as Training in Studio, inspect imported labels and then retrain.
https://docs.edgeimpulse.com/tools/specifications/data-annotation/ei-labels
'''.encode('utf-8-sig'))

with ZipFile(archive) as package:
    assert package.testzip() is None
    packed = json.loads(package.read(f'{upload_folder}/info.labels'))
    assert packed == {'version': 1, 'files': entries}
    jpg_paths = {name for name in package.namelist() if name.endswith('.jpg')}
    assert jpg_paths == {f'{upload_folder}/{entry["path"]}' for entry in entries}
    assert all(entry['category'] == 'training' and entry['boundingBoxes'] == [] for entry in entries)

columns, cell_width, cell_height = 10, 120, 200
rows = (len(frames) + columns - 1) // columns
sheet = Image.new('RGB', (columns * cell_width, 29 + rows * cell_height), '#141a21')
draw = ImageDraw.Draw(sheet)
font = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 14)
draw.text((11, 6), f'Closed glass door / {len(frames)} training negatives / source time', fill='#dbe9f1', font=font)
for position, (index, data) in enumerate(frames):
    x = (position % columns) * cell_width
    y = 29 + (position // columns) * cell_height
    with Image.open(io.BytesIO(data)) as photo:
        photo.thumbnail((cell_width - 8, cell_height - 23))
        sheet.paste(photo, (x + (cell_width - photo.width)//2, y))
    draw.text((x + 10, y + 180), f'{index/4:6.2f} s', fill='#dbe9f1', font=font)
sheet.save(outputs / 'door-video-180441-preview.jpg', quality=91)
print(f'{len(frames)} verified JPEGs. Skipped {dict(rejections)} from {len(candidates)} curated candidates.')
print(f'Views: {dict(Counter(row["view"] for row in records))}. ZIP: {archive.stat().st_size:,} bytes.')
