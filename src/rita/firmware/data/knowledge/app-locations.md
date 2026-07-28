# Where applications live

Source: https://docs.zephyrproject.org/latest/develop/application/index.html
(researched 2026-07-28)

The recommended layout keeps user applications **inside the west workspace,
beside — never inside — the `zephyr/` tree**:

```
zephyrproject/            <- the west workspace (has .west/)
├── zephyr/               <- the Zephyr source tree
├── modules/  bootloader/ <- managed by west
└── applications/         <- YOUR applications go here
    └── my-app/
```

Keeping apps in the workspace makes `west build`, `west flash`, and twister
work with no extra environment setup.

RITA's convention: scaffolded applications are created under the
configured `applications_dir` (default `<workspace>/applications/`), one
directory per application, named from the request. Samples stay where they
are in `zephyr/samples/**`; authored tests carry a `testcase.yaml` so
twister owns their verification.
