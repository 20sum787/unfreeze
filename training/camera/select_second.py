from collections import Counter
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


work = Path(__file__).resolve().parent
groups = json.loads((work / 'second_groups.json').read_text())
all_indices = [i for indices in groups.values() for i in indices]
assert len(all_indices) == len(set(all_indices))
features = {}
result = {}
rejections = {}
font = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 13)


def source(index):
    return work / 'second_4fps' / f'{index:04d}.jpg'


def aligned_distance(left, right):
    return min(float(np.mean(np.abs(left[1:-1, 1:-1] - right[y:y+42, x:x+22])))
               for y in range(3) for x in range(3))


for group, indices in groups.items():
    kept = []
    category = group.split('_', 1)[0]
    history = [i for name, selected in result.items() if name.startswith(category + '_') for i in selected]
    for index in indices:
        with Image.open(source(index)) as frame:
            frame.load()
            assert frame.size == (540, 960)
            pixels = np.asarray(frame)
            neutral_midgray = ((pixels >= 126) & (pixels <= 130)).all(axis=2)
            damaged = np.count_nonzero(neutral_midgray.mean(axis=1) > 0.75) >= 4
            thumb = np.asarray(frame.convert('L').resize((24, 44), Image.Resampling.BOX), dtype=np.float32)
        if damaged or thumb.std() < 13:
            rejections[index] = 'flat_or_damaged'
            continue
        match = None
        for previous in kept + history:
            distance = aligned_distance(thumb, features[previous])
            if distance < 3.2 or (abs(index - previous) <= 6 and distance < 5.2):
                match = previous
                break
        if match is not None:
            rejections[index] = f'near_duplicate_of_{match}'
            continue
        features[index] = thumb
        kept.append(index)
    result[group] = kept

(work / 'second_selected.json').write_text(json.dumps(result, indent=2))
(work / 'second_rejected.json').write_text(json.dumps(rejections, indent=2))
for category in ('clear', 'narrow', 'review'):
    indices = sorted(i for name, selected in result.items() if name.startswith(category + '_') for i in selected)
    for offset in range(0, len(indices), 50):
        page = indices[offset:offset + 50]
        columns, width, height = 10, 118, 197
        sheet = Image.new('RGB', (columns * width, ((len(page) + columns - 1) // columns) * height), '#151b21')
        draw = ImageDraw.Draw(sheet)
        for position, index in enumerate(page):
            x, y = position % columns * width, position // columns * height
            with Image.open(source(index)) as frame:
                frame.thumbnail((width - 5, height - 20))
                sheet.paste(frame, (x + (width - frame.width) // 2, y))
            draw.text((x + 4, y + height - 17), f'{index/4:5.2f}s #{index}', font=font, fill='white')
        sheet.save(work / f'second-qa-{category}-{offset//50}.jpg', quality=89)
print({name: len(indices) for name, indices in result.items()})
print(Counter({category: sum(len(ids) for name, ids in result.items() if name.startswith(category+'_'))
               for category in ('clear', 'narrow', 'review')}))
