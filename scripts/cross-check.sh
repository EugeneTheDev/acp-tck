#!/usr/bin/env bash
# Cross-check the ACP TCK against independently implemented agents:
#   v1 -- `testy` (Rust SDK's own test fixture agent, built from a local checkout) and
#         `examples/echo_agent.py` (Python SDK's example agent, pinned to 1.0.0rc1)
#   v2 -- `testy` again, this time built with the `unstable_protocol_v2` feature so it routes
#         v2 connections to its native v2 agent, and a repo-authored minimal v2 agent
#         (`scripts/cross-check/python_v2_agent.py`, pinned to 1.0.0rc2) since no upstream v2
#         example agent exists yet (see `.agents/research/reference-sdks-v2-status.md`)
#
# This is a manual/CI cross-check, NOT part of `uv run pytest` -- it needs a Rust toolchain
# and both SDK checkouts. See `AGENTS.md` "Cross-checking against upstream agents" and
# `.agents/research/testy-cross-check.md` / `.agents/research/reference-sdks-v2-status.md`.
#
# Set ACP_CROSS_CHECK_V2=0 to skip both v2 legs and run only the v1 comparison (e.g. if the
# local Rust toolchain lacks the v2 feature, or to keep a quick v1-only smoke run).
#
# Exits 0 iff the script itself completed (every enabled agent run happened and its JSON report
# was written). The agents' own conformance verdicts are data, not the script's success -- read
# the printed table(s) and verdict lines.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ACP_RUST_SDK="${ACP_RUST_SDK:-$(cat "$REPO_ROOT/.agents/skills/check-rust-sdk/.repo")}"
ACP_PYTHON_SDK="${ACP_PYTHON_SDK:-$(cat "$REPO_ROOT/.agents/skills/check-python-sdk/.repo")}"
OUT_DIR="${OUT_DIR:-$REPO_ROOT/scratch/cross-check}"
CROSS_CHECK_V2="${ACP_CROSS_CHECK_V2:-1}"

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

TESTY_V2_EXIT=""
PYTHON_V2_EXIT=""
if [ "$CROSS_CHECK_V2" = "1" ]; then
  # Built into an isolated --target-dir, never the checkout's own target/debug/testy: an
  # earlier probe in this effort found that a *dual*-feature build (v1 + unstable_protocol_v2,
  # picking the route per-connection from the client's own `initialize`) does NOT reproduce the
  # v1-only build's ACP-INIT-003 baseline unchanged, contrary to what
  # `.agents/research/reference-sdks-v2-status.md` assumed at the time it was written: since
  # slice V2-0b, the v1 ACP-INIT-003 probe now sends an `info` object alongside the unsupported
  # `protocolVersion: 65535`, which a dual-feature router accepts as valid v2 params and happily
  # routes to (and correctly answers from) its v2 agent -- so the same probe that FAILs against
  # a strict v1-only build actually PASSes against the dual build, for an entirely different
  # reason having nothing to do with the v1 agent's own conformance. Building the v2 leg into
  # its own --target-dir keeps the v1 leg's binary (and its documented baseline) untouched.
  echo "== Building testy (--no-default-features --features unstable_protocol_v2) from $ACP_RUST_SDK ==" >&2
  TESTY_V2_TARGET_DIR="$OUT_DIR/target-v2"
  (
    cd "$ACP_RUST_SDK"
    cargo build -p agent-client-protocol-test --bin testy --no-default-features \
      --features unstable_protocol_v2 --target-dir "$TESTY_V2_TARGET_DIR"
  )

  TESTY_V2="$TESTY_V2_TARGET_DIR/debug/testy"
  if [ ! -x "$TESTY_V2" ]; then
    echo "error: expected testy binary at $TESTY_V2 after build, not found" >&2
    exit 1
  fi

  echo "== Running acp-tck --protocol-version 2 against testy ($TESTY_V2) ==" >&2
  set +e
  uv run acp-tck --protocol-version 2 --cancel-prompt wait_for_cancel \
    --report-json "$OUT_DIR/testy-v2.json" -- "$TESTY_V2"
  TESTY_V2_EXIT=$?
  set -e
  echo "testy (v2) exit code: $TESTY_V2_EXIT" >&2

  echo "== Running acp-tck --protocol-version 2 against python_v2_agent.py (agent-client-protocol==1.0.0rc2) ==" >&2
  set +e
  uv run acp-tck --protocol-version 2 --cancel-prompt wait_for_cancel \
    --report-json "$OUT_DIR/python-v2.json" -- \
    uv run --no-project --with 'agent-client-protocol==1.0.0rc2' python \
      "$SCRIPT_DIR/cross-check/python_v2_agent.py"
  PYTHON_V2_EXIT=$?
  set -e
  echo "python_v2_agent exit code: $PYTHON_V2_EXIT" >&2
else
  echo "== ACP_CROSS_CHECK_V2=0 -- skipping the v2 legs ==" >&2
fi

echo
echo "== Comparison table =="
set +e
if [ "$CROSS_CHECK_V2" = "1" ]; then
  python3 "$SCRIPT_DIR/cross-check-summary.py" \
    "$OUT_DIR/testy.json" testy \
    "$OUT_DIR/echo_agent.json" echo_agent \
    --report "$OUT_DIR/testy-v2.json" testy_v2 \
    --report "$OUT_DIR/python-v2.json" python_v2_agent \
    --expect-only-mandatory-fail ACP-INIT-003 \
    --expect "testy_v2=" \
    --expect "python_v2_agent=ACP-BATCH-201,ACP-BATCH-202,ACP-INIT-003,ACP-INIT-201,ACP-INIT-202"
else
  python3 "$SCRIPT_DIR/cross-check-summary.py" \
    "$OUT_DIR/testy.json" testy \
    "$OUT_DIR/echo_agent.json" echo_agent \
    --expect-only-mandatory-fail ACP-INIT-003
fi
SUMMARY_EXIT=$?
set -e

echo
echo "testy exit code: $TESTY_EXIT"
echo "echo_agent exit code: $ECHO_EXIT"
if [ "$CROSS_CHECK_V2" = "1" ]; then
  echo "testy (v2) exit code: $TESTY_V2_EXIT"
  echo "python_v2_agent exit code: $PYTHON_V2_EXIT"
fi
echo "cross-check-summary.py expectations exit code: $SUMMARY_EXIT"

exit 0
