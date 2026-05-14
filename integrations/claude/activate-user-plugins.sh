#!/usr/bin/env bash
set -eu

plugin_activation_log="$HOME/.local/state/mempalace-plugin-activation.log"
mkdir -p "$(dirname "$plugin_activation_log")"

run_quiet() {
  {
    printf '[%s] ' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    printf '%s\n' "$*"
  } >> "$plugin_activation_log"
  "$@" >> "$plugin_activation_log" 2>&1
}

stale_copilot_plugin="$HOME/.copilot/installed-plugins/mempalace"
if [ -e "$stale_copilot_plugin" ]; then
  run_quiet rm -rf "$stale_copilot_plugin" || true
fi

if [ -x "${CLAUDE_BIN:-}" ]; then
  if [ -f "$HOME/.claude/settings.json" ]; then
    settings_tmp="$(mktemp)"
    jq 'del(.extraKnownMarketplaces.mempalace)' \
      "$HOME/.claude/settings.json" > "$settings_tmp"
    mv "$settings_tmp" "$HOME/.claude/settings.json"
  fi
  if [ -f "$HOME/.claude/plugins/known_marketplaces.json" ]; then
    marketplaces_tmp="$(mktemp)"
    jq 'del(.mempalace)' \
      "$HOME/.claude/plugins/known_marketplaces.json" > "$marketplaces_tmp"
    mv "$marketplaces_tmp" "$HOME/.claude/plugins/known_marketplaces.json"
  fi
  run_quiet "$CLAUDE_BIN" plugin marketplace remove mempalace || true
  run_quiet "$CLAUDE_BIN" plugin marketplace add "$MEMPALACE_CLAUDE_MARKETPLACE_PATH" || true
  run_quiet "$CLAUDE_BIN" plugin uninstall --scope project mempalace@mempalace || true
  run_quiet "$CLAUDE_BIN" plugin uninstall --scope user mempalace@mempalace || true
  run_quiet "$CLAUDE_BIN" plugin install --scope user mempalace@mempalace || true
  run_quiet "$CLAUDE_BIN" plugin enable mempalace@mempalace || true
fi
