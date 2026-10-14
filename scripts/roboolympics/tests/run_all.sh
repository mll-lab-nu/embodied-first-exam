#!/bin/bash
# Run every family's referee test in the simulator image (not part of CI: it needs the image), N at a time.
#   scripts/roboolympics/tests/run_all.sh [N] [family_snake ...]
HERE="$(cd "$(dirname "$0")" && pwd)"; N="${1:-8}"; shift || true
names=("$@"); [ ${#names[@]} -eq 0 ] && names=($(cd "$HERE" && ls test_*.py | sed 's/^test_//; s/\.py$//'))
out="$(mktemp -d)"; fail=0
for n in "${names[@]}"; do
  ( RFO_OUT="$out/$n" "$HERE/../dev.sh" "/rfo/tests/test_$n.py" > "$out/$n.log" 2>&1; echo $? > "$out/$n.rc" ) &
  while [ "$(jobs -r | wc -l)" -ge "$N" ]; do sleep 1; done
done; wait
for n in "${names[@]}"; do
  if [ "$(cat "$out/$n.rc")" = 0 ] && grep -q "^PASS " "$out/$n.log"; then echo "PASS $n"; else echo "FAIL $n: $(tail -n 3 "$out/$n.log" | tr '\n' ' ' | cut -c1-300)"; fail=1; fi
done
echo "logs: $out"; exit $fail
