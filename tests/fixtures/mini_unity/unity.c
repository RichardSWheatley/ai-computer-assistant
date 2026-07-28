#include "unity.h"

int unity_tests = 0;
int unity_failures = 0;
const char *unity_current_test = "";
int unity_current_failed = 0;

__attribute__((weak)) void setUp(void) {}
__attribute__((weak)) void tearDown(void) {}
