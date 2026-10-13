from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_sqlite(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        markets = con.execute("SELECT COUNT(*) FROM markets").fetchone()[0]
        snapshots = con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
        years = [
            row[0]
            for row in con.execute(
                "SELECT source_year FROM sources WHERE completed=1 ORDER BY source_year"
            ).fetchall()
        ]
    finally:
        con.close()
    if integrity != "ok":
        raise RuntimeError(f"SQLite integrity check failed: {integrity}")
    if years != list(range(2015, 2025)):
        raise RuntimeError(f"completed source years are {years}, expected 2015-2024")
    if markets <= 0 or snapshots <= 0:
        raise RuntimeError(f"empty output: markets={markets}, snapshots={snapshots}")
    return {
        "integrity_check": integrity,
        "completed_years": years,
        "markets": markets,
        "snapshots": snapshots,
    }


def remove_old_parts(upload_dir: Path, prefix: str) -> None:
    for path in upload_dir.glob(f"{prefix}.*"):
        if path.is_file():
            path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="Package extractor output into upload-sized ZIP parts")
    parser.add_argument("--database", default=r"output\research_pre2025.sqlite3")
    parser.add_argument("--report-json", default=r"output\extraction_report.json")
    parser.add_argument("--report-txt", default=r"output\extraction_report.txt")
    parser.add_argument("--upload-dir", default="upload")
    parser.add_argument("--part-mib", type=int, default=400)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    database = (root / args.database).resolve() if not Path(args.database).is_absolute() else Path(args.database)
    report_json = (root / args.report_json).resolve() if not Path(args.report_json).is_absolute() else Path(args.report_json)
    report_txt = (root / args.report_txt).resolve() if not Path(args.report_txt).is_absolute() else Path(args.report_txt)
    upload_dir = (root / args.upload_dir).resolve() if not Path(args.upload_dir).is_absolute() else Path(args.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    verification = verify_sqlite(database)
    print(json.dumps(verification, indent=2))

    prefix = "research_pre2025_sqlite.zip"
    remove_old_parts(upload_dir, prefix)
    zip_path = upload_dir / prefix

    print(f"Creating compressed archive: {zip_path}")
    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
        allowZip64=True,
    ) as zf:
        zf.write(database, arcname=database.name)
        if report_json.is_file():
            zf.write(report_json, arcname=report_json.name)
        if report_txt.is_file():
            zf.write(report_txt, arcname=report_txt.name)

    zip_sha256 = sha256_file(zip_path)
    part_size = args.part_mib * 1024 * 1024
    parts = []

    print(f"Splitting archive into {args.part_mib} MiB parts")
    with zip_path.open("rb") as src:
        index = 1
        while True:
            data = src.read(part_size)
            if not data:
                break
            part_path = upload_dir / f"{prefix}.{index:03d}"
            part_path.write_bytes(data)
            parts.append(
                {
                    "name": part_path.name,
                    "size_bytes": part_path.stat().st_size,
                    "sha256": sha256_file(part_path),
                }
            )
            print(f"  {part_path.name}: {part_path.stat().st_size:,} bytes")
            index += 1

    manifest = {
        "format": "ordered raw split of a standard ZIP64 archive",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "database_name": database.name,
        "database_size_bytes": database.stat().st_size,
        "database_sha256": sha256_file(database),
        "sqlite_verification": verification,
        "zip_name": zip_path.name,
        "zip_size_bytes": zip_path.stat().st_size,
        "zip_sha256": zip_sha256,
        "part_size_bytes": part_size,
        "part_count": len(parts),
        "parts": parts,
        "reconstruction_windows": f"copy /b {prefix}.001+{prefix}.002+... {prefix}",
    }
    manifest_path = upload_dir / f"{prefix}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # The split parts are the upload deliverable; remove the duplicate full ZIP
    # to avoid consuming twice the disk space.
    zip_path.unlink()

    print()
    print("PACKAGING PASS")
    print(f"Manifest: {manifest_path}")
    print(f"Parts: {len(parts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
