import os
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont


SOURCE = Path(os.environ["UNFREEZE_VIDEO"])
WORK = Path(__file__).resolve().parent
FFMPEG = "ffmpeg"


def extract(seconds, destination, width, filters):
    name = f"t{round(seconds * 1000):06d}.jpg"
    output = destination / name
    if not output.exists():
        result = subprocess.run(
            [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-nostdin",
             "-threads", "2", "-ss", f"{seconds:.3f}", "-i", str(SOURCE),
             "-map", "0:v:0", "-frames:v", "1", "-an", "-vf",
             f"{filters}scale={width}:-2:flags=area", "-q:v", "2", "-y", str(output)],
            check=True, capture_output=True,
        )
        if not output.exists():
            raise RuntimeError(f"No frame at {seconds:.3f} s: {result.stderr!r}")
    return output


def make_sheets(paths, destination):
    columns, rows = 5, 5
    cell_width, cell_height = 240, 157
    capacity = rows * columns
    font = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 15)
    for start in range(0, len(paths), capacity):
        group = paths[start : start + capacity]
        sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "#11171e")
        draw = ImageDraw.Draw(sheet)
        for index, path in enumerate(group):
            x = index % columns * cell_width
            y = index // columns * cell_height
            with Image.open(path) as image:
                image.thumbnail((cell_width - 6, 133))
                sheet.paste(image, (x + (cell_width - image.width) // 2, y + (133 - image.height) // 2))
            seconds = int(path.stem[1:]) / 1000
            draw.text((x + 7, y + 137), f"{start + index + 1:02d}  {seconds:6.2f} s", fill="white", font=font)
        sheet.save(destination / f"sheet-{start // capacity + 1:02d}.jpg", quality=90)


parser = argparse.ArgumentParser()
parser.add_argument("directory")
parser.add_argument("--step", type=float, default=2)
parser.add_argument("--start", type=float, default=0.25)
parser.add_argument("--end", type=float, default=138.5)
parser.add_argument("--width", type=int, default=448)
parser.add_argument("--times", type=Path)
parser.add_argument("--crop")
args = parser.parse_args()
destination = WORK / args.directory
destination.mkdir(exist_ok=True)
if args.times:
    times = [float(line) for line in args.times.read_text().splitlines() if line.strip()]
else:
    count = int((args.end - args.start) / args.step) + 1
    times = [args.start + index * args.step for index in range(count)]
filters = f"crop={args.crop}," if args.crop else ""
with ThreadPoolExecutor(max_workers=5) as pool:
    images = list(pool.map(lambda value: extract(value, destination, args.width, filters), times))
make_sheets(images, destination)
print(f"Extracted {len(images)} frames to {destination}")
