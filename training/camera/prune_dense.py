from pathlib import Path
import json

import numpy as np
from PIL import Image, ImageDraw, ImageFont


work = Path(__file__).resolve().parent
groups = json.loads((work / 'dense_groups.json').read_text())
all_indices = [index for indices in groups.values() for index in indices]
assert len(all_indices) == len(set(all_indices))
excluded = set(json.loads((work / 'dense_exclude.json').read_text())) if (work / 'dense_exclude.json').exists() else set()
font = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 13)
unique = {}
skipped = {}
features = {}


def frame_path(index):
    return work / 'dense' / f'{index:04d}.jpg'


for name, indices in groups.items():
    kept = []
    failed = {}
    comparison = (unique['clear_train'] + unique['narrow_train']) if name.endswith('_audit') else []
    for index in indices:
        if index in excluded:
            failed[index] = 'visual'
            continue
        with Image.open(frame_path(index)) as image:
            rgb = np.asarray(image)
            gray = image.convert('L')
            small = np.asarray(gray.resize((48, 27), Image.Resampling.BOX), dtype=np.float32)
            reduced = np.asarray(gray.resize((17, 9), Image.Resampling.BOX), dtype=np.int16)
            signature = (reduced[:, 1:] > reduced[:, :-1]).ravel()
        neutral_midgray = ((rgb >= 126) & (rgb <= 130)).all(axis=2)
        block_damage = (neutral_midgray.mean(axis=1) > 0.7).sum() >= 3
        if block_damage or np.mean((rgb == 128).all(axis=2)) > 0.035 or small.std() < 13:
            failed[index] = 'flat_or_decoder_damage'
            continue
        near_duplicate = None
        for previous in kept + comparison:
            previous_small, previous_signature = features[previous]
            delta = np.abs(previous_small - small).mean()
            hamming = (signature != previous_signature).sum()
            same_window = abs(index - previous) <= 8
            if delta < 3.5 or (delta < 7 and hamming <= 12) or (same_window and delta < 6):
                near_duplicate = previous
                break
        if near_duplicate is not None:
            failed[index] = f'near_duplicate_of_{near_duplicate}'
            continue
        features[index] = (small, signature)
        kept.append(index)
    unique[name] = kept
    skipped[name] = failed

(work / 'dense_selected.json').write_text(json.dumps(unique, indent=2))
(work / 'dense_skipped.json').write_text(json.dumps(skipped, indent=2))
for name, indices in unique.items():
    columns, cell_width, cell_height = 7, 195, 131
    sheet = Image.new('RGB', (columns * cell_width, ((len(indices) + columns - 1) // columns) * cell_height), '#121820')
    draw = ImageDraw.Draw(sheet)
    for offset, index in enumerate(indices):
        x, y = (offset % columns) * cell_width, (offset // columns) * cell_height
        with Image.open(frame_path(index)) as image:
            image.thumbnail((cell_width - 4, cell_height - 20))
            sheet.paste(image, (x + 2, y))
        draw.text((x + 4, y + 113), f'{index/4:6.2f}s  #{index:03d}', font=font, fill='white')
    sheet.save(work / f'v2-{name}.jpg', quality=89)
print({name: len(indices) for name, indices in unique.items()})
