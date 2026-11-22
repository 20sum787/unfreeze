from pathlib import Path
from PIL import Image, ImageDraw

base = Path(__file__).resolve().parent / 'final_frames'
times = [3400, 8250, 10250, 25300, 26250, 28250, 30250, 34250, 36250, 38250, 44250, 48250, 64250, 67400, 72250, 73200, 88250, 118250, 120250, 126250]
sheet = Image.new('RGB', (1200, 1000), '#11171e')
draw = ImageDraw.Draw(sheet)
for i, time in enumerate(times):
    with Image.open(base / f't{time:06d}.jpg') as frame:
        left = 0 if time in (3400, 8250, 10250, 25300, 26250, 28250, 30250, 34250, 36250, 38250, 44250, 118250, 120250) else (460 if time != 126250 else 240)
        crop = frame.crop((left, 145, left + 300, 319))
        x, y = i % 4 * 300, i // 4 * 200
        sheet.paste(crop, (x, y))
        draw.text((x + 8, y + 177), f'{time / 1000:.2f} s', fill='white')
sheet.save(base.parent / 'qa-crops.jpg', quality=91)
