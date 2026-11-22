from pathlib import Path
import json

from PIL import Image, ImageDraw, ImageFont


work = Path(__file__).resolve().parent
groups = json.loads((work / 'dense_selected.json').read_text())
font = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 14)
categories = {
    'gallery_a': [i for i in groups['clear_train'] if 8 <= i <= 52 or 104 <= i <= 142],
    'gallery_b': [i for i in groups['clear_train'] if 168 <= i <= 178] + [i for i in groups['clear_audit'] if 476 <= i <= 496 or i in (524, 546, 548)],
    'vestibule': [354, 356, 366, 368, 374, 378, 380, 382, 384, 385, 387, 388, 416, 417, 433, 436, 440, 443, 288, 290, 294, 296, 297],
}
for title, indices in categories.items():
    columns, width, height = 5, 226, 136
    sheet = Image.new('RGB', (columns * width, ((len(indices) + columns - 1) // columns) * height), '#121820')
    draw = ImageDraw.Draw(sheet)
    for offset, index in enumerate(indices):
        x, y = (offset % columns) * width, (offset // columns) * height
        with Image.open(work / 'dense' / f'{index:04d}.jpg') as frame:
            bounds = (0, 125, 360, 305) if title.startswith('gallery') else (397, 145, 800, 351)
            detail = frame.crop(bounds)
            detail.thumbnail((width, height - 18))
            sheet.paste(detail, (x, y))
        draw.text((x + 4, y + 119), f'{index/4:6.2f}s  #{index:03d}', fill='white', font=font)
    sheet.save(work / f'check-{title}.jpg', quality=92)
