These tests verify the `beaker_kernel` -> `beaker_notebook` compatibility shim.

When the package was renamed, `src/beaker_kernel/__init__.py` installed a
meta-path finder that redirects every `beaker_kernel[.X]` import to the matching
`beaker_notebook[.X]` module.

This directory used to hold a full copy of the test suite that imported through
the old `beaker_kernel.*` names, to prove nothing broke in the rename. That copy
was a maintenance burden: every real test change had to be mirrored here.

It has been replaced by `test_shims.py`, which only asserts what the shim is
actually responsible for -- that each old import name resolves to the *same
module object* (and therefore the same file on disk) as its new name. The list
of shimmed modules lives in `SHIMMED_MODULES` in that file; add an entry when
new code starts depending on a `beaker_kernel.*` import.
