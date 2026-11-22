from collections import Counter
from hashlib import sha256
import io
import json
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from PIL import Image


work = Path(__file__).resolve().parent
outputs = work.parents[1] / 'outputs'
outputs.mkdir(exist_ok=True)
destination = outputs / 'edge-impulse-training'
sources = [
    ('door-video-expanded-dataset.zip', 49),
    ('door-video-155557-dataset.zip', 83),
]
records = []
assets = {}
pixel_hashes = set()
assert not destination.exists(), destination

for filename, expected in sources:
    with ZipFile(outputs / filename) as source:
        info = json.loads(source.read('edge_impulse_train/info.labels'))
        assert info['version'] == 1 and len(info['files']) == expected
        for record in info['files']:
            relative = PurePosixPath(record['path'])
            assert relative.parent == PurePosixPath('training') and relative.suffix == '.jpg'
            assert record['category'] == 'training' and record['label']['type'] == 'label'
            assert relative.name not in assets
            data = source.read(f'edge_impulse_train/{relative}')
            with Image.open(io.BytesIO(data)) as image:
                assert image.format == 'JPEG' and image.size in {(960, 540), (540, 960)}
                image.load()
                digest = sha256(image.tobytes()).digest()
                assert digest not in pixel_hashes, relative
                pixel_hashes.add(digest)
            assets[relative.name] = data
            records.append(record)

counts = Counter(record['label']['label'] for record in records)
assert counts == {'clear_ahead': 75, 'narrow_ahead': 57}
assert len({record['name'] for record in records}) == len(records)

(destination / 'training').mkdir(parents=True)
for name, data in assets.items():
    (destination / 'training' / name).write_bytes(data)
(destination / 'info.labels').write_text(
    json.dumps({'version': 1, 'files': records}, indent=2) + '\n', encoding='utf-8',
)

packed = json.loads((destination / 'info.labels').read_text(encoding='utf-8'))['files']
indexed = {record['path'] for record in packed}
actual = {path.relative_to(destination).as_posix() for path in destination.rglob('*.jpg')}
assert actual == indexed and len(actual) == len(records)
assert all((destination / 'training' / name).read_bytes() == data for name, data in assets.items())
print(f'{len(actual)} verified training images. {dict(counts)}')
print(destination)
