# Function parameter contracts (RITA's coding rule)

Sources: MISRA C:2012 Dir 4.14 / CERT C API guidance via
https://wiki.sei.cmu.edu/confluence/display/c (researched 2026-07-28);
rule stated by the project owner.

**Every function must either RESTRICT its input and output parameters, or
VALIDATE them before executing.** No unguarded parameters, ever.

Restrict — make invalid values unrepresentable:
- enums instead of raw ints for modes/states;
- narrow typedefs (`uint8_t channel` not `int`), `size_t` for sizes;
- `const` pointers for read-only inputs;
- bounded output buffers passed WITH their capacity.

Validate — guard clauses first, before any work:

```c
int mspi_read(uint8_t ch, uint8_t *buf, size_t len)
{
    if (ch >= MSPI_CHANNEL_COUNT) return -EINVAL;
    if (buf == NULL)              return -EINVAL;
    if (len == 0 || len > MSPI_MAX_XFER) return -EINVAL;
    /* ...only now do the work... */
}
```

Outputs are part of the contract too: clamp or reject out-of-range results
(`-EINVAL`/`-ERANGE` returns, never silent wraparound), and document the
valid output range beside the prototype.

Unit tests exercise exactly this contract per function: valid inputs →
expected outputs; boundary values (0, max, max+1); invalid inputs →
rejected with the documented error. A function without such tests is an
incomplete function.
