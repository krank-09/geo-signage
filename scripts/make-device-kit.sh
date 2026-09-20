#!/usr/bin/env bash
# Packages the display-laptop kit into dist/device-kit.zip (send this to each display laptop).
# The kit's GUIDE.md is generated from Part D of DOCUMENTATION.md (between the BEGIN/END display-guide markers),
# so there is only one place to edit it.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p dist
rm -f dist/device-kit.zip
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
mkdir "$stage/device-kit"
rsync -a --exclude '.env' --exclude '.venv' --exclude '.cache' --exclude '__pycache__' --exclude '.ruff_cache' --exclude '.pytest_cache' --exclude '.DS_Store' device/ "$stage/device-kit/"

if [ -f DOCUMENTATION.md ]; then
  {
    echo "# Display laptop setup guide"
    echo
    # Take the marked block; promote headings one level ("### D3. X" -> "## 3. X"), leaving code fences alone.
    awk '
      /<!-- BEGIN:display-guide -->/ { on = 1; next }
      /<!-- END:display-guide -->/   { on = 0 }
      !on { next }
      /^```/ { fence = !fence }
      !fence && /^###+ / { sub(/^#/, ""); sub(/^## D/, "## ") }
      { print }
    ' DOCUMENTATION.md
  } > "$stage/device-kit/GUIDE.md"
fi

(cd "$stage" && zip -qr "$OLDPWD/dist/device-kit.zip" device-kit)
echo "Created dist/device-kit.zip ($(du -h dist/device-kit.zip | cut -f1))"
unzip -Z1 dist/device-kit.zip | sed 's#^device-kit/##' | grep -v '/$' | sort | sed 's/^/  /'
