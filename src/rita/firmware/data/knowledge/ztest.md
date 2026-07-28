# ztest (writing tests twister can gate)

Source: https://docs.zephyrproject.org/latest/develop/test/ztest.html
(researched 2026-07-28)

Minimal complete test:

```c
#include <zephyr/ztest.h>

ZTEST_SUITE(my_suite, NULL, NULL, NULL, NULL, NULL);

ZTEST(my_suite, test_something)
{
    zassert_equal(2 + 2, 4, "math broke");
    zassert_true(true, "logic broke");
}
```

`ZTEST_SUITE(name, predicate, setup, before, after, teardown)` — the four
trailing hooks are optional (NULL). Assertions: `zassert_equal`,
`zassert_true/false`, `zassert_is_null/not_null`, `zassert_mem_equal`, …

Required files beside `src/main.c`: `CMakeLists.txt` (normal app shape),
`prj.conf` with `CONFIG_ZTEST=y`, and a **`testcase.yaml`** so twister
discovers and runs it:

```yaml
tests:
  app.my_suite:
    tags: my_feature
    harness: ztest
```

Run: `west twister -T path/to/test -p native_sim`.
