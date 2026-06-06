#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
PORT="${1:-5173}"

cd "$FRONTEND_DIR"

if command -v pnpm >/dev/null 2>&1; then
  if [ ! -d node_modules ]; then
    pnpm install
  fi
  exec pnpm dev -- --port "$PORT"
fi

if command -v npm >/dev/null 2>&1; then
  if [ ! -d node_modules ]; then
    npm install
  fi
  exec npm run dev -- --port "$PORT"
fi

CODEX_NODE=""
for candidate in \
  "/Applications/Codex.app/Contents/Resources/node" \
  "$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
do
  if [ -x "$candidate" ]; then
    CODEX_NODE="$candidate"
    break
  fi
done

if [ -z "$CODEX_NODE" ]; then
  echo "No pnpm/npm found, and no Codex Node runtime was available." >&2
  exit 1
fi

NODE_BIN_DIR="/tmp/codex-node-bin"
NODE_ADHOC="/tmp/codex-node-adhoc"
mkdir -p "$NODE_BIN_DIR"
cp "$CODEX_NODE" "$NODE_ADHOC"
xattr -cr "$NODE_ADHOC" 2>/dev/null || true
codesign --force --sign - "$NODE_ADHOC" >/dev/null 2>&1 || true
ln -sf "$NODE_ADHOC" "$NODE_BIN_DIR/node"

PNPM_DIR="/tmp/codex-pnpm"
PNPM_CJS="$PNPM_DIR/bin/pnpm.cjs"
if [ ! -f "$PNPM_CJS" ]; then
  rm -rf "$PNPM_DIR"
  mkdir -p "$PNPM_DIR"
  TARBALL="$("$NODE_ADHOC" -e "fetch('https://registry.npmjs.org/pnpm/latest').then(r=>r.json()).then(j=>console.log(j.dist.tarball)).catch(e=>{console.error(e); process.exit(1)})")"
  curl -fsSL "$TARBALL" -o "$PNPM_DIR/pnpm.tgz"
  tar -xzf "$PNPM_DIR/pnpm.tgz" -C "$PNPM_DIR" --strip-components=1
fi

if [ ! -d node_modules ]; then
  PATH="$NODE_BIN_DIR:$PATH" "$NODE_ADHOC" "$PNPM_CJS" install || true
  PATH="$NODE_BIN_DIR:$PATH" "$NODE_ADHOC" "$PNPM_CJS" approve-builds --all || true
  PATH="$NODE_BIN_DIR:$PATH" "$NODE_ADHOC" "$PNPM_CJS" install
fi

PATH="$NODE_BIN_DIR:$PATH" exec "$NODE_ADHOC" "$PNPM_CJS" dev -- --port "$PORT"
