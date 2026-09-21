"""Create presentation playback copies; keep archived demonstration MP4s untouched."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
ASSETS = OUT / '.weekly_2026_09_19'
MEDIA = ASSETS / 'media'
MEDIA.mkdir(parents=True, exist_ok=True)
GROUP_IDS = ['coil_base', 'keyhole_base', 'horseshoe_base', 'hedgehog_side',
             'lock_base', 'fiber_base', 'claws_a', 'knot_base', 'buzz_f3',
             'rope_prefix', 'blanket_latest']
groups = {g['id']: g for g in json.loads((ROOT / 'reports/weekly/2026-09-19/demo_inventory.json').read_text())}
thumbs = json.loads((ASSETS / 'thumbnails.json').read_text())
thumbmap = {(t['group'], t['camera']): t for t in thumbs}


def probe(path):
    return json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
        'stream=codec_name,width,height,pix_fmt,avg_frame_rate,nb_frames,duration',
        '-of', 'json', str(path)]))['streams'][0]


def prepare(key):
    gid, cam = key
    source = Path(groups[gid]['videos'][cam])
    output = MEDIA / f'{gid}_{cam}.mp4'
    src = probe(source)
    # No temporal resampling, trimming, or overlay. Only presentation compression.
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                    '-threads', '2', '-i', str(source), '-map', '0:v:0', '-an',
                    '-vf', "scale=w='min(960,iw)':h=-2", '-c:v', 'libx264',
                    '-preset', 'fast', '-crf', '26', '-pix_fmt', 'yuv420p',
                    '-threads', '2', '-vsync', '0', '-movflags', '+faststart', str(output)],
                   check=True)
    dst = probe(output)
    assert src['nb_frames'] == dst['nb_frames'], (key, src, dst)
    assert src['avg_frame_rate'] == dst['avg_frame_rate'], (key, src, dst)
    assert abs(float(src['duration']) - float(dst['duration'])) < .001, (key, src, dst)
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-xerror',
                    '-threads', '2', '-i', str(output), '-f', 'null', '-'], check=True)
    t = thumbmap.get(key)
    if t is None:
        stamp = float(src['duration']) * .5
        poster = ASSETS / f'{gid}_{cam}.jpg'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-ss', str(stamp), '-i', str(source), '-frames:v', '1',
                        '-q:v', '3', str(poster)], check=True)
        t = dict(group=gid, camera=cam, source=str(source), time_s=stamp, image=str(poster))
    row = dict(group=gid, camera=cam, source=str(source), playback_file=str(output),
               source_probe=src, playback_probe=dst, bytes=output.stat().st_size,
               sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
               full_decode=True, frames_and_timing_preserved=True, poster=t)
    print(f'{gid}/{cam}: {row["bytes"]/1e6:.2f} MB, {dst["nb_frames"]} frames', flush=True)
    return row


if __name__ == '__main__':
    keys = []
    for gid in GROUP_IDS:
        cams = (['agentview', 'front_oblique', 'wrist'] if 'agentview' in groups[gid]['videos']
                else ['cam_high', 'cam_low', 'cam_left_wrist', 'cam_right_wrist'])
        keys.extend((gid, cam) for cam in cams)
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(prepare, keys))
    for row in records:
        thumbmap[(row['group'], row['camera'])] = row['poster']
    (ASSETS / 'thumbnails.json').write_text(json.dumps(list(thumbmap.values()), ensure_ascii=False, indent=2) + '\n')
    (ASSETS / 'embedded_media.json').write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n')
    print(f'Validated {len(records)} full videos; {sum(r["bytes"] for r in records)/1e6:.2f} MB', flush=True)
