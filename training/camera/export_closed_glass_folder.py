import json
from pathlib import Path
from zipfile import ZipFile


outputs = Path(__file__).resolve().parents[2] / 'outputs'
outputs.mkdir(exist_ok=True)
destination = outputs / 'edge-impulse-180441-training'
prefix = 'edge_impulse_train/'
with ZipFile(outputs / 'door-video-180441-closed-glass.zip') as source:
    manifest_data = source.read(prefix + 'info.labels')
    manifest = json.loads(manifest_data)
    assert manifest['version'] == 1 and len(manifest['files']) == 53
    images = {}
    for entry in manifest['files']:
        name = Path(entry['path'])
        assert name.parent == Path('training') and name.suffix == '.jpg'
        assert entry['category'] == 'training' and entry['boundingBoxes'] == []
        images[name] = source.read(prefix + entry['path'])
    assert len(images) == 53

(destination / 'training').mkdir(parents=True, exist_ok=True)
for name, data in images.items():
    (destination / name).write_bytes(data)
(destination / 'info.labels').write_bytes(manifest_data)
assert {path.relative_to(destination) for path in destination.rglob('*.jpg')} == images.keys()
assert all((destination / name).read_bytes() == data for name, data in images.items())
assert (destination / 'info.labels').read_bytes() == manifest_data
print(f'{len(images)} images and their annotations verified at {destination}')
