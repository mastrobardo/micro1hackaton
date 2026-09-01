#!/usr/bin/env bash
# Regenerate docs/diagrams/ from the typed JSON IR: interactive HTML + README images.
#
# Edit the JSON (ghostc.architecture.json / ghostc.workflow.json), never the HTML or PNGs.
#
# Needs: the archify skill (https://github.com/tt-a1i/archify), Node >= 22, Chrome, python3+PIL.
set -euo pipefail

ARCHIFY_HOME="${ARCHIFY_HOME:-$HOME/.claude/skills/archify}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIA="$ROOT/docs/diagrams"
WIDTH="${DIAGRAM_PNG_WIDTH:-2400}"

[ -f "$ARCHIFY_HOME/bin/archify.mjs" ] || {
  echo "archify not found at $ARCHIFY_HOME — set ARCHIFY_HOME" >&2; exit 1; }

echo "==> deliver (validate 9/9 showcase, then atomically commit the HTML)"
for pair in "architecture:ghostc.architecture:ghostc-architecture" \
            "workflow:ghostc.workflow:ghostc-workflow"; do
  IFS=: read -r type src out <<< "$pair"
  node "$ARCHIFY_HOME/bin/archify.mjs" deliver "$type" "$DIA/$src.json" "$DIA/$out.html" \
       --quality showcase --json | python3 -c \
       'import json,sys; d=json.load(sys.stdin); v=d["validation"]; print("   %s ok=%s %s/%s checks, %s errors, %s warnings"%(d["type"],d["ok"],v["checksPassed"],v["checkCount"],v["errors"],v["warnings"]))'
done

echo "==> browser evidence"
for out in ghostc-architecture ghostc-workflow; do
  node "$ARCHIFY_HOME/bin/archify.mjs" visual-check "$DIA/$out.html" --json | python3 -c \
       'import json,sys; d=json.load(sys.stdin); print("   %s: %s"%(d["artifact"]["path"].rsplit("/",1)[-1], d["status"]))'
done

echo "==> static images (viewer export, driven headlessly)"
for out in ghostc-architecture ghostc-workflow; do
  for theme in light dark; do
    node "$ROOT/scripts/archify-export.mjs" \
      "[{\"file\":\"$DIA/$out.html\",\"theme\":\"$theme\",\"format\":\"png\",\"out\":\"$DIA/$out.$theme.png\"}]"
  done
  node "$ROOT/scripts/archify-export.mjs" \
    "[{\"file\":\"$DIA/$out.html\",\"theme\":\"light\",\"format\":\"svg\",\"out\":\"$DIA/$out.svg\"}]"
done

echo "==> downscale to ${WIDTH}px + palette-quantize for the README"
python3 - "$DIA" "$WIDTH" <<'PY'
import os, sys
from PIL import Image
dia, width = sys.argv[1], int(sys.argv[2])
for name in ('ghostc-architecture', 'ghostc-workflow'):
    for theme in ('light', 'dark'):
        f = os.path.join(dia, f'{name}.{theme}.png')
        before = os.path.getsize(f)
        im = Image.open(f).convert('RGB')
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        # Flat vector art: a 256-colour palette is visually lossless and ~4x smaller.
        im.quantize(colors=256, method=Image.MEDIANCUT, dither=Image.NONE).save(f, optimize=True)
        print(f'   {os.path.basename(f)}  {before//1024} KB -> {os.path.getsize(f)//1024} KB')
PY

echo "done."
