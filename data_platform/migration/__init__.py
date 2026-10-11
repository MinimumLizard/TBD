"""One-off loaders that bring the old repos' history into the new platform, each with a reconciliation report.

Principle (docs/architecture.md §14): wherever the old repo kept raw files, the migration does not copy the old
tables. It replays the raw files through the NEW collectors' parsers and then proves the result reproduces the
old tables. Passing that is evidence for both the migration and the new collectors.

Every migration is repeatable: running it twice adds nothing the second time.
"""
