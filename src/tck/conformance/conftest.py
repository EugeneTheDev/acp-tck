"""No fixtures live here: `tck.plugin` supplies all of them (`agent_launch`,
`agent_initialize_result`, the capability gate, and the requirement collector). This suite is
always run with `-p tck.plugin` explicitly -- by the `acp-tck` CLI, or by hand
(`pytest src/tck/conformance -p tck.plugin --tck-agent-cmd ...`) -- rather than via a `pytest11`
auto-registration, so nothing needs to happen in this file for either invocation to work.
"""
