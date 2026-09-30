#!/usr/bin/env bash
# Generated task dirs must be what their generator renders from its sources today: edit subset.toml, facts.json
# or a template and forget to re-render, and the tasks go on telling the agent the old text -- a pass mark, an
# episode limit. Renders into a scratch copy of the repo and compares.
root="$(cd "$(dirname "$0")/.." && pwd)"; rc=0
for gen in "$root"/scripts/*/gen_tasks.py; do
  sim=$(basename "$(dirname "$gen")"); tmp=$(mktemp -d)
  mkdir -p "$tmp/scripts" "$tmp/images"
  cp -r "$root/scripts/$sim" "$root/scripts/limited" "$tmp/scripts/"; cp -r "$root/tasks" "$tmp/"
  cp "$root/images/VERSION" "$tmp/images/"
  if ! out=$(python3 "$tmp/scripts/$sim/gen_tasks.py" render 2>&1); then
    echo "FAIL scripts/$sim/gen_tasks.py render: $out"; rc=1
  else
    stale=$(diff -rq "$root/tasks" "$tmp/tasks" | sed -E -e "s|^Files $root/(.*) and .* differ$|FAIL \1 differs from its render|" \
      -e "s|^Only in $tmp/(.*): (.*)$|FAIL \1/\2 is missing|")
    [ -n "$stale" ] && { echo "$stale"
      echo "FAIL tasks/ is not what scripts/$sim/gen_tasks.py renders: run its \`render\`, then \`harbor add --scan .\` in tasks/"; rc=1; }
    rendered=$(sed -n 's|^rendered tasks/||p' <<<"$out")   # a family taken out of subset.toml leaves its dirs behind
    for d in "$root"/tasks/"$sim"-*/; do
      [ -d "$d" ] || continue; d=$(basename "$d")
      grep -qxF "$d" <<<"$rendered" || { echo "FAIL tasks/$d: scripts/$sim/gen_tasks.py no longer renders it"; rc=1; }
    done
  fi
  rm -rf "$tmp"
done
exit $rc
