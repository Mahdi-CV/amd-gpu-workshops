# Fixture Provenance

Source repository:

```text
https://github.com/Mahdi-CV/open_type_faster
```

Frozen revision:

```text
b1ca3817ef414c609564b71fc36553feadc0349a
```

Snapshot date: October 25, 2026

The fixture is a workshop-owned frozen copy of the Python application and its
tests. It intentionally retains the seeded accuracy defect in `stats.py` so
participants can exercise the OpenClaw debugging workflow.

The fixture baseline is:

```text
5 failed, 102 passed
```

The expected corrected result is:

```text
107 passed
```

`MANIFEST.sha256` records the immutable file hashes used by reset and
verification tooling.

The upstream repository does not currently include a standalone license file
in this snapshot. Keep the fixture for internal workshop distribution unless
the repository owner explicitly approves broader redistribution.
