#!/bin/bash
# Reproducible production build for a React + Vite + Tailwind app.
# 1) vite bundles the app (copies public/ -> outDir, incl. static signup/login pages)
# 2) tailwind compiles the stylesheet AFTER vite (vite/lightningcss does NOT process @tailwind)
set -e
cd "$(dirname "$0")"

BUILD_DIR="frontend/build"   # change to your vite outDir
TAILWIND_CONFIG="./tailwind.config.js"
CSS_INPUT="./src/index.css"

echo "== Vite build =="
node_modules/.bin/vite build

echo "== Tailwind compile (post-vite) =="
CSSFILE=$(ls "$BUILD_DIR"/assets/index-*.css 2>/dev/null | head -1)
if [ -n "$CSSFILE" ]; then
  node_modules/.bin/tailwindcss -c "$TAILWIND_CONFIG" -i "$CSS_INPUT" -o "$CSSFILE"
  echo "compiled -> $CSSFILE ($(wc -c < "$CSSFILE") bytes)"
else
  echo "WARN: no built css asset found; verify outDir/BUILD_DIR" >&2
fi

echo "== Build complete =="
ls -la "$BUILD_DIR"/
