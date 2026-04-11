#!/usr/bin/env bash
# scripts/install-hooks.sh — install shared git hooks for all contributors
# Run once after cloning: bash scripts/install-hooks.sh
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_SRC="$REPO_ROOT/hooks"
HOOKS_DST="$REPO_ROOT/.git/hooks"

for hook in "$HOOKS_SRC"/*; do
    name="$(basename "$hook")"
    dest="$HOOKS_DST/$name"
    cp "$hook" "$dest"
    chmod +x "$dest"
    echo "Installed: $dest"
done

echo "All hooks installed. Run 'git commit' to verify."
