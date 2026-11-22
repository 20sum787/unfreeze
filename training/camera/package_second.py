from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile

from PIL import Image, ImageDraw, ImageFont


work = Path(__file__).resolve().parent
outputs = work.parents[1] / 'outputs'
outputs.mkdir(exist_ok=True)
archive = outputs / 'door-video-155557-dataset.zip'
clip, site = 'vid_20261121_155557', 'gallery_glass_door_01'
selected = json.loads((work / 'second_selected.json').read_text())
train_root = 'edge_impulse_train'
review_root = 'review_unlabeled'
subtypes = {
    'clear_gallery_side': ('clear_ahead', 'gallery_side_pass', 'wide_or_lateral_route_visually_reviewed'),
    'clear_open_floor': ('clear_ahead', 'open_gallery_floor', 'wide_route_visually_reviewed'),
    'narrow_entry_view': ('narrow_ahead', 'inside_vestibule_entry_view', 'visual_proxy_width_unmeasured'),
    'narrow_forward_to_room': ('narrow_ahead', 'vestibule_toward_room', 'visual_proxy_width_unmeasured'),
    'narrow_open_threshold': ('narrow_ahead', 'open_threshold_from_inside', 'visual_proxy_width_unmeasured'),
    'narrow_forward_to_gallery': ('narrow_ahead', 'vestibule_toward_gallery', 'visual_proxy_width_unmeasured'),
    'review_closed_or_turn': ('', 'door_state_or_travel_direction_uncertain', 'needs_review'),
}


def frame_path(index):
    return work / 'second_4fps' / f'{index:04d}.jpg'


labels = []
records = []
pixel_hashes = set()
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as output:
    for group, indices in selected.items():
        label, scene, basis = subtypes[group]
        for index in indices:
            source_ms = index * 250
            sample = f'{label or "review"}.{clip}.{source_ms:06d}'
            if label:
                path = f'training/{sample}.jpg'
                full_path = f'{train_root}/{path}'
                labels.append({'path': path, 'name': sample, 'category': 'training',
                               'label': {'type': 'label', 'label': label},
                               'metadata': {'site_id': site, 'clip_id': clip, 'source_ms': str(source_ms),
                                            'scene_type': scene, 'label_basis': basis, 'orientation': 'portrait'}})
            else:
                full_path = f'{review_root}/{sample}.jpg'
            original = frame_path(index).read_bytes()
            with Image.open(io.BytesIO(original)) as image:
                image.load()
                assert image.size == (540, 960) and image.format == 'JPEG' and not image.getexif()
                digest = hashlib.sha256(image.tobytes()).digest()
                assert digest not in pixel_hashes
                pixel_hashes.add(digest)
            output.writestr(full_path, original)
            records.append({'file': full_path, 'label': label, 'scene_type': scene, 'label_basis': basis,
                            'source_seconds': f'{source_ms / 1000:.2f}', 'site_id': site, 'clip_id': clip,
                            'measured_clear_width_cm': ''})
    output.writestr(f'{train_root}/info.labels', json.dumps({'version': 1, 'files': labels}, indent=2))
    manifest = io.StringIO(newline='')
    writer = csv.DictWriter(manifest, fieldnames=list(records[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(records)
    output.writestr('frame_manifest.csv', manifest.getvalue().encode('utf-8-sig'))
    stats = Counter(row['label'] for row in records)
    threshold = len(selected['narrow_open_threshold'])
    output.writestr('README.txt', f'''VID20261121155557.mp4: narrow-passage supplement
{len(records)} images, {len(labels)} labeled. Portrait JPEGs retain the 540 x 960 frame. Review at 4 Hz removed occlusion, clear blur and near duplicates. The CSV includes timestamps and label rationale.
Upload edge_impulse_train as Training. This batch can supplement 49 earlier landscape frames. Check the Studio preprocessing preview for floor and door visibility and use the same transforms at deployment.
{stats['clear_ahead']} clear_ahead side-pass or open-floor frames. {stats['narrow_ahead']} narrow_ahead frames face the vestibule, including {threshold} views of a partly open door and threshold. Clear width and cue lead time remain unmeasured.
Review {stats['']} unlabeled glass doors, side glances and ambiguous routes before upload. These clips share site ID {site}. An independent site is needed to evaluate generalization.

'''.encode('utf-8-sig'))

with zipfile.ZipFile(archive) as output:
    assert output.testzip() is None
    jpgs = {path for path in output.namelist() if path.endswith('.jpg')}
    assert jpgs == {row['file'] for row in records}
    packed = json.loads(output.read(f'{train_root}/info.labels'))['files']
    assert packed == labels and {f'{train_root}/{item["path"]}' for item in packed} == {
        path for path in jpgs if path.startswith(f'{train_root}/')}

preview_rows = [
    ('Clear / gallery', selected['clear_gallery_side']),
    ('Clear / open floor', selected['clear_open_floor']),
    ('Narrow / inside vestibule', sorted(selected['narrow_entry_view'] + selected['narrow_forward_to_room']
                                       + selected['narrow_forward_to_gallery'])),
    ('Narrow / open threshold', selected['narrow_open_threshold']),
    ('Review / unlabeled', selected['review_closed_or_turn']),
]
width, height, columns = 154, 216, 8
preview = Image.new('RGB', (width * columns, height * len(preview_rows)), '#141a21')
draw = ImageDraw.Draw(preview)
font = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 15)
for row, (title, indices) in enumerate(preview_rows):
    capacity = min(len(indices), columns)
    picks = [indices[round(i * (len(indices) - 1) / max(1, capacity - 1))] for i in range(capacity)]
    y = row * height
    draw.text((12, y + 3), f'{title} ({len(indices)})', font=font, fill='#dbe9f1')
    for column, index in enumerate(picks):
        x = column * width
        with Image.open(frame_path(index)) as frame:
            frame.thumbnail((width - 8, height - 44))
            preview.paste(frame, (x + (width-frame.width)//2, y + 22))
        draw.text((x + 32, y + height - 19), f'{index/4:.2f}s', font=font, fill='#dbe9f1')
preview.save(outputs / 'door-video-155557-preview.jpg', quality=91)
print(f'{len(records)} total, {stats["clear_ahead"]} clear, {stats["narrow_ahead"]} narrow, {threshold} open threshold, {stats[""]} review.')
