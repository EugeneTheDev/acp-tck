"""The ACP v2 (Draft) conformance suite, shipped inside the `tck` wheel.

Run with `acp-tck --protocol-version 2 -- <agent command>`, or directly with
`pytest src/tck/v2/conformance -p tck.v2.plugin --tck-agent-cmd '<agent command>'`. See
`AGENTS.md` for the option reference and the requirement/test conventions -- v2 is Draft, so
expect this suite's coverage and the vendored schema pin to churn more than v1's.
"""
