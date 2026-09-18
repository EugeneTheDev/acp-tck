"""`acp-tck` console-script entry point: parses TCK options and runs the packaged conformance
suite (`tck.conformance`) via pytest, loading `tck.plugin` explicitly (see `tck/plugin.py`'s
module docstring for why it is not a `pytest11` auto-registered plugin).
"""

from __future__ import annotations

import argparse
import shlex
import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path

import pytest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="acp-tck",
        description="Run the ACP Test Compatibility Kit against an agent launched as a stdio subprocess.",
    )
    parser.add_argument("--agent-cwd", default=None, metavar="DIR", help="Working directory for the agent.")
    parser.add_argument(
        "--agent-env",
        action="append",
        default=[],
        metavar="KEY=VAL",
        help="Environment variable to overlay on the agent's process; repeatable.",
    )
    parser.add_argument("--timeout", type=float, default=30.0, metavar="S", help="Per-response timeout in seconds.")
    parser.add_argument(
        "--startup-timeout", type=float, default=30.0, metavar="S", help="Startup timeout in seconds."
    )
    parser.add_argument(
        "--cancel-prompt",
        default=None,
        metavar="TEXT",
        help="Prompt text for the cancellation tests (ACP-CANCEL-001/002), passed through as "
        "--tck-cancel-prompt. Pick something that keeps the agent under test busy long enough "
        "for session/cancel to land while the turn is still in flight -- otherwise those tests "
        "SKIP with reason 'cancellation not exercised', which means what it says, not that the "
        "agent failed conformance. Default: a long free-form writing prompt.",
    )
    parser.add_argument("-k", dest="expression", default=None, metavar="EXPR", help="pytest -k expression.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose pytest output.")
    parser.add_argument("--version", action="store_true", help="Print the acp-tck version and exit.")
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        metavar="-- <command> [args...]",
        help="The agent command to run, after a `--` separator, e.g. `-- python agent.py`.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        try:
            print(f"acp-tck {_pkg_version('acp-tck')}")
        except PackageNotFoundError:
            print("acp-tck (version unknown; package not installed)")
        return 0

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("no agent command given; pass it after `--`, e.g. `acp-tck -- python agent.py`")

    conformance_dir = Path(__file__).parent / "conformance"

    pytest_args: list[str] = [
        str(conformance_dir),
        "-p",
        "tck.plugin",
        "-p",
        "no:cacheprovider",
        "--rootdir",
        str(conformance_dir),
        "--tck-agent-cmd",
        shlex.join(command),
        "--tck-timeout",
        str(args.timeout),
        "--tck-startup-timeout",
        str(args.startup_timeout),
        # Show skip reasons in the terminal (e.g. "cancellation not exercised") -- a SKIPPED
        # cancel test is a meaningful, distinct outcome from PASS/FAIL, not noise to hide.
        "-rs",
    ]
    if args.agent_cwd is not None:
        pytest_args += ["--tck-agent-cwd", args.agent_cwd]
    for env in args.agent_env:
        pytest_args += ["--tck-agent-env", env]
    if args.cancel_prompt is not None:
        pytest_args += ["--tck-cancel-prompt", args.cancel_prompt]
    if args.expression is not None:
        pytest_args += ["-k", args.expression]
    if args.verbose:
        pytest_args.append("-v")

    return pytest.main(pytest_args)
