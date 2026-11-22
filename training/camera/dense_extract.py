import os
from pathlib import Path
import subprocess


work = Path(__file__).resolve().parent
out = work / 'dense'
out.mkdir(exist_ok=True)
source = Path(os.environ["UNFREEZE_VIDEO"])
ffmpeg = "ffmpeg"
subprocess.run([str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-nostdin',
                '-y', '-threads', '5', '-i', str(source), '-an', '-map', '0:v:0',
                '-vf', 'fps=fps=4:start_time=0,scale=960:540:flags=area',
                '-q:v', '2', '-start_number', '0', str(out / '%04d.jpg')], check=True)
print(f'Extracted {len(list(out.glob("*.jpg")))} candidate frames.')
