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
source = 'IPS_2026-11-21.15.29.42.1650.mp4'
site, clip = 'gallery_glass_door_01', 'ips_20261121_152942'
groups = json.loads((work / 'dense_selected.json').read_text(encoding='utf-8'))
train_dir, check_dir, review_dir = 'edge_impulse_train', 'same_site_check', 'review_unlabeled'
annotations = {train_dir: [], check_dir: []}
manifest = []
hashes = set()
archive = outputs / 'door-video-expanded-dataset.zip'


def describe(group, index):
    if group.startswith('narrow'):
        return 'narrow_ahead', 'vestibule_forward', 'visual_proxy_width_unmeasured'
    if group.startswith('clear'):
        subtype = 'gallery_background' if index in (84, 88, 456) else 'gallery_side_pass'
        return 'clear_ahead', subtype, 'visually_reviewed_from_video'
    if index == 101:
        return '', 'side_opening_direction_uncertain', 'needs_review'
    if index in (306, 308, 394):
        return '', 'side_stairwell', 'needs_review'
    return '', 'glass_or_travel_direction_uncertain', 'needs_review'


with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as output:
    for group, indices in groups.items():
        category = 'training' if group.endswith('_train') else 'testing' if group.endswith('_audit') else ''
        folder = {'training': train_dir, 'testing': check_dir, '': review_dir}[category]
        for index in indices:
            label, subtype, basis = describe(group, index)
            sample = f'{label or "review"}.{clip}.{index * 250:06d}'
            frame = work / 'dense' / f'{index:04d}.jpg'
            relative_path = f'{category}/{sample}.jpg' if category else f'{sample}.jpg'
            path = f'{folder}/{relative_path}'
            data = frame.read_bytes()
            with Image.open(io.BytesIO(data)) as photo:
                assert photo.format == 'JPEG' and photo.size == (960, 540)
                photo.load()
                digest = hashlib.sha256(photo.tobytes()).digest()
                assert digest not in hashes, frame
                hashes.add(digest)
            output.writestr(path, data)
            if label:
                annotations[folder].append({
                    'path': relative_path, 'name': sample, 'category': category,
                    'label': {'type': 'label', 'label': label},
                    'metadata': {'site_id': site, 'clip_id': clip, 'source_ms': str(index * 250),
                                 'scene_type': subtype, 'label_basis': basis},
                })
            manifest.append({'file': path, 'label': label, 'subset': folder, 'source_seconds': f'{index/4:.2f}',
                             'site_id': site, 'clip_id': clip, 'scene_type': subtype, 'label_basis': basis,
                             'measured_clear_width_cm': ''})
    for folder, entries in annotations.items():
        output.writestr(f'{folder}/info.labels', json.dumps({'version': 1, 'files': entries}, indent=2))
    manifest_io = io.StringIO(newline='')
    writer = csv.DictWriter(manifest_io, fieldnames=list(manifest[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(manifest)
    output.writestr('frame_manifest.csv', manifest_io.getvalue().encode('utf-8-sig'))
    summary = Counter((record['subset'], record['label']) for record in manifest)
    clear_train, narrow_train = (summary[train_dir, label] for label in ('clear_ahead', 'narrow_ahead'))
    clear_test, narrow_test = (summary[check_dir, label] for label in ('clear_ahead', 'narrow_ahead'))
    output.writestr('README.txt', f'''Chest-camera frame selection
Source: {source}, about 139 seconds. Candidates were sampled at 4 Hz, reviewed for angle, blur and occlusion, then screened for near duplicates using thumbnail brightness and gradient hashes. JPEGs retain the full 960 x 540 frame.
edge_impulse_train/ contains {clear_train} clear_ahead and {narrow_train} narrow_ahead frames. Upload this folder as Training. info.labels includes class and source metadata. Replace earlier selections from the same video to avoid duplicates.
clear_ahead includes side passes and open areas. narrow_ahead is a visual proxy for looking along a vestibule and includes exit approaches. Width was not measured, so the labels cannot verify an 85 cm limit. Few frontal entries were recorded; cue lead time needs new recordings.
same_site_check/ contains {clear_test} clear and {narrow_test} narrow views. Training and check frames are separated by at least two seconds and screened for near duplicates, but share the background. Treat this as a same-site test.
review_unlabeled/ contains {summary[review_dir, '']} difficult frames. Consult the original recording for passability, direction and width. frame_manifest.csv records source time, use and label basis. Keep near-duplicate sequences together. Apply augmentations during training.
https://docs.edgeimpulse.com/studio/projects/data-acquisition/dataset/uploader
'''.encode('utf-8-sig'))

train_indices = groups['clear_train'] + groups['narrow_train']
test_indices = groups['clear_audit'] + groups['narrow_audit']
assert min(abs(train - test) for train in train_indices for test in test_indices) >= 8
with zipfile.ZipFile(archive) as output:
    assert output.testzip() is None
    images = {name for name in output.namelist() if name.endswith('.jpg')}
    assert images == {row['file'] for row in manifest}
    for folder, expected in annotations.items():
        actual = json.loads(output.read(f'{folder}/info.labels'))['files']
        assert actual == expected
        assert {f'{folder}/{entry["path"]}' for entry in actual} == {p for p in images if p.startswith(f'{folder}/')}

width, height = 224, 151
preview = Image.new('RGB', (width * 6, height * len(groups)), '#141a21')
draw = ImageDraw.Draw(preview)
font = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 14)
for row, (group, indices) in enumerate(groups.items()):
    size = min(6, len(indices))
    picks = [indices[round(i * (len(indices)-1) / max(1, size-1))] for i in range(size)]
    for col, index in enumerate(picks):
        x, y = col * width, row * height
        with Image.open(work / 'dense' / f'{index:04d}.jpg') as frame:
            frame.thumbnail((width - 8, 123))
            preview.paste(frame, (x + 4, y + 2))
        draw.text((x + 6, y + 127), f'{index/4:6.2f}s   {group.upper()}', font=font, fill='#dbe9f1')
preview.save(outputs / 'door-video-expanded-preview.jpg', quality=92)
print(f'{len(manifest)} images, {clear_train}+{narrow_train} train, {clear_test}+{narrow_test} check, {summary[review_dir, ""]} review. {archive.stat().st_size:,} bytes.')
