#!/usr/bin/env python3
"""CLI alarm clock — stdlib only, JSON persistence."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

DEFAULT_ALARMS_FILE = Path("alarms.json")
SCHEMA_VERSION = 1
TIME_PATTERN = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


@dataclass
class Alarm:
    id: int
    time: str
    label: str = ""
    enabled: bool = True
    once: bool = True


@dataclass
class AlarmStore:
    version: int = SCHEMA_VERSION
    next_id: int = 1
    alarms: list[Alarm] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Validation & scheduling
# ---------------------------------------------------------------------------


def parse_time(value: str) -> tuple[int, int]:
    match = TIME_PATTERN.match(value.strip())
    if not match:
        raise ValueError(f"Invalid time '{value}'. Use 24-hour HH:MM (e.g. 07:30).")
    return int(match.group(1)), int(match.group(2))


def next_fire_at(alarm: Alarm, now: datetime | None = None) -> datetime:
    now = now or datetime.now()
    hour, minute = parse_time(alarm.time)
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def get_next_alarm(alarms: list[Alarm], now: datetime | None = None) -> tuple[Alarm, datetime] | None:
    now = now or datetime.now()
    enabled = [a for a in alarms if a.enabled]
    if not enabled:
        return None
    best: tuple[Alarm, datetime] | None = None
    for alarm in enabled:
        fire_at = next_fire_at(alarm, now)
        if best is None or fire_at < best[1] or (fire_at == best[1] and alarm.id < best[0].id):
            best = (alarm, fire_at)
    return best


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _alarm_from_dict(data: dict[str, Any]) -> Alarm:
    return Alarm(
        id=int(data["id"]),
        time=str(data["time"]),
        label=str(data.get("label", "")),
        enabled=bool(data.get("enabled", True)),
        once=bool(data.get("once", True)),
    )


def _validate_store(raw: dict[str, Any]) -> AlarmStore:
    if not isinstance(raw, dict):
        raise ValueError("Invalid alarms file: root must be a JSON object.")

    alarms_raw = raw.get("alarms")
    if not isinstance(alarms_raw, list):
        raise ValueError("Invalid alarms file: 'alarms' must be a list.")

    alarms: list[Alarm] = []
    seen_ids: set[int] = set()
    for item in alarms_raw:
        if not isinstance(item, dict):
            raise ValueError("Invalid alarms file: each alarm must be an object.")
        alarm = _alarm_from_dict(item)
        parse_time(alarm.time)
        if alarm.id in seen_ids:
            raise ValueError(f"Invalid alarms file: duplicate alarm id {alarm.id}.")
        seen_ids.add(alarm.id)
        alarms.append(alarm)

    next_id = raw.get("next_id")
    if next_id is None:
        next_id = max((a.id for a in alarms), default=0) + 1
    else:
        next_id = int(next_id)
        if next_id <= max((a.id for a in alarms), default=0):
            next_id = max((a.id for a in alarms), default=0) + 1

    version = int(raw.get("version", SCHEMA_VERSION))
    return AlarmStore(version=version, next_id=next_id, alarms=alarms)


def load_store(path: Path) -> AlarmStore:
    if not path.exists():
        return AlarmStore()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid alarms file: {exc.msg} at line {exc.lineno}.") from exc
    return _validate_store(raw)


def save_store(path: Path, store: AlarmStore) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": store.version,
        "next_id": store.next_id,
        "alarms": [asdict(alarm) for alarm in store.alarms],
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def find_alarm(store: AlarmStore, alarm_id: int) -> Alarm:
    for alarm in store.alarms:
        if alarm.id == alarm_id:
            return alarm
    raise ValueError(f"Alarm not found: {alarm_id}")


# ---------------------------------------------------------------------------
# Sound
# ---------------------------------------------------------------------------


def ring_alarm(alarm: Alarm, *, use_sound: bool = True) -> None:
    message = f"[ALARM] {alarm.time}"
    if alarm.label:
        message += f" — {alarm.label}"
    print(message, flush=True)

    if not use_sound:
        return

    if sys.platform == "win32":
        import winsound

        for _ in range(5):
            winsound.Beep(1000, 400)
            time.sleep(0.15)
    else:
        for _ in range(5):
            sys.stdout.write("\a")
            sys.stdout.flush()
            time.sleep(0.4)


def sleep_until(target: datetime) -> None:
    while True:
        remaining = (target - datetime.now()).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 1.0))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_add(store: AlarmStore, time_str: str, label: str) -> None:
    parse_time(time_str)
    alarm = Alarm(id=store.next_id, time=time_str, label=label)
    store.next_id += 1
    store.alarms.append(alarm)
    print(f"Added alarm {alarm.id} at {alarm.time}" + (f" ({label})" if label else ""))


def _day_label(fire_at: datetime, now: datetime) -> str:
    if fire_at.date() == now.date():
        return "today"
    if fire_at.date() == (now + timedelta(days=1)).date():
        return "tomorrow"
    return fire_at.strftime("%Y-%m-%d")


def cmd_list(store: AlarmStore) -> None:
    if not store.alarms:
        print("No alarms.")
        return

    now = datetime.now()
    next_result = get_next_alarm(store.alarms, now)
    next_id = next_result[0].id if next_result else None

    if next_result:
        next_alarm, next_at = next_result
        label = _day_label(next_at, now)
        print(
            f"Next to ring: alarm {next_alarm.id} at "
            f"{next_at.strftime('%Y-%m-%d %H:%M')} ({label})"
        )
    else:
        print("No enabled alarms scheduled.")
    print()

    print(f"{'ID':<4} {'TIME':<6} {'STATUS':<9} {'RINGS AT':<20} LABEL")
    for alarm in sorted(store.alarms, key=lambda a: a.id):
        status = "enabled" if alarm.enabled else "disabled"
        if alarm.enabled:
            fire_at = next_fire_at(alarm, now)
            rings = fire_at.strftime("%Y-%m-%d %H:%M")
            if alarm.id == next_id:
                rings += " *"
        else:
            rings = "-"
        print(f"{alarm.id:<4} {alarm.time:<6} {status:<9} {rings:<20} {alarm.label}")


def cmd_delete(store: AlarmStore, alarm_id: int) -> None:
    before = len(store.alarms)
    store.alarms = [a for a in store.alarms if a.id != alarm_id]
    if len(store.alarms) == before:
        raise ValueError(f"Alarm not found: {alarm_id}")
    print(f"Deleted alarm {alarm_id}.")


def cmd_set_enabled(store: AlarmStore, alarm_id: int, enabled: bool) -> None:
    alarm = find_alarm(store, alarm_id)
    alarm.enabled = enabled
    state = "enabled" if enabled else "disabled"
    print(f"Alarm {alarm_id} {state}.")


def cmd_run(store: AlarmStore, path: Path, use_sound: bool) -> None:
    if not any(a.enabled for a in store.alarms):
        print("No enabled alarms.")
        return

    print("Waiting for next alarm... (Ctrl+C to stop)")
    try:
        while True:
            result = get_next_alarm(store.alarms)
            if result is None:
                print("No enabled alarms.")
                return
            alarm, fire_at = result
            print(
                f"Next: alarm {alarm.id} at {fire_at.strftime('%Y-%m-%d %H:%M')} "
                f"({alarm.time})",
                flush=True,
            )
            sleep_until(fire_at)
            if datetime.now() < fire_at:
                continue
            ring_alarm(alarm, use_sound=use_sound)
            if alarm.once:
                alarm.enabled = False
            save_store(path, store)
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        raise SystemExit(130) from None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alarm",
        description="Simple CLI alarm clock (JSON storage, stdlib only).",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_ALARMS_FILE,
        help=f"Path to alarms JSON file (default: {DEFAULT_ALARMS_FILE})",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    add_p = sub.add_parser("add", help="Add an alarm")
    add_p.add_argument("time", help="Alarm time in 24-hour HH:MM format")
    add_p.add_argument(
        "label",
        nargs="*",
        default=[],
        metavar="LABEL",
        help="Optional label (words after time, e.g. add 07:30 Wake up)",
    )

    sub.add_parser("list", help="List all alarms and show which rings next")

    del_p = sub.add_parser("delete", help="Delete an alarm by id")
    del_p.add_argument("id", type=int, help="Alarm id")

    en_p = sub.add_parser("enable", help="Enable an alarm")
    en_p.add_argument("id", type=int, help="Alarm id")

    dis_p = sub.add_parser("disable", help="Disable an alarm")
    dis_p.add_argument("id", type=int, help="Alarm id")

    run_p = sub.add_parser("run", help="Wait until the next alarm fires")
    run_p.add_argument("--no-sound", action="store_true", help="Disable beep on ring")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    path: Path = args.file

    try:
        store = load_store(path)
        if args.command == "add":
            cmd_add(store, args.time, " ".join(args.label))
        elif args.command == "list":
            cmd_list(store)
        elif args.command == "delete":
            cmd_delete(store, args.id)
        elif args.command == "enable":
            cmd_set_enabled(store, args.id, True)
        elif args.command == "disable":
            cmd_set_enabled(store, args.id, False)
        elif args.command == "run":
            cmd_run(store, path, use_sound=not args.no_sound)
        else:
            parser.error(f"Unknown command: {args.command}")
            return 2
        if args.command != "run":
            save_store(path, store)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
