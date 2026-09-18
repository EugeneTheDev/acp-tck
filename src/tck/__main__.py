"""`python -m tck` -- same as the `acp-tck` console script. Useful for the self-tests
(`tests/test_cli.py`) to invoke the CLI as a subprocess without depending on the console script
being installed on `PATH`."""

from tck import main

if __name__ == "__main__":
    raise SystemExit(main())
