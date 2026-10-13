from __future__ import annotations

import argparse
import bz2
import gzip
import hashlib
import io
import json
import sqlite3
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = "football-v2-pre2025-sqlite-v1.0.0"
RESEARCH_YEARS = tuple(range(2015, 2025))
TARGETS = {"T20": 1200, "T10": 600, "T5": 300, "T2": 120}
RESEARCH_START_MS = int(datetime(2015, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
RESEARCH_END_MS = int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)

SCHEMA_SQL = r"""
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS metadata(
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources(
    source_year INTEGER PRIMARY KEY,
    tar_name TEXT NOT NULL,
    tar_path TEXT NOT NULL,
    tar_size_bytes INTEGER NOT NULL,
    tar_mtime_ns INTEGER NOT NULL,
    members_seen INTEGER NOT NULL DEFAULT 0,
    members_ok INTEGER NOT NULL DEFAULT 0,
    members_failed INTEGER NOT NULL DEFAULT 0,
    markets_written INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    started_utc TEXT,
    completed_utc TEXT
);

CREATE TABLE IF NOT EXISTS members(
    source_year INTEGER NOT NULL,
    member_name TEXT NOT NULL,
    member_size_bytes INTEGER NOT NULL,
    member_index INTEGER NOT NULL,
    status TEXT NOT NULL,
    records_seen INTEGER NOT NULL DEFAULT 0,
    markets_found INTEGER NOT NULL DEFAULT 0,
    markets_written INTEGER NOT NULL DEFAULT 0,
    decompressed_size_bytes INTEGER,
    error TEXT,
    PRIMARY KEY(source_year, member_name),
    FOREIGN KEY(source_year) REFERENCES sources(source_year) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS markets(
    market_id TEXT PRIMARY KEY,
    source_year INTEGER NOT NULL,
    event_type_id TEXT,
    event_id TEXT,
    event_name TEXT,
    competition_id TEXT,
    competition_name TEXT,
    country_code TEXT,
    market_name TEXT,
    market_type TEXT,
    betting_type TEXT,
    market_base_rate REAL,
    number_of_winners INTEGER,
    turn_in_play_enabled INTEGER,
    market_start_ms INTEGER NOT NULL,
    market_start_iso TEXT NOT NULL,
    market_start_year INTEGER NOT NULL,
    market_start_month INTEGER NOT NULL,
    final_market_status TEXT,
    final_inplay INTEGER,
    final_publish_time_ms INTEGER,
    final_publish_time_iso TEXT,
    source_tar TEXT NOT NULL,
    source_member TEXT NOT NULL,
    FOREIGN KEY(source_year) REFERENCES sources(source_year) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS runners(
    market_id TEXT NOT NULL,
    selection_id INTEGER NOT NULL,
    handicap REAL NOT NULL DEFAULT 0,
    handicap_source TEXT NOT NULL,
    runner_name TEXT,
    sort_priority INTEGER,
    adjustment_factor REAL,
    final_status TEXT,
    winner INTEGER,
    voided INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(market_id, selection_id, handicap),
    FOREIGN KEY(market_id) REFERENCES markets(market_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS snapshots(
    market_id TEXT NOT NULL,
    selection_id INTEGER NOT NULL,
    handicap REAL NOT NULL DEFAULT 0,
    snap_label TEXT NOT NULL,
    target_seconds_preoff INTEGER NOT NULL,
    frame_publish_time_ms INTEGER NOT NULL,
    frame_publish_time_iso TEXT NOT NULL,
    seconds_preoff REAL NOT NULL,
    distance_from_target_seconds REAL NOT NULL,
    ltp REAL NOT NULL,
    runner_total_matched REAL,
    market_total_matched REAL,
    market_status TEXT,
    inplay INTEGER,
    runner_rc_age_seconds REAL,
    ltp_observed_age_seconds REAL,
    ltp_change_age_seconds REAL,
    tv_observed_age_seconds REAL,
    tv_change_age_seconds REAL,
    market_tv_age_seconds REAL,
    PRIMARY KEY(market_id, selection_id, handicap, snap_label),
    FOREIGN KEY(market_id) REFERENCES markets(market_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS qa_issues(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_year INTEGER,
    source_member TEXT,
    market_id TEXT,
    severity TEXT NOT NULL,
    code TEXT NOT NULL,
    detail TEXT,
    created_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_markets_source_year ON markets(source_year);
CREATE INDEX IF NOT EXISTS idx_markets_start_year ON markets(market_start_year);
CREATE INDEX IF NOT EXISTS idx_markets_type ON markets(market_type);
CREATE INDEX IF NOT EXISTS idx_markets_event ON markets(event_id);
CREATE INDEX IF NOT EXISTS idx_runners_market ON runners(market_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_label ON snapshots(snap_label);
CREATE INDEX IF NOT EXISTS idx_snapshots_market ON snapshots(market_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_runner ON snapshots(selection_id, handicap);
CREATE INDEX IF NOT EXISTS idx_qa_code ON qa_issues(code);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso_from_ms(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc).isoformat()


def parse_time_ms(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            return int(value)
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000)
    except (TypeError, ValueError, OverflowError):
        return None


def to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def to_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def normalise_handicap(value: Any) -> float:
    parsed = to_float(value)
    if parsed is None or parsed == 0:
        return 0.0
    return parsed


def age_seconds(frame_ms: int, observed_ms: int | None) -> float | None:
    if observed_ms is None:
        return None
    return max(0.0, (frame_ms - observed_ms) / 1000.0)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def protocol_hash() -> str:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "research_years": list(RESEARCH_YEARS),
        "targets": TARGETS,
        "holdout": "2025-2026 NEVER ACCESSED",
        "snapshot_rule": "nearest observation at or before each target; never closer to kickoff",
        "asian_handicap_identity": ["market_id", "selection_id", "rc[].hc"],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def connect_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA temp_store=MEMORY")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA_SQL)
    return con


def write_metadata(con: sqlite3.Connection, key: str, value: Any) -> None:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    con.execute(
        "INSERT OR REPLACE INTO metadata(key,value) VALUES(?,?)",
        (key, text),
    )


def add_issue(
    con: sqlite3.Connection,
    source_year: int | None,
    source_member: str | None,
    market_id: str | None,
    severity: str,
    code: str,
    detail: str,
) -> None:
    con.execute(
        """
        INSERT INTO qa_issues(
            source_year,source_member,market_id,severity,code,detail,created_utc
        ) VALUES(?,?,?,?,?,?,?)
        """,
        (source_year, source_member, market_id, severity, code, detail[:4000], utc_now()),
    )


def decode_member(raw: bytes, member_name: str) -> tuple[list[dict[str, Any]], int]:
    lower = member_name.lower()
    try:
        if lower.endswith(".bz2") or raw.startswith(b"BZh"):
            decoded = bz2.decompress(raw)
        elif lower.endswith(".gz") or raw.startswith(b"\x1f\x8b"):
            decoded = gzip.decompress(raw)
        else:
            decoded = raw
    except Exception as exc:
        raise ValueError(f"decompression failed: {type(exc).__name__}: {exc}") from exc

    if not decoded.strip():
        raise ValueError("empty decompressed member")

    records: list[dict[str, Any]] = []
    lines = decoded.splitlines()
    for line_number, raw_line in enumerate(lines, 1):
        if not raw_line.strip():
            continue
        try:
            obj = json.loads(raw_line)
        except Exception as exc:
            raise ValueError(
                f"JSON decode failed at line {line_number}: {type(exc).__name__}: {exc}"
            ) from exc
        if isinstance(obj, dict):
            records.append(obj)
        elif isinstance(obj, list):
            records.extend(item for item in obj if isinstance(item, dict))

    if not records:
        raise ValueError("member contains no JSON objects")
    return records, len(decoded)


def new_market_state() -> dict[str, Any]:
    return {
        "event_type_id": None,
        "event_id": None,
        "event_name": None,
        "competition_id": None,
        "competition_name": None,
        "country_code": None,
        "market_name": None,
        "market_type": None,
        "betting_type": None,
        "market_base_rate": None,
        "number_of_winners": None,
        "turn_in_play_enabled": None,
        "market_start_ms": None,
        "market_status": None,
        "inplay": None,
        "final_publish_time_ms": None,
        "market_total_matched": None,
        "market_tv_observed_ms": None,
        "runner_meta": {},
        "runner_state": {},
        "snapshots": {},
    }


def unique_meta_handicap(st: dict[str, Any], selection_id: int) -> float | None:
    values = {hc for sid, hc in st["runner_meta"].keys() if sid == selection_id}
    if len(values) == 1:
        return next(iter(values))
    return None


def ensure_runner_state(
    st: dict[str, Any], selection_id: int, handicap: float, handicap_source: str
) -> dict[str, Any]:
    key = (selection_id, handicap)
    rs = st["runner_state"].setdefault(
        key,
        {
            "handicap_source": handicap_source,
            "ltp": None,
            "ltp_observed_ms": None,
            "ltp_change_ms": None,
            "tv": None,
            "tv_observed_ms": None,
            "tv_change_ms": None,
            "rc_observed_ms": None,
        },
    )
    if rs["handicap_source"] != "RC_HC" and handicap_source == "RC_HC":
        rs["handicap_source"] = "RC_HC"
    return rs


def update_market_definition(st: dict[str, Any], md: dict[str, Any]) -> None:
    mappings = {
        "event_type_id": "eventTypeId",
        "event_id": "eventId",
        "event_name": "eventName",
        "competition_id": "competitionId",
        "competition_name": "competition",
        "country_code": "countryCode",
        "market_name": "name",
        "market_type": "marketType",
        "betting_type": "bettingType",
        "market_base_rate": "marketBaseRate",
        "number_of_winners": "numberOfWinners",
        "turn_in_play_enabled": "turnInPlayEnabled",
    }
    for dest, source in mappings.items():
        if source in md and md[source] is not None:
            st[dest] = md[source]

    market_start = parse_time_ms(md.get("marketTime"))
    if market_start is None:
        market_start = parse_time_ms(md.get("openDate"))
    if market_start is not None:
        st["market_start_ms"] = market_start

    if "status" in md:
        st["market_status"] = md.get("status")
    if "inPlay" in md:
        st["inplay"] = bool(md.get("inPlay"))

    for rd in md.get("runners") or []:
        if not isinstance(rd, dict):
            continue
        sid = to_int(rd.get("id"))
        if sid is None:
            continue
        hc = normalise_handicap(rd.get("hc"))
        key = (sid, hc)
        meta = st["runner_meta"].setdefault(key, {})
        if rd.get("name") is not None:
            meta["name"] = rd.get("name")
        if rd.get("status") is not None:
            meta["status"] = rd.get("status")
        if rd.get("sortPriority") is not None:
            meta["sort_priority"] = to_int(rd.get("sortPriority"))
        if rd.get("adjustmentFactor") is not None:
            meta["adjustment_factor"] = to_float(rd.get("adjustmentFactor"))
        ensure_runner_state(st, sid, hc, "MD_HC")


def choose_snapshot(current: dict[str, Any] | None, candidate: dict[str, Any]) -> dict[str, Any]:
    if current is None or candidate["distance"] < current["distance"]:
        return candidate
    return current


def build_market_states(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}

    for record in records:
        pt = to_int(record.get("pt"))
        changes = record.get("mc")
        if pt is None or not isinstance(changes, list):
            continue

        for mc in changes:
            if not isinstance(mc, dict):
                continue
            market_id = str(mc.get("id") or "")
            if not market_id:
                continue

            st = states.setdefault(market_id, new_market_state())
            st["final_publish_time_ms"] = pt

            md = mc.get("marketDefinition")
            if isinstance(md, dict):
                update_market_definition(st, md)

            if "tv" in mc:
                market_tv = to_float(mc.get("tv"))
                if market_tv is not None:
                    st["market_total_matched"] = market_tv
                    st["market_tv_observed_ms"] = pt

            for rc in mc.get("rc") or []:
                if not isinstance(rc, dict):
                    continue
                sid = to_int(rc.get("id"))
                if sid is None:
                    continue

                if "hc" in rc:
                    hc = normalise_handicap(rc.get("hc"))
                    hc_source = "RC_HC"
                else:
                    md_hc = unique_meta_handicap(st, sid)
                    if md_hc is not None:
                        hc = md_hc
                        hc_source = "MD_UNIQUE_HC"
                    else:
                        hc = 0.0
                        hc_source = "DEFAULT_ZERO"

                rs = ensure_runner_state(st, sid, hc, hc_source)
                rs["rc_observed_ms"] = pt

                if "ltp" in rc:
                    new_ltp = to_float(rc.get("ltp"))
                    if new_ltp is not None:
                        if rs["ltp"] is None or new_ltp != rs["ltp"]:
                            rs["ltp_change_ms"] = pt
                        rs["ltp"] = new_ltp
                        rs["ltp_observed_ms"] = pt

                if "tv" in rc:
                    new_tv = to_float(rc.get("tv"))
                    if new_tv is not None:
                        if rs["tv"] is None or new_tv != rs["tv"]:
                            rs["tv_change_ms"] = pt
                        rs["tv"] = new_tv
                        rs["tv_observed_ms"] = pt

            start_ms = st["market_start_ms"]
            if start_ms is None:
                continue
            seconds_preoff = (start_ms - pt) / 1000.0
            if seconds_preoff < 0:
                continue

            # Snapshot every runner's current state after applying this frame.
            # This preserves a cached LTP while recording its true age.
            for (sid, hc), rs in st["runner_state"].items():
                if rs["ltp"] is None:
                    continue
                for label, target_seconds in TARGETS.items():
                    # Causal rule: never use a frame closer to kickoff than target.
                    if seconds_preoff < target_seconds:
                        continue
                    distance = seconds_preoff - target_seconds
                    candidate = {
                        "distance": distance,
                        "frame_publish_time_ms": pt,
                        "seconds_preoff": seconds_preoff,
                        "ltp": rs["ltp"],
                        "runner_total_matched": rs["tv"],
                        "market_total_matched": st["market_total_matched"],
                        "market_status": st["market_status"],
                        "inplay": 1 if st["inplay"] else 0,
                        "runner_rc_age_seconds": age_seconds(pt, rs["rc_observed_ms"]),
                        "ltp_observed_age_seconds": age_seconds(pt, rs["ltp_observed_ms"]),
                        "ltp_change_age_seconds": age_seconds(pt, rs["ltp_change_ms"]),
                        "tv_observed_age_seconds": age_seconds(pt, rs["tv_observed_ms"]),
                        "tv_change_age_seconds": age_seconds(pt, rs["tv_change_ms"]),
                        "market_tv_age_seconds": age_seconds(pt, st["market_tv_observed_ms"]),
                    }
                    snap_key = (sid, hc, label)
                    st["snapshots"][snap_key] = choose_snapshot(
                        st["snapshots"].get(snap_key), candidate
                    )

    return states


def metadata_for_runner(st: dict[str, Any], sid: int, hc: float) -> dict[str, Any]:
    exact = st["runner_meta"].get((sid, hc))
    if exact:
        return exact
    candidates = [meta for (msid, _mhc), meta in st["runner_meta"].items() if msid == sid]
    if len(candidates) == 1:
        return candidates[0]
    return {}


def persist_market_states(
    con: sqlite3.Connection,
    source_year: int,
    source_tar: str,
    source_member: str,
    states: dict[str, dict[str, Any]],
) -> tuple[int, int]:
    written = 0
    skipped = 0

    for market_id, st in states.items():
        event_type = str(st["event_type_id"]) if st["event_type_id"] is not None else None
        if event_type is not None and event_type != "1":
            add_issue(
                con, source_year, source_member, market_id, "INFO",
                "NON_FOOTBALL_MARKET_SKIPPED", f"eventTypeId={event_type}"
            )
            skipped += 1
            continue

        start_ms = st["market_start_ms"]
        if start_ms is None:
            add_issue(
                con, source_year, source_member, market_id, "ERROR",
                "MISSING_MARKET_START", "No marketTime/openDate could be parsed"
            )
            skipped += 1
            continue

        if not (RESEARCH_START_MS <= start_ms < RESEARCH_END_MS):
            add_issue(
                con, source_year, source_member, market_id, "INFO",
                "OUTSIDE_RESEARCH_DATE_SKIPPED", f"market_start={iso_from_ms(start_ms)}"
            )
            skipped += 1
            continue

        existing = con.execute(
            "SELECT source_member FROM markets WHERE market_id=?", (market_id,)
        ).fetchone()
        if existing is not None:
            add_issue(
                con, source_year, source_member, market_id, "ERROR",
                "DUPLICATE_MARKET_ID",
                f"already stored from member={existing[0]}; duplicate not overwritten",
            )
            skipped += 1
            continue

        start_dt = datetime.fromtimestamp(start_ms / 1000.0, tz=timezone.utc)
        con.execute(
            """
            INSERT INTO markets(
                market_id,source_year,event_type_id,event_id,event_name,
                competition_id,competition_name,country_code,market_name,market_type,
                betting_type,market_base_rate,number_of_winners,turn_in_play_enabled,
                market_start_ms,market_start_iso,market_start_year,market_start_month,
                final_market_status,final_inplay,final_publish_time_ms,final_publish_time_iso,
                source_tar,source_member
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                market_id, source_year, event_type, st["event_id"], st["event_name"],
                str(st["competition_id"]) if st["competition_id"] is not None else None,
                st["competition_name"], st["country_code"], st["market_name"],
                st["market_type"], st["betting_type"], to_float(st["market_base_rate"]),
                to_int(st["number_of_winners"]),
                1 if st["turn_in_play_enabled"] else 0 if st["turn_in_play_enabled"] is not None else None,
                start_ms, iso_from_ms(start_ms), start_dt.year, start_dt.month,
                st["market_status"], 1 if st["inplay"] else 0 if st["inplay"] is not None else None,
                st["final_publish_time_ms"], iso_from_ms(st["final_publish_time_ms"]),
                source_tar, source_member,
            ),
        )

        keys = set(st["runner_meta"].keys()) | set(st["runner_state"].keys())
        keys |= {(sid, hc) for sid, hc, _label in st["snapshots"].keys()}

        for sid, hc in sorted(keys):
            meta = metadata_for_runner(st, sid, hc)
            rs = st["runner_state"].get((sid, hc), {})
            final_status = meta.get("status")
            winner = 1 if final_status == "WINNER" else 0 if final_status == "LOSER" else None
            voided = 1 if final_status == "REMOVED" else 0
            con.execute(
                """
                INSERT INTO runners(
                    market_id,selection_id,handicap,handicap_source,runner_name,
                    sort_priority,adjustment_factor,final_status,winner,voided
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    market_id, sid, hc, rs.get("handicap_source", "MD_HC"),
                    meta.get("name"), to_int(meta.get("sort_priority")),
                    to_float(meta.get("adjustment_factor")), final_status, winner, voided,
                ),
            )

        for (sid, hc, label), snap in st["snapshots"].items():
            frame_ms = snap["frame_publish_time_ms"]
            con.execute(
                """
                INSERT INTO snapshots(
                    market_id,selection_id,handicap,snap_label,target_seconds_preoff,
                    frame_publish_time_ms,frame_publish_time_iso,seconds_preoff,
                    distance_from_target_seconds,ltp,runner_total_matched,
                    market_total_matched,market_status,inplay,runner_rc_age_seconds,
                    ltp_observed_age_seconds,ltp_change_age_seconds,tv_observed_age_seconds,
                    tv_change_age_seconds,market_tv_age_seconds
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    market_id, sid, hc, label, TARGETS[label], frame_ms,
                    iso_from_ms(frame_ms), snap["seconds_preoff"], snap["distance"],
                    snap["ltp"], snap["runner_total_matched"],
                    snap["market_total_matched"], snap["market_status"], snap["inplay"],
                    snap["runner_rc_age_seconds"], snap["ltp_observed_age_seconds"],
                    snap["ltp_change_age_seconds"], snap["tv_observed_age_seconds"],
                    snap["tv_change_age_seconds"], snap["market_tv_age_seconds"],
                ),
            )

        written += 1

    return written, skipped


