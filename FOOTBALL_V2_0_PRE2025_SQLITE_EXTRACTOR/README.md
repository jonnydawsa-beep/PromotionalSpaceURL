# Football V2.0 — Pre-2025 SQLite Extractor

This package creates one compact research database from the yearly Betfair football archives on the Windows host.

## Non-negotiable holdout firewall

The extractor references only these exact files:

- `2015.tar`
- `2016.tar`
- `2017.tar`
- `2018.tar`
- `2019.tar`
- `2020.tar`
- `2021.tar`
- `2022.tar`
- `2023.tar`
- `2024.tar`

It does **not** glob the source directory and does not stat, open, hash or read `2025.tar` or `2026.tar`.

Default source folder:

```text
C:\BetfairMultiSport\Football\raw
```

## Output

The extraction creates:

```text
output\research_pre2025.sqlite3
output\extraction_report.json
output\extraction_report.txt
```

The SQLite contains:

- event, competition and market metadata;
- market start time and source provenance;
- runner identity and settlement status;
- Asian Handicap identity using `(market_id, selection_id, rc[].hc)`;
- nearest causal snapshots at T-20, T-10, T-5 and T-2;
- LTP and available runner/market matched-volume diagnostics;
- status/in-play state;
- ages of the cached runner observation, LTP observation/change and volume observation/change;
- member-level extraction audit and retained QA failures.

The SQLite contains **no 2025–2026 data**.

## Run

1. Extract this package to a normal local folder.
2. Double-click `DOCTOR.bat`.
3. When DOCTOR passes, double-click `RUN_EXTRACT_RESEARCH.bat`.
4. Leave the extraction running. It is resumable by completed year.
5. When it finishes, double-click `VERIFY_OUTPUT.bat`.
6. Double-click `PACK_FOR_UPLOAD.bat` if the SQLite is too large to upload directly.

Upload back:

```text
output\research_pre2025.sqlite3
output\extraction_report.json
```

or, when split packaging was needed:

```text
upload\research_pre2025_sqlite.zip.001
upload\research_pre2025_sqlite.zip.002
...
upload\research_pre2025_sqlite.zip.manifest.json
```

## Important interpretation limits

The database records historical LTP snapshots and available volume diagnostics. It is research/proxy evidence, not proof that a Betfair order would have filled at the historical LTP. Execution stress and prospective fill certification remain separate requirements.

## Python

Python 3.10 or newer is recommended. The extractor uses only Python’s standard library; no `pip install` is required.
