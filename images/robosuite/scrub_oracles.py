"""Remove cap-x's human-written reference solutions from the image so agents cannot look them up.
ORACLE_CODE string constants -> None; env_configs/human_oracle_code/ deleted. Fails loudly if anything is left."""
import pathlib, re, shutil, sys
root = pathlib.Path("/opt/cap-x")
n = 0
for p in root.rglob("*.py"):
    if "third_party" in p.parts: continue
    s = p.read_text(errors="ignore")
    s2 = re.sub(r'ORACLE_CODE(\w*)\s*=\s*(r?"""|r?\'\'\')(.*?)\2', r'ORACLE_CODE\1 = None  # scrubbed', s, flags=re.S)
    s2 = re.sub(r'oracle_code\s*=\s*(r?"""|r?\'\'\')(.*?)\1', r'oracle_code = None  # scrubbed', s2, flags=re.S)
    if s2 != s: p.write_text(s2); n += 1
shutil.rmtree(root / "env_configs" / "human_oracle_code", ignore_errors=True)
left = [str(p) for p in root.rglob("*") if p.is_file() and "third_party" not in p.parts and p.suffix in {".py", ".yaml", ".yml", ".md", ".txt"}
        and re.search(r'sample_grasp_pose\("red cube"\)|ORACLE_CODE\w*\s*=\s*(r?"""|r?\'\'\')', p.read_text(errors="ignore"))]
print(f"scrubbed {n} files; leftovers: {left}")
sys.exit(1 if left else 0)
