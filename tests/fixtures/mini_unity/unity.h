/* Minimal Unity-compatible test framework for RITA's offline test suite.
 * Same macros and OUTPUT FORMAT as ThrowTheSwitch/Unity, so HostUnity's
 * parser is exercised exactly as it will be against the real framework
 * (which RITA clones onto the user's machine). */
#ifndef MINI_UNITY_H
#define MINI_UNITY_H

#include <stdio.h>

extern int unity_tests;
extern int unity_failures;
extern const char *unity_current_test;
extern int unity_current_failed;

#define UNITY_BEGIN() (unity_tests = 0, unity_failures = 0, 0)

#define RUN_TEST(fn) do { \
    unity_tests++; unity_current_test = #fn; unity_current_failed = 0; \
    fn(); \
    if (!unity_current_failed) \
        printf("%s:%d:%s:PASS\n", __FILE__, __LINE__, #fn); \
} while (0)

#define UNITY_END() (printf("-----------------------\n%d Tests %d Failures 0 Ignored\n%s\n", \
    unity_tests, unity_failures, unity_failures ? "FAIL" : "OK"), unity_failures)

#define TEST_ASSERT_TRUE_MESSAGE(cond, msg) do { \
    if (!(cond)) { \
        printf("%s:%d:%s:FAIL: %s\n", __FILE__, __LINE__, unity_current_test, msg); \
        unity_failures++; unity_current_failed = 1; \
    } } while (0)

#define TEST_ASSERT_TRUE(cond) TEST_ASSERT_TRUE_MESSAGE(cond, "Expression Evaluated To FALSE")
#define TEST_ASSERT_FALSE(cond) TEST_ASSERT_TRUE_MESSAGE(!(cond), "Expression Evaluated To TRUE")
#define TEST_ASSERT_EQUAL_INT(expected, actual) \
    TEST_ASSERT_TRUE_MESSAGE((expected) == (actual), "Values Not Equal")
#define TEST_ASSERT_NOT_NULL(p) TEST_ASSERT_TRUE_MESSAGE((p) != NULL, "Expected Non-NULL")
#define TEST_ASSERT_NULL(p) TEST_ASSERT_TRUE_MESSAGE((p) == NULL, "Expected NULL")

void setUp(void);
void tearDown(void);

#endif