def purge_incomplete_year(con: sqlite3.Connection, source_year: int) -> None:
    with con:
        con.execute("DELETE FROM markets WHERE source_year=?", (source_year,))
        con.execute("DELETE FROM qa_issues WHERE source_year=?", (source_year,))
        con.execute("DELETE FROM sources WHERE source_year=?", (source_year,))


def process_year(con: sqlite3.Connection, source_year: int, tar_path: Path) -> None:
    stat = tar_path.stat()
    existing = con.execute(
        "SELECT tar_size_bytes,tar_mtime_ns,completed FROM sources WHERE source_year=?",
        (source_year,),
    ).fetchone()

    if existing and existing[2] == 1:
        if existing[0] != stat.st_size or existing[1] != stat.st_mtime_ns:
            raise RuntimeError(
                f"{source_year}.tar changed after a completed extraction. "
                "Delete the SQLite and restart rather than mixing source versions."
            )
        print(f"[{source_year}] already complete and source unchanged - skipping", flush=True)
        return

    if existing:
        print(f"[{source_year}] incomplete prior run found - purging and restarting year", flush=True)
        purge_incomplete_year(con, source_year)

    with con:
        con.execute(
            """
            INSERT INTO sources(
                source_year,tar_name,tar_path,tar_size_bytes,tar_mtime_ns,
                started_utc,completed
            ) VALUES(?,?,?,?,?,?,0)
            """,
            (
                source_year, tar_path.name, str(tar_path), stat.st_size,
                stat.st_mtime_ns, utc_now(),
            ),
        )

    print(f"[{source_year}] OPEN {tar_path} ({stat.st_size:,} bytes)", flush=True)
    member_index = 0
    markets_written_total = 0

    try:
        with tarfile.open(tar_path, "r:*") as tf:
            for member in tf:
                if not member.isfile():
                    continue
                member_index += 1
                try:
                    extracted = tf.extractfile(member)
                    if extracted is None:
                        raise ValueError("tar member could not be opened")
                    raw = extracted.read()
                    records, decoded_size = decode_member(raw, member.name)
                    states = build_market_states(records)
                    with con:
                        written, _skipped = persist_market_states(
                            con, source_year, tar_path.name, member.name, states
                        )
                        con.execute(
                            """
                            INSERT INTO members(
                                source_year,member_name,member_size_bytes,member_index,
                                status,records_seen,markets_found,markets_written,
                                decompressed_size_bytes,error
                            ) VALUES(?,?,?,?,?,?,?,?,?,NULL)
                            """,
                            (
                                source_year, member.name, member.size, member_index,
                                "OK", len(records), len(states), written, decoded_size,
                            ),
                        )
                        con.execute(
                            """
                            UPDATE sources SET
                                members_seen=members_seen+1,
                                members_ok=members_ok+1,
                                markets_written=markets_written+?
                            WHERE source_year=?
                            """,
                            (written, source_year),
                        )
                    markets_written_total += written
                except Exception as exc:
                    detail = f"{type(exc).__name__}: {exc}"
                    with con:
                        con.execute(
                            """
                            INSERT OR REPLACE INTO members(
                                source_year,member_name,member_size_bytes,member_index,
                                status,records_seen,markets_found,markets_written,
                                decompressed_size_bytes,error
                            ) VALUES(?,?,?,?,?,0,0,0,NULL,?)
                            """,
                            (
                                source_year, member.name, member.size, member_index,
                                "FAILED", detail[:4000],
                            ),
                        )
                        con.execute(
                            """
                            UPDATE sources SET
                                members_seen=members_seen+1,
                                members_failed=members_failed+1
                            WHERE source_year=?
                            """,
                            (source_year,),
                        )
                        add_issue(
                            con, source_year, member.name, None, "ERROR",
                            "MEMBER_PARSE_FAILED", detail,
                        )

                if member_index % 250 == 0:
                    print(
                        f"[{source_year}] members={member_index:,} "
                        f"markets_written={markets_written_total:,}",
                        flush=True,
                    )
    except Exception:
        con.commit()
        raise

    with con:
        con.execute(
            """
            UPDATE sources SET completed=1,completed_utc=?
            WHERE source_year=?
            """,
            (utc_now(), source_year),
        )

    print(
        f"[{source_year}] COMPLETE members={member_index:,} "
        f"markets_written={markets_written_total:,}",
        flush=True,
    )


