#!/usr/bin/env bash
set -eu

codex_repo="$HOME/.codex/.tmp/plugins"
marketplace="$codex_repo/.agents/plugins/marketplace.json"
source_plugin="$HOME/.agents/plugins/plugins/mempalace"
target_plugin="$codex_repo/plugins/mempalace"

if [ ! -e "$marketplace" ] || [ ! -e "$source_plugin" ]; then
  exit 0
fi

mkdir -p "$codex_repo/plugins"
ln -sfn "$source_plugin" "$target_plugin"

tmp="$(mktemp)"
jq '
  .plugins |= (
    if any(.name == "mempalace") then
      map(
        if .name == "mempalace" then
          .source = {"source":"local","path":"./plugins/mempalace"}
          | .policy = {"installation":"INSTALLED_BY_DEFAULT","authentication":"ON_INSTALL"}
          | .category = "Coding"
        else
          .
        end
      )
    else
      . + [{
        "name": "mempalace",
        "source": {"source":"local","path":"./plugins/mempalace"},
        "policy": {"installation":"INSTALLED_BY_DEFAULT","authentication":"ON_INSTALL"},
        "category": "Coding"
      }]
    end
  )
' "$marketplace" > "$tmp"

if cmp -s "$tmp" "$marketplace"; then
  rm -f "$tmp"
  exit 0
fi

mv "$tmp" "$marketplace"
