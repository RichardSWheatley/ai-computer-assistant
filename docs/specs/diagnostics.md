# Diagnostics: RITA checks her own setup and says exactly what's wrong

RITA is a GUI-only product: the user cannot run a terminal to find out why
something failed. Every dependency she drives (coding agent, MCP server,
west, SDK, CERBERUS, Unity, voice) must therefore be checkable **from
inside the app**, with the real output shown — not a guess, not a shrug.

## Behavior

- `rita.diagnostics.run_checks(cfg, deep=False) -> list[Check]` where
  `Check(name, ok, detail)`. Pure data, no printing; every detail states
  the concrete finding (path found, exit code, stderr tail).
- Checks: workspace, coder command resolvable, **coder smoke invocation**
  (deep only — runs the agent on a trivial prompt and reports exit code
  plus stdout/stderr tails), MCP config + **whether the server command
  actually starts**, voice imports (a real import, not a spec probe),
  west, Zephyr SDK, CERBERUS, Unity.
- "check setup" / "run diagnostics" / "check your setup" route
  deterministically (grammar, like every other command) to the report;
  the summary line is spoken, the full report lands in the screen pane.
  The Settings page's button submits the same command — one code path.
- **A broken MCP never blocks coding.** `CoderCli` retries once without
  `--mcp-config` when an invocation fails with one configured, and says
  so in the failure/detail text — workspace tools are an enhancement,
  not a prerequisite for authoring code.
- Coder failures quote what the agent actually printed: argv, exit code,
  stdout tail AND stderr tail. Never "exited 1 with output" alone.
- The packaged build bundles what it dynamically imports: the `mcp`
  package (else `rita.exe mcp-serve` cannot run in a frozen install) and
  the voice runtime's binaries.

## Acceptance criteria

- Every check returns a `Check` with a non-empty detail, ok or not.
- An unconfigured coder/workspace is reported as not-ok, naming the fix.
- The coder error text contains argv, exit code, and both output streams.
- A failing MCP-configured invocation is retried without MCP and reports
  the fallback; a clean invocation never retries.
- "check setup" routes to diagnostics (chat kind, not work).
- The PyInstaller spec collects `mcp` and the voice packages.
