#!/usr/bin/env bash
set -eu

state_dir="$HOME/.local/state/mempalace-codex-ingest"
state_file="$state_dir/state.tsv"
log_file="$state_dir/ingest.log"
lock_dir="$state_dir/lock"
sessions_root="$HOME/.codex/sessions"
stable_after="${MEMPALACE_CODEX_STABLE_AFTER:-120}"
max_files_per_run="${MEMPALACE_CODEX_MAX_FILES_PER_RUN:-25}"

mkdir -p "$state_dir"
touch "$state_file"

if ! mkdir "$lock_dir" 2>/dev/null; then
  exit 0
fi

tmp_state="$(mktemp)"
tmp_candidates="$(mktemp)"
cleanup() {
  rm -f "$tmp_state" "$tmp_candidates"
  rmdir "$lock_dir" 2>/dev/null || true
}
trap cleanup EXIT

log() {
  printf '[%s] %s\n' "$(date -Is)" "$*" >> "$log_file"
}

if [ ! -d "$sessions_root" ]; then
  exit 0
fi

cp "$state_file" "$tmp_state"
now="$(date +%s)"

find "$sessions_root" -type f -name 'rollout-*.jsonl' -printf '%T@ %p\n' \
  | sort -n \
  > "$tmp_candidates"

processed=0
while IFS= read -r candidate; do
  mtime_float="${candidate%% *}"
  path="${candidate#* }"

  if [ -z "$path" ] || [ ! -f "$path" ]; then
    continue
  fi

  mtime="${mtime_float%%.*}"
  if [ -z "$mtime" ]; then
    continue
  fi

  if grep -Fqx "$path	$mtime" "$tmp_state"; then
    continue
  fi

  age="$((now - mtime))"
  if [ "$age" -lt "$stable_after" ]; then
    continue
  fi

  if ! tail -n 1 "$path" | grep -Fq '"task_complete"'; then
    continue
  fi

  tmp_dir="$(mktemp -d)"
  tmp_file="$tmp_dir/$(basename "$path")"
  cp "$path" "$tmp_file"

  if mempalace mine "$tmp_dir" --mode convos --wing codex-sessions --agent mempalace >> "$log_file" 2>&1; then
    printf '%s\t%s\n' "$path" "$mtime" >> "$tmp_state"
    processed="$((processed + 1))"
    log "ingested $path"
  else
    status="$?"
    log "ingest failed with exit $status for $path"
  fi

  rm -rf "$tmp_dir"

  if [ "$processed" -ge "$max_files_per_run" ]; then
    break
  fi
done < "$tmp_candidates"

sort -u "$tmp_state" -o "$state_file"
