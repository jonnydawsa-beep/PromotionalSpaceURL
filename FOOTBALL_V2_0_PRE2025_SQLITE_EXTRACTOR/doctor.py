from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

RESEARCH_YEARS = tuple(range(2015, 2025))
MIN_PYTHON = (3, 10)


def gb(value: int) -> float:
    return value / (1024 ** 3)


def main() -> int:
    parser = argparse.ArgumentParser(description="Football V2.0 extractor preflight")
    parser.add_argument("--raw-dir", default=r"C:\BetfairMultiSport\Football\raw")
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    package_dir = Path(__file__).resolve().parent
    failures: list[str] = []

    print("=" * 72)
    print("FOOTBALL V2.0 PRE-2025 SQLITE EXTRACTOR — DOCTOR")
    print("=" * 72)
    print(f"Python: {sys.version}")
    print(f"SQLite: {sqlite3.sqlite_version}")
    print(f"Package: {package_dir}")
    print(f"Research source: {raw_dir}")
    print("Holdout firewall: 2025.tar and 2026.tar are not inspected")
    print()

    if sys.version_info < MIN_PYTHON:
        failures.append(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required; found "
            f"{sys.version_info.major}.{sys.version_info.minor}"
        )

    total_bytes = 0
    source_rows = []
    for year in RESEARCH_YEARS:
        path = raw_dir / f"{year}.tar"
        if not path.is_file():
            failures.append(f"missing required source: {path}")
            source_rows.append({"year": year, "path": str(path), "exists": False})
            continue
        size = path.stat().st_size
        total_bytes += size
        source_rows.append(
            {"year": year, "path": str(path), "exists": True, "size_bytes": size}
        )
        print(f"PASS source {year}: {path.name} — {gb(size):.3f} GiB")

    output_dir = package_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    disk = shutil.disk_usage(output_dir)
    # The compact SQLite should normally be much smaller than the TAR inputs,
    # but retain a conservative floor and a proportional allowance.
    recommended_free = max(15 * 1024 ** 3, int(total_bytes * 0.65))
    print()
    print(f"Research TAR total: {gb(total_bytes):.3f} GiB")
    print(f"Free space at output location: {gb(disk.free):.3f} GiB")
    print(f"Recommended minimum free: {gb(recommended_free):.3f} GiB")
    if disk.free < recommended_free:
        failures.append(
            f"insufficient free disk at {output_dir}: "
            f"{gb(disk.free):.2f} GiB free; recommend {gb(recommended_free):.2f} GiB"
        )

    print()
    print("Running synthetic parser/database self-test...")
    result = subprocess.run(
        [sys.executable, str(package_dir / "extract_research.py"), "--self-test"],
        cwd=package_dir,
        text=True,
        capture_output=True,
    )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip())
    if result.returncode != 0:
        failures.append(f"synthetic self-test failed with exit code {result.returncode}")

    report = {
        "status": "FAIL" if failures else "PASS",
        "python": sys.version,
        "sqlite": sqlite3.sqlite_version,
        "raw_dir": str(raw_dir),
        "research_sources": source_rows,
        "holdout_firewall": "2025-2026 NOT INSPECTED",
        "total_source_bytes": total_bytes,
        "output_free_bytes": disk.free,
        "recommended_free_bytes": recommended_free,
        "self_test_exit_code": result.returncode,
        "failures": failures,
    }
    (package_dir / "doctor_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    print()
    if failures:
        print("DOCTOR FAIL")
        for failure in failures:
            print(f" - {failure}")
        return 2

    print("DOCTOR PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