def query_pairs(con: sqlite3.Connection, sql: str) -> dict[str, int]:
    return {str(key): int(value) for key, value in con.execute(sql).fetchall()}


def build_report(con: sqlite3.Connection, output_db: Path, elapsed_seconds: float) -> dict[str, Any]:
    integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
    counts = {
        table: int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in ("sources", "members", "markets", "runners", "snapshots", "qa_issues")
    }

    markets_by_source_year = query_pairs(
        con,
        "SELECT source_year,COUNT(*) FROM markets GROUP BY source_year ORDER BY source_year",
    )
    markets_by_start_year = query_pairs(
        con,
        "SELECT market_start_year,COUNT(*) FROM markets GROUP BY market_start_year ORDER BY market_start_year",
    )
    snapshots_by_label = query_pairs(
        con,
        "SELECT snap_label,COUNT(*) FROM snapshots GROUP BY snap_label ORDER BY snap_label",
    )
    qa_by_code = query_pairs(
        con,
        "SELECT code,COUNT(*) FROM qa_issues GROUP BY code ORDER BY COUNT(*) DESC,code",
    )
    market_types = query_pairs(
        con,
        "SELECT COALESCE(market_type,'<NULL>'),COUNT(*) FROM markets GROUP BY market_type ORDER BY COUNT(*) DESC",
    )

    source_rows = [
        {
            "source_year": row[0],
            "tar_name": row[1],
            "tar_size_bytes": row[2],
            "members_seen": row[3],
            "members_ok": row[4],
            "members_failed": row[5],
            "markets_written": row[6],
            "completed": bool(row[7]),
        }
        for row in con.execute(
            """
            SELECT source_year,tar_name,tar_size_bytes,members_seen,members_ok,
                   members_failed,markets_written,completed
            FROM sources ORDER BY source_year
            """
        ).fetchall()
    ]

    runner_count = counts["runners"]
    settled_count = int(
        con.execute("SELECT COUNT(*) FROM runners WHERE winner IS NOT NULL OR voided=1").fetchone()[0]
    )
    settlement_coverage = settled_count / runner_count if runner_count else 0.0

    classification = "PASS"
    reasons: list[str] = []

    if integrity != "ok":
        classification = "FAIL"
        reasons.append(f"SQLite integrity_check={integrity}")

    completed_years = {row["source_year"] for row in source_rows if row["completed"]}
    missing_completed = sorted(set(RESEARCH_YEARS) - completed_years)
    if missing_completed:
        classification = "FAIL"
        reasons.append(f"incomplete source years: {missing_completed}")

    zero_market_years = [year for year in RESEARCH_YEARS if int(markets_by_source_year.get(str(year), 0)) == 0]
    if zero_market_years:
        classification = "FAIL"
        reasons.append(f"zero reconstructed markets in source years: {zero_market_years}")

    duplicate_count = int(qa_by_code.get("DUPLICATE_MARKET_ID", 0))
    if duplicate_count:
        classification = "FAIL"
        reasons.append(f"duplicate market IDs: {duplicate_count}")

    member_failures = sum(row["members_failed"] for row in source_rows)
    if classification != "FAIL" and member_failures:
        classification = "WARNING"
        reasons.append(f"member parse failures retained in QA: {member_failures}")

    report = {
        "schema_version": SCHEMA_VERSION,
        "protocol_hash": protocol_hash(),
        "extractor_sha256": sha256_file(Path(__file__).resolve()),
        "classification": classification,
        "usable_for_mining": classification != "FAIL",
        "reasons": reasons,
        "research_years": "2015-2024",
        "holdout_firewall": "2025.tar and 2026.tar were never statted, opened, hashed or read",
        "snapshot_rule": "nearest causal frame at or before T20/T10/T5/T2",
        "asian_handicap_identity": "(market_id, selection_id, rc[].hc)",
        "database_path": str(output_db.resolve()),
        "database_size_bytes": output_db.stat().st_size if output_db.exists() else None,
        "integrity_check": integrity,
        "counts": counts,
        "sources": source_rows,
        "markets_by_source_year": markets_by_source_year,
        "markets_by_start_year": markets_by_start_year,
        "snapshots_by_label": snapshots_by_label,
        "market_types": market_types,
        "qa_by_code": qa_by_code,
        "settled_runner_count": settled_count,
        "settlement_coverage": settlement_coverage,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "created_utc": utc_now(),
    }
    return report


