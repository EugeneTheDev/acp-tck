"""No fixtures live here: `tck.v2.plugin` supplies all of them (`agent_launch`,
`agent_initialize_result`, the capability gate, and the requirement collector). This suite is
always run with `-p tck.v2.plugin` explicitly -- by the `acp-tck` CLI (`--protocol-version 2`),
or by hand (`pytest src/tck/v2/conformance -p tck.v2.plugin --tck-agent-cmd ...`) -- rather than
via a `pytest11` auto-registration, so nothing needs to happen in this file for either
invocation to work.
"""
