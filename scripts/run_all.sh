#!/usr/bin/env bash
# Full BIRD mini-dev ablation: 4 presets, then re-score against corrected gold, then report.
# Resumable: re-running skips finished questions; LLM calls are cached.
set -uo pipefail
cd "$(dirname "$0")/.."
DATA=data/bird/mini_dev_sqlite.json
DBS=data/bird/dev_databases
for preset in full bare mschema values; do
  echo "=== $preset $(date)"
  .venv/bin/t2sql eval --data $DATA --db-root $DBS --preset $preset --concurrency ${CONCURRENCY:-3}
done
for r in runs/*/; do .venv/bin/t2sql rescore "$r" > /dev/null; done
.venv/bin/t2sql report runs
echo "=== done $(date)"
