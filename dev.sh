#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
workbench_root="$repository_root/apps/workbench"
kura_manifest="$workbench_root/vendor/kura/crates/Cargo.toml"
rebuild_agent=0
rebuild_kura=0
prepare_only=0

usage() {
  cat <<'EOF'
Usage: ./dev.sh [options]

Start the Loopforge Workbench development environment from the repository root.
Missing dependencies and sidecars are prepared automatically. Existing sidecars
are reused so frontend development keeps its fast Vite hot-reload loop.

Options:
  --rebuild-agent      Rebuild the Loopforge Agent sidecar before starting.
  --rebuild-kura       Rebuild the Kura sidecar before starting.
  --rebuild-sidecars   Rebuild both sidecars before starting.
  --prepare-only       Prepare dependencies and sidecars, then exit.
  -h, --help           Show this help message.
EOF
}

fail() {
  printf 'dev.sh: %s\n' "$1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

while (($# > 0)); do
  case "$1" in
    --rebuild-agent)
      rebuild_agent=1
      ;;
    --rebuild-kura)
      rebuild_kura=1
      ;;
    --rebuild-sidecars)
      rebuild_agent=1
      rebuild_kura=1
      ;;
    --prepare-only)
      prepare_only=1
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      fail "unknown option: $1"
      ;;
  esac
  shift
done

require_command pnpm
require_command cargo

if [[ ! -f "$kura_manifest" ]]; then
  require_command git
  printf 'Initializing the pinned Kura submodule...\n'
  git -C "$repository_root" submodule update --init --recursive -- \
    apps/workbench/vendor/kura
fi

[[ -f "$kura_manifest" ]] || fail "Kura submodule initialization did not produce $kura_manifest"

cd "$workbench_root"
printf 'Checking Workbench dependencies...\n'
pnpm install --frozen-lockfile

executable_suffix=""
if [[ "${OS:-}" == "Windows_NT" ]]; then
  executable_suffix=".exe"
fi

kura_binary="$workbench_root/resources/dope-cli$executable_suffix"
agent_binary="$workbench_root/resources/loopforge-agent$executable_suffix"

sidecar_ready() {
  if [[ -n "$executable_suffix" ]]; then
    [[ -f "$1" ]]
  else
    [[ -x "$1" ]]
  fi
}

if ((rebuild_kura == 1)) || ! sidecar_ready "$kura_binary"; then
  printf 'Building the Kura sidecar...\n'
  pnpm build:kura
else
  printf 'Reusing Kura sidecar: %s\n' "$kura_binary"
fi

if ((rebuild_agent == 1)) || ! sidecar_ready "$agent_binary"; then
  require_command uv
  printf 'Building the Loopforge Agent sidecar...\n'
  pnpm build:agent
else
  printf 'Reusing Loopforge Agent sidecar: %s\n' "$agent_binary"
fi

if ((prepare_only == 1)); then
  printf 'Development environment is ready.\n'
  exit 0
fi

printf 'Starting Loopforge Workbench with frontend hot reload...\n'
exec pnpm dev:desktop
