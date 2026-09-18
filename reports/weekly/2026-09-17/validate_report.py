"""Validate this report's local references and existing video metadata."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import hashlib
import json
import re
import subprocess

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]


class Scan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []
        self.ids = []
        self.players = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a:
            self.ids.append(a['id'])
        for k in ['href', 'src', 'poster']:
            if a.get(k):
                self.refs.append(a[k])
        if tag == 'option' and a.get('value', '').endswith('.mp4'):
            self.refs.append(a['value'])
        if tag == 'video':
            self.players.append(a['src'])


def probe(p):
    result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=codec_name,width,height,nb_frames,duration,avg_frame_rate',
        '-of', 'json', str(p)], capture_output=True, text=True, timeout=30)
    d = dict(path=str(p.relative_to(ROOT)), passed=False)
    if result.returncode:
        d['error'] = result.stderr
        return d
    streams = json.loads(result.stdout).get('streams', [])
    if not streams:
        d['error'] = 'No video stream'
        return d
    d.update(streams[0])
    d['passed'] = int(d.get('nb_frames', '0')) > 0 and float(d.get('duration', '0')) > 0
    return d


def main():
    s = Scan()
    s.feed((OUT / 'index.html').read_text())
    markdown_refs = re.findall(r'\]\(([^\s)]+)\)', (OUT / 'weekly-report.md').read_text())
    s.refs.extend(markdown_refs)
    missing = []
    files = set()
    for ref in set(s.refs):
        u = urlsplit(ref)
        if u.scheme:
            continue
        if not u.path:
            if u.fragment not in s.ids:
                missing.append(ref)
            continue
        p = (OUT / unquote(u.path)).resolve()
        # This validator creates its own linked output after all checks.
        if p == OUT / 'validation.json':
            continue
        if not p.exists():
            missing.append(ref)
        elif p.is_file():
            files.add(p)
    videos = sorted(p for p in files if p.suffix == '.mp4')
    with ThreadPoolExecutor(max_workers=4) as pool:
        probes = list(pool.map(probe, videos))
    by_path = {p['path']: p for p in probes}
    report = json.loads((OUT / 'report.json').read_text())
    inspection = json.loads((OUT / 'inspection.json').read_text())
    inspection_issues = []
    expected_tasks = {t['id'] for t in report['tasks']} | {'rope_threading', 'knot_untying', 'buzz_wire_3d'}
    inspected_tasks = inspection['inspection']
    expected_gates = {'G1', 'G2', 'G3', 'G4', 'G5'}
    if set(inspected_tasks) != expected_tasks or len(inspected_tasks) != 10:
        inspection_issues.append('Inspection coverage does not match the ten report tasks')
    if {g['id'] for g in inspection['gates']} != expected_gates:
        inspection_issues.append('Five gate definitions are missing or duplicated')
    if inspection != report['inspection']:
        inspection_issues.append('Standalone and main JSON inspections differ')
    for task_id, task in inspected_tasks.items():
        if s.ids.count('inspect-' + task_id) != 1:
            inspection_issues.append(f'{task_id}: missing or duplicate inspection anchor')
        if set(task['gates']) != expected_gates:
            inspection_issues.append(f'{task_id}: incomplete five-gate assessment')
        for gate_id, gate in task['gates'].items():
            if gate['status'] not in inspection['status_labels']:
                inspection_issues.append(f'{task_id}/{gate_id}: invalid status')
            if not all(gate.get(k) for k in ['evidence', 'gap', 'references']):
                inspection_issues.append(f'{task_id}/{gate_id}: missing evidence, scope, or reference')
            for ref in gate['references']:
                if not (ROOT / ref).is_file():
                    inspection_issues.append(f'{task_id}/{gate_id}: missing source {ref}')
    mismatches = []
    manifest_results = []
    for task in report['tasks']:
        for m in task['media']:
            p = by_path[m['src']]
            if abs(float(p.get('duration', 0)) - m['duration_s']) > .15:
                mismatches.append(dict(video=m['src'], expected=m['duration_s'], actual=p.get('duration')))
            manifest = json.loads((ROOT / m['manifest']).read_text())
            manifest_videos = manifest.get('videos', manifest.get('video_files', {}))
            # Hash primary videos against existing archive evidence where stored.
            expected = None
            for value in manifest_videos.values() if isinstance(manifest_videos, dict) else manifest_videos:
                if isinstance(value, dict):
                    name = value.get('path', value.get('file', ''))
                    if Path(name).name == Path(m['src']).name:
                        expected = value.get('sha256')
                        break
            sha = None
            if expected:
                h = hashlib.sha256()
                with (ROOT / m['src']).open('rb') as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b''):
                        h.update(chunk)
                sha = h.hexdigest()
                if sha != expected:
                    mismatches.append(dict(video=m['src'], error='Archive SHA-256 mismatch'))
            manifest_results.append(dict(manifest=m['manifest'], video=m['src'],
                expected_sha256=expected, actual_sha256=sha,
                hash_matches=(sha == expected) if expected else None))
    failed = [p for p in probes if not p['passed']]
    result = dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),
        passed=not (missing or failed or mismatches or inspection_issues),
        local_reference_count=len(set(s.refs)), video_file_count=len(videos),
        embedded_player_count=len(s.players), missing_references=missing,
        failed_probes=failed, archive_mismatches=mismatches,
        inspected_task_count=len(inspected_tasks),
        gate_assessment_count=sum(len(t['gates']) for t in inspected_tasks.values()),
        inspection_issues=inspection_issues,
        primary_video_archive_hashes=manifest_results, videos=probes,
        scope='HTML and Markdown local links, ten-task five-gate inspection coverage and source references, all linked camera streams via ffprobe, primary duration and available archive hashes. Existing decode evidence reused; physics and full video decoding not rerun. No browser automation available.')
    (OUT / 'validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ['videos','primary_video_archive_hashes']}, ensure_ascii=False, indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
