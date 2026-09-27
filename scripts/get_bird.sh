#!/usr/bin/env bash
# Download everything the benchmark needs into data/bird/ (~1.5 GB on disk after unzip).
#   - BIRD mini-dev questions (HF, 0.9 MB) and SQLite databases (official Drive package, 763 MB)
#   - Arcwise-Plat-SQL corrected gold SQL (GitHub, 0.3 MB)
#   - BIRD train few-shot pool (HF, 2.7 MB; databases disjoint from mini-dev)
set -euo pipefail
cd "$(dirname "$0")/.." && mkdir -p data/bird && cd data/bird

HF=https://huggingface.co/datasets/birdsql
curl -sSL -o mini_dev_sqlite.json "$HF/bird_mini_dev/resolve/main/data/mini_dev_sqlite-00000-of-00001.json"
curl -sSL -o train_filtered.jsonl "$HF/bird23-train-filtered/resolve/main/data/train-00000-of-00001.jsonl"
curl -sSL -o arcwise_plat_sql_only.json \
  https://raw.githubusercontent.com/uiuc-kang-lab/text_to_sql_benchmarks/main/data/arcwise_plat_sql_only_with_diff.json

if [ ! -d dev_databases ]; then
  # Google Drive throttles single connections; fetch in 8 parallel byte ranges.
  URL="https://drive.usercontent.google.com/download?id=13VLWIwpw5E3d5DUkMvzw7hvHE67a4XkG&export=download&confirm=t"
  TOTAL=799944582; N=8; CH=$(( (TOTAL + N - 1) / N ))
  for i in $(seq 0 $((N-1))); do
    S=$((i*CH)); E=$((S+CH-1)); [ $E -ge $TOTAL ] && E=$((TOTAL-1))
    curl -sSL --retry 5 -r "$S-$E" -o "part$i" "$URL" &
  done; wait
  cat part{0..7} > minidev.zip && rm part*
  unzip -q minidev.zip $(unzip -l minidev.zip | awk '/\.sqlite$|database_description\/.*csv$/ {print $4}')
  rm minidev.zip
  # normalise layout to data/bird/dev_databases/<db_id>/<db_id>.sqlite
  src=$(dirname "$(find . -name 'california_schools.sqlite' | head -1)")
  mv "$(dirname "$src")" dev_databases 2>/dev/null || true
fi

python3 - <<'PY'
import json
mini = json.load(open("mini_dev_sqlite.json"))
arc = {str(x["question_id"]): x for x in json.load(open("arcwise_plat_sql_only.json"))}
out = [dict(m, SQL=arc[str(m["question_id"])]["SQL"]) for m in mini if str(m["question_id"]) in arc]
json.dump(out, open("mini_dev_arcwise.json", "w"), indent=1)
print(f"mini-dev: {len(mini)} questions; corrected gold for {len(out)}")
PY
