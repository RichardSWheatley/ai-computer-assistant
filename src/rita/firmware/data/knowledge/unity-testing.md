# Unity host unit tests

Source: https://github.com/ThrowTheSwitch/Unity (researched 2026-07-28)

Unit tests are NOT ztest: they run on the host in milliseconds, test one
function in isolation, and stub out hardware/RTOS. RITA uses Unity — the
same framework CERBERUS's Executioner head uses.

Shape of a test file (`tests/unit/test_<module>.c`):

```c
#include "unity.h"
#include "app.h"

void setUp(void) {}      /* optional per-test setup */
void tearDown(void) {}

void test_mspi_read_rejects_null_buffer(void)
{
    TEST_ASSERT_EQUAL_INT(-EINVAL, mspi_read(0, NULL, 16));
}

void test_mspi_read_valid(void)
{
    uint8_t buf[16];
    TEST_ASSERT_EQUAL_INT(0, mspi_read(0, buf, sizeof buf));
}

int main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_mspi_read_rejects_null_buffer);
    RUN_TEST(test_mspi_read_valid);
    return UNITY_END();
}
```

Assertions: `TEST_ASSERT_EQUAL_INT`, `TEST_ASSERT_TRUE/FALSE`,
`TEST_ASSERT_NULL/NOT_NULL`, `TEST_ASSERT_EQUAL_MEMORY`, plus `_MESSAGE`
variants. Output lines are `file:line:test:PASS|FAIL: message` with a
`N Tests M Failures K Ignored` summary — machine-parseable.

Compile on the host: `cc -I<unity/src> -I<src> unity.c test_x.c <sources
except main.c> -o test_x && ./test_x`. The compiler is the host's when one
is on PATH, else the Zephyr SDK's toolchain (the SDK ships gcc by default;
LLVM is the non-default bundle). Name every test `test_<function>_…` so
per-function coverage is checkable mechanically.
