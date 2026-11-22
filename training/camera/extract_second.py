import os
from pathlib import Path
import subprocess
import sys


work = Path(__file__).resolve().parent
out = work / (sys.argv[2] if len(sys.argv) > 2 else 'second_4fps')
out.mkdir(exist_ok=True)
source = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ["UNFREEZE_VIDEO"])
ffmpeg = "ffmpeg"
result = subprocess.run([str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-nostdin',
                         '-y', '-threads', '5', '-i', str(source), '-an', '-map', '0:v:0',
                         '-vf', "fps=fps=4:start_time=0,scale=w='if(gt(iw,ih),960,540)':h='if(gt(iw,ih),540,960)':flags=area,setsar=1",
                         '-map_metadata', '-1', '-q:v', '2', '-start_number', '0', str(out / '%04d.jpg')],
                        capture_output=True, check=True)
print(f'Extracted {len(list(out.glob("*.jpg")))} frames.')
