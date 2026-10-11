"""Layer 4: model plug-ins (docs/architecture.md §7, decision 0015).

A model is a folder here: manifest.yaml (what it reads, what it writes, its versions), compute.py (one pure function,
compute(inputs, as_of) -> {table: rows}), METHOD.md (the method in plain language) and tests/. Folders starting
with an underscore contain code shared by several models and are not models themselves.

    framework.py   the manifest schema, the input reader and the output writer
    registry.py    finds and validates every manifest, orders models by dependency, publishes them
"""
