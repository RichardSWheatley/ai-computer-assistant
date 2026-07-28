# Twister (the test runner and RITA's gate)

Source: https://docs.zephyrproject.org/latest/develop/twister/index.html
(researched 2026-07-28)

- Invoke as `west twister`. Select suites with `-T <dir>`, platforms with
  `-p <platform>` (repeatable), individual scenarios with `-s <scenario>`.
- Device testing: `--device-testing --hardware-map map.yaml`; generate the
  map from connected boards with `--generate-hardware-map map.yaml`
  (ports/runners are detected — never hardcode them).
- Outputs land in `twister-out/` (override `-O/--outdir`):
  **`twister.json` is the machine-readable verdict** (statuses, reasons,
  timings); `testplan.json` explains filtering; per-test dirs hold
  `build.log` and `handler.log`.
- Harnesses: `ztest` (default for tests), `console` with
  `harness_config: {type: multi_line, regex: [...]}` for output-matching
  samples, `pytest` for stateful interaction (pytest-twister-harness).
- Suite yaml (sample.yaml / testcase.yaml) fields: `platform_allow`,
  `platform_exclude`, `integration_platforms`, `tags`, `timeout`,
  `harness`, `depends_on`, `filter` (expressions over CONFIG_*/dt_* —
  evaluated by twister, not by tools reading the yaml).
