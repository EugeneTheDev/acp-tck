#!/usr/bin/env bash
# Cross-check the ACP TCK against two independently implemented agents:
#   - `testy`, the Rust SDK's own test fixture agent (built from a local checkout)
#   - `examples/echo_agent.py`, the Python SDK's example agent (pinned to 1.0.0rc1)
#
# This is a manual/CI cross-check, NOT part of `uv run pytest` -- it needs a Rust toolchain
# and both SDK checkouts. See `AGENTS.md` "Cross-checking against upstream agents" and
# `.agents/research/testy-cross-check.md`.
#
# Exits 0 iff the script itself completed (both agent runs happened and both JSON reports
# were written). The agents' own conformance verdicts are data, not the script's success --
# read the printed table and verdict lines.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ACP_RUST_SDK="${ACP_RUST_SDK:-$(cat "$REPO_ROOT/.agents/skills/check-rust-sdk/.repo")}"
ACP_PYTHON_SDK="${ACP_PYTHON_SDK:-$(cat "$REPO_ROOT/.agents/skills/check-python-sdk/.repo")}"
OUT_DIR="${OUT_DIR:-$REPO_ROOT/scratch/cross-check}"

mkdir -p "$OUT_DIR"

echo "== Building testy (--no-default-features) from $ACP_RUST_SDK ==" >&2
(
  cd "$ACP_RUST_SDK"
  cargo build -p agent-client-protocol-test --bin testy --no-default-features
)

TESTY="$ACP_RUST_SDK/target/debug/testy"
if [ ! -x "$TESTY" ]; then
  echo "error: expected testy binary at $TESTY after build, not found" >&2
  exit 1
fi

echo "== Running acp-tck against testy ($TESTY) ==" >&2
cd "$REPO_ROOT"
set +e
uv run acp-tck --cancel-prompt wait_for_cancel --report-json "$OUT_DIR/testy.json" -- "$TESTY"
TESTY_EXIT=$?
set -e
echo "testy exit code: $TESTY_EXIT" >&2

echo "== Running acp-tck against echo_agent.py (agent-client-protocol==1.0.0rc1) ==" >&2
set +e
uv run acp-tck --cancel-prompt wait_for_cancel --report-json "$OUT_DIR/echo_agent.json" -- \
  uv run --no-project --with 'agent-client-protocol==1.0.0rc1' python "$ACP_PYTHON_SDK/examples/echo_agent.py"
ECHO_EXIT=$?
set -e
echo "echo_agent exit code: $ECHO_EXIT" >&2

echo
echo "== Comparison table =="
python3 "$SCRIPT_DIR/cross-check-summary.py" \
  "$OUT_DIR/testy.json" testy \
  "$OUT_DIR/echo_agent.json" echo_agent

echo
echo "testy exit code: $TESTY_EXIT"
echo "echo_agent exit code: $ECHO_EXIT"

exit 0
