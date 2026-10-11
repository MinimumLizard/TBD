"""Data platform: raw archive, database, collectors and (later) models for the TBD market-information portal.

Start with docs/architecture.md. The layers live in:
    core/        shared plumbing: settings, raw store, database, HTTP client, collector runner
    collectors/  one package per data source
    migration/   one-off loaders that move the old repos' history in, with reconciliation
    jobs/        command-line entry points the scheduler calls
"""
