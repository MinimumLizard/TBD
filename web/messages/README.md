# Site text

Every word on the site lives in these files (`en.json` now; `si.json` and `ta.json` are empty until translated).
No user-facing text is written in code. The copy lint (`python -m data_platform.compliance`) checks all of them for
advice language on every change. Disclaimers are not here: they live in `compliance/disclaimers.yaml`.
