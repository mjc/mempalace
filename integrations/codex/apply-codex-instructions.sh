#!/usr/bin/env bash
set -eu

config_file="$HOME/.codex/config.toml"
config_dir="$(dirname "$config_file")"
tmp="$(mktemp)"

mkdir -p "$config_dir"
touch "$config_file"

awk '
  /^# BEGIN managed by home-manager: codex-mempalace-instructions$/ { skip = 1; next }
  /^# END managed by home-manager: codex-mempalace-instructions$/ { skip = 0; next }
  skip != 1 { print }
' "$config_file" > "$tmp"

{
  cat <<'EOF'
# BEGIN managed by home-manager: codex-mempalace-instructions
developer_instructions = """
EOF
  cat "$MEMPALACE_CODEX_DEVELOPER_INSTRUCTIONS_PATH"
  cat <<'EOF'
"""
# END managed by home-manager: codex-mempalace-instructions

EOF
  cat "$tmp"
} > "$config_file"

rm -f "$tmp"
