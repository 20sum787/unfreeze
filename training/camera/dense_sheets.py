from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont


work = Path(__file__).resolve().parent
start, end, step, columns, rows = map(int, sys.argv[1:6])
directory = sys.argv[6] if len(sys.argv) > 6 else 'dense'
size = columns * rows
fonts = Path('C:/Windows/Fonts')
font = ImageFont.truetype(str(fonts / 'consola.ttf'), 14)
indices = list(range(start, end + 1, step))
for page, offset in enumerate(range(0, len(indices), size), 1):
    group = indices[offset:offset + size]
    cell_w, cell_h = (126, 213) if directory.endswith('_4fps') else (188, 124)
    sheet = Image.new('RGB', (columns * cell_w, ((len(group) + columns - 1) // columns) * cell_h), '#131922')
    draw = ImageDraw.Draw(sheet)
    for i, index in enumerate(group):
        x, y = (i % columns) * cell_w, (i // columns) * cell_h
        with Image.open(work / directory / f'{index:04d}.jpg') as frame:
            frame.thumbnail((cell_w - 4, cell_h - 20))
            sheet.paste(frame, (x + (cell_w - frame.width) // 2, y + 1))
        draw.text((x + 4, y + cell_h - 18), f'{index / 4:5.2f}s [{index}]', font=font, fill='white')
    sheet.save(work / f'{directory}-{start}-{step}-{page}.jpg', quality=90)
