"""Canonical two-mode task registry; historical task directories are immutable inputs."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
REGISTRY=ROOT/'suites/two-modes.json'
ARCHIVE=ROOT/'archive/task_versions/pre-unified-20260929'
PROTOCOL='docs/prompts/metaworldplus_codex_luna_high_two_modes.md'
VERSION='60min-v3'
BENCHMARKS=('vlabench','metaworldplus','robocasa','robocasa365','robocasa-gr1')
def read(path):return json.loads(Path(path).read_text())
def write(path,value):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def resolve(path):
 p=ROOT/path
 if p.exists():return p
 historical=ARCHIVE/path
 if historical.exists():return historical
 raise FileNotFoundError(path)
def rows():return read(REGISTRY)['instances']