def write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "extraction_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    lines = [
        "FOOTBALL V2.0 PRE-2025 EXTRACTION REPORT",
        "=" * 52,
        f"classification: {report['classification']}",
        f"usable_for_mining: {report['usable_for_mining']}",
        f"research_years: {report['research_years']}",
        f"holdout_firewall: {report['holdout_firewall']}",
        f"database_size_bytes: {report['database_size_bytes']}",
        f"integrity_check: {report['integrity_check']}",
        f"settlement_coverage: {report['settlement_coverage']:.6f}",
        f"elapsed_seconds: {report['elapsed_seconds']}",
        "",
        "counts:",
    ]
    lines.extend(f"  {key}: {value}" for key, value in report["counts"].items())
    lines.append("")
    lines.append("markets_by_source_year:")
    lines.extend(
        f"  {year}: {report['markets_by_source_year'].get(str(year), 0)}"
        for year in RESEARCH_YEARS
    )
    lines.append("")
    lines.append("reasons:")
    lines.extend(f"  - {reason}" for reason in report["reasons"] or ["none"])
    lines.append("")
    lines.append("qa_by_code:")
    lines.extend(f"  {key}: {value}" for key, value in report["qa_by_code"].items())
    (output_dir / "extraction_report.txt").write_text("\n".join(lines), encoding="utf-8")


