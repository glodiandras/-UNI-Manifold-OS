"""F9 backup / restore audit (docs/plan/audit/08-f9-mentes-visszaallitas.md): snapshot → change → revert round trips on every
write path, conflict handling (CAS), the static guard against destructive git, and recovery from a damaged index.

Synthetic vaults in temp dirs only (the in-process core frame of `tests.biztonsag`, and the product layout of
`tests.fresh_install` / `tests.migracio`)."""