def extract_all(raw_dir: Path, output_db: Path) -> dict[str, Any]:
    raw_dir = raw_dir.resolve()
    output_db = output_db.resolve()

    # Deliberately reference only the ten research paths. Do not glob/list the
    # source directory and do not stat/open/hash 2025.tar or 2026.tar.
    source_paths = {year: raw_dir / f"{year}.tar" for year in RESEARCH_YEARS}
    missing = [year for year, path in source_paths.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing required research TARs: {missing}")

    started = time.time()
    con = connect_db(output_db)
    write_metadata(con, "schema_version", SCHEMA_VERSION)
    write_metadata(con, "protocol_hash", protocol_hash())
    write_metadata(con, "research_years", "2015-2024")
    write_metadata(con, "holdout_firewall", "2025-2026 NEVER ACCESSED")
    write_metadata(con, "extractor_sha256", sha256_file(Path(__file__).resolve()))
    con.commit()

    try:
        for year in RESEARCH_YEARS:
            process_year(con, year, source_paths[year])

        con.execute("ANALYZE")
        con.commit()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.commit()

        report = build_report(con, output_db, time.time() - started)
        write_metadata(con, "extraction_report", report)
        con.commit()
        write_report(report, output_db.parent)
        return report
    finally:
        con.close()


def verify_database(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        tables = {
            row[0] for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        required = {"metadata", "sources", "members", "markets", "runners", "snapshots", "qa_issues"}
        missing = sorted(required - tables)
        result = {
            "path": str(path.resolve()),
            "size_bytes": path.stat().st_size,
            "integrity_check": integrity,
            "missing_tables": missing,
            "markets": con.execute("SELECT COUNT(*) FROM markets").fetchone()[0] if "markets" in tables else None,
            "snapshots": con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] if "snapshots" in tables else None,
            "status": "PASS" if integrity == "ok" and not missing else "FAIL",
        }
        return result
    finally:
        con.close()


def synthetic_records(year: int) -> bytes:
    start_dt = datetime(year, 6, 1, 15, 0, tzinfo=timezone.utc)
    start_ms = int(start_dt.timestamp() * 1000)
    market_id = f"1.{year}00001"
    runners = [
        {"id": 101, "name": "Home", "sortPriority": 1, "status": "ACTIVE"},
        {"id": 102, "name": "Away", "sortPriority": 2, "status": "ACTIVE"},
        {"id": 103, "name": "The Draw", "sortPriority": 3, "status": "ACTIVE"},
    ]
    messages = []
    offsets = [1300, 650, 310, 130]
    prices = [(2.2, 3.5, 3.4), (2.18, 3.55, 3.45), (2.16, 3.6, 3.5), (2.14, 3.65, 3.55)]
    for index, (offset, price_triplet) in enumerate(zip(offsets, prices)):
        md = None
        if index == 0:
            md = {
                "eventTypeId": "1",
                "eventId": f"E{year}",
                "eventName": "Synthetic Home v Away",
                "competitionId": "C1",
                "competition": "Synthetic League",
                "countryCode": "GB",
                "name": "Match Odds",
                "marketType": "MATCH_ODDS",
                "bettingType": "ODDS",
                "marketBaseRate": 5.0,
                "numberOfWinners": 1,
                "turnInPlayEnabled": True,
                "marketTime": start_dt.isoformat().replace("+00:00", "Z"),
                "status": "OPEN",
                "inPlay": False,
                "runners": runners,
            }
        mc = {
            "id": market_id,
            "tv": 1000.0 + index * 100,
            "rc": [
                {"id": 101, "ltp": price_triplet[0], "tv": 400.0 + index * 20},
                {"id": 102, "ltp": price_triplet[1], "tv": 300.0 + index * 20},
                {"id": 103, "ltp": price_triplet[2], "tv": 300.0 + index * 20},
            ],
        }
        if md is not None:
            mc["marketDefinition"] = md
        messages.append({"op": "mcm", "pt": start_ms - offset * 1000, "mc": [mc]})

    final_runners = [
        {"id": 101, "name": "Home", "sortPriority": 1, "status": "WINNER"},
        {"id": 102, "name": "Away", "sortPriority": 2, "status": "LOSER"},
        {"id": 103, "name": "The Draw", "sortPriority": 3, "status": "LOSER"},
    ]
    messages.append(
        {
            "op": "mcm",
            "pt": start_ms + 7200 * 1000,
            "mc": [
                {
                    "id": market_id,
                    "marketDefinition": {
                        "eventTypeId": "1",
                        "eventId": f"E{year}",
                        "name": "Match Odds",
                        "marketType": "MATCH_ODDS",
                        "marketTime": start_dt.isoformat().replace("+00:00", "Z"),
                        "status": "CLOSED",
                        "inPlay": True,
                        "runners": final_runners,
                    },
                }
            ],
        }
    )
    return "\n".join(json.dumps(item, separators=(",", ":")) for item in messages).encode("utf-8")


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="football_v2_extract_test_") as tmp:
        root = Path(tmp)
        raw_dir = root / "raw"
        raw_dir.mkdir()
        for year in RESEARCH_YEARS:
            payload = bz2.compress(synthetic_records(year))
            tar_path = raw_dir / f"{year}.tar"
            with tarfile.open(tar_path, "w") as tf:
                info = tarfile.TarInfo(name=f"{year}/synthetic-{year}.json.bz2")
                info.size = len(payload)
                tf.addfile(info, io.BytesIO(payload))

        output_db = root / "output" / "research_pre2025.sqlite3"
        report = extract_all(raw_dir, output_db)
        con = sqlite3.connect(output_db)
        try:
            markets = con.execute("SELECT COUNT(*) FROM markets").fetchone()[0]
            snapshots = con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0]
            winners = con.execute("SELECT COUNT(*) FROM runners WHERE winner=1").fetchone()[0]
        finally:
            con.close()

        assert markets == 10, markets
        assert snapshots == 120, snapshots
        assert winners == 10, winners
        assert report["integrity_check"] == "ok", report
        assert report["classification"] == "PASS", report
        print("SELF TEST PASS")
        print(json.dumps({"markets": markets, "snapshots": snapshots, "winners": winners}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a pre-2025 Football research SQLite from 2015.tar through 2024.tar only."
    )
    parser.add_argument("--raw-dir", default=r"C:\BetfairMultiSport\Football\raw")
    parser.add_argument("--output", default=r"output\research_pre2025.sqlite3")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--verify", metavar="SQLITE_PATH")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        return

    if args.verify:
        result = verify_database(Path(args.verify))
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result["status"] == "PASS" else 2)

    report = extract_all(Path(args.raw_dir), Path(args.output))
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(2 if report["classification"] == "FAIL" else 0)


if __name__ == "__main__":
    main()
