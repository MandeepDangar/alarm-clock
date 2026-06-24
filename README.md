# ⏰ CLI Alarm Clock

A lightweight, production-minded alarm clock for the terminal. Add alarms, manage them by id, and let `run` block until the next one fires — with sound, JSON persistence, and zero third-party dependencies.

Built as a focused exercise: small surface area, clear behavior, and honest documentation of tradeoffs.

---

## Design decisions

### Single file (`alarm.py`)

Everything lives in one module rather than a package layout. For a tool this size, splitting into multiple files would add navigation overhead without improving testability much. Sections are separated with comments so the file stays scannable.

### Stdlib only

Uses `argparse`, `json`, `dataclasses`, and `pathlib` — no `pip install` step, no dependency drift, runs anywhere Python 3.10+ is available.

### JSON file persistence

Alarms are stored in `alarms.json` (configurable via `--file`). JSON is human-readable, easy to inspect during development, and sufficient for a single-user CLI tool. The schema includes a `version` field and a `next_id` counter so integer ids stay stable and monotonic.

### Integer ids with gaps

Ids are simple integers (`1`, `2`, `3`…), assigned via `next_id`. Deleted ids are never reused — gaps are intentional and keep the UX predictable (`delete 2` always means the same alarm).

### 24-hour local time, roll to tomorrow

Times are stored as `"HH:MM"` strings in local wall-clock time. If you add an alarm whose time has already passed today, it schedules for **tomorrow**. This avoids surprising immediate rings while keeping scheduling logic straightforward. Timezone and DST handling are explicitly out of scope.

### One-shot alarms by default

After an alarm fires during `run`, it is automatically **disabled** (`once: true`). This matches a simple “remind me once” model and prevents accidental re-rings on the next loop iteration. Re-enable with `enable <id>` to use it again.

### Foreground `run` loop

`run` is a blocking process — not a background daemon. It computes the next enabled alarm, sleeps in 1-second chunks (responsive to Ctrl+C), rings, persists state, and repeats. The process must stay alive for alarms to fire.

### Atomic writes

JSON is written to a temporary file and replaced with `os.replace()` to reduce the risk of a corrupted file if the process is interrupted mid-write.

### Platform-aware sound


| Platform      | Behavior                                                               |
| ------------- | ---------------------------------------------------------------------- |
| Windows       | `winsound.Beep()` — audible beep loop                                  |
| Linux / macOS | Terminal bell (`\a`) — may be silent if the terminal has bell disabled |
| All           | Printed `[ALARM]` message always shown                                 |


Sound can be suppressed with `run --no-sound`.

---

## Intentionally out of scope

These were considered and deliberately deferred to keep the tool shippable within a short timebox:


| Feature                                     | Reason deferred                                                |
| ------------------------------------------- | -------------------------------------------------------------- |
| Recurring / daily alarms                    | Requires recurrence rules and “already fired today” state      |
| Snooze                                      | Needs interactive prompt or timer logic during ring            |
| Background daemon / OS service              | Out of scope for a CLI exercise; `run` must stay in foreground |
| SQLite or external database                 | JSON is sufficient for single-user, low-volume storage         |
| Timezone / DST support                      | Adds complexity disproportionate to the use case               |
| Natural language times (`"7am tomorrow"`)   | Needs a parser; strict `HH:MM` is easier to validate           |
| File locking / multi-process safety         | Last-write-wins is acceptable for solo terminal use            |
| GUI / TUI                                   | CLI-only by requirement                                        |
| Third-party CLI libraries (`click`, `rich`) | Stdlib keeps install friction at zero                          |


---

## Requirements

- **Python 3.10+**
- No external packages

---

## Installation

Clone the repository and run directly with Python:

```bash
git clone https://github.com/<your-username>/alarm-clock.git
cd alarm-clock
```

Verify it works:

```bash
python alarm.py --help
```

---

## Usage

### Command reference


| Command                 | Description                                         |
| ----------------------- | --------------------------------------------------- |
| `add <TIME> [LABEL...]` | Add an alarm (optional multi-word label after time) |
| `list`                  | List all alarms; highlight the next one to ring     |
| `delete <ID>`           | Remove an alarm permanently                         |
| `enable <ID>`           | Turn an alarm on                                    |
| `disable <ID>`          | Turn an alarm off without deleting                  |
| `run`                   | Block until the next enabled alarm fires            |
| `run --no-sound`        | Same as `run`, but without beep                     |


Global option (works with any command):


| Option        | Description                                  |
| ------------- | -------------------------------------------- |
| `--file PATH` | Path to alarms JSON (default: `alarms.json`) |


---

### Scenarios & examples

#### Set a morning alarm

```bash
python alarm.py add 07:30 Wake up
# Added alarm 1 at 07:30 (Wake up)
```

#### Add a quick reminder with no label

```bash
python alarm.py add 14:00
# Added alarm 2 at 14:00
```

#### See all alarms and what rings next

```bash
python alarm.py list
```

Example output:

```text
Next to ring: alarm 1 at 2025-06-25 07:30 (tomorrow)

ID   TIME   STATUS    RINGS AT             LABEL
1    07:30  enabled   2025-06-25 07:30 *   Wake up
2    14:00  enabled   2025-06-24 14:00     Morning call
3    18:00  disabled  -                    Gym
```

The `*` marks the alarm that `run` will fire first. Disabled alarms show `-` in the **RINGS AT** column.

#### Temporarily silence an alarm

```bash
python alarm.py disable 2
# Alarm 2 disabled.
```

Re-enable later:

```bash
python alarm.py enable 2
# Alarm 2 enabled.
```

#### Remove an alarm you no longer need

```bash
python alarm.py delete 3
# Deleted alarm 3.
```

#### Wait for the next alarm to fire

```bash
python alarm.py run
```

Example session:

```text
Waiting for next alarm... (Ctrl+C to stop)
Next: alarm 2 at 2025-06-24 14:00 (14:00)
[ALARM] 14:00 — Morning call
```

After a one-shot alarm fires, it is automatically disabled and `alarms.json` is updated. The loop continues if other enabled alarms remain.

Stop waiting at any time with **Ctrl+C** (exit code `130`).

#### Run quietly (no beep)

Useful in shared spaces or when the terminal bell is already annoying:

```bash
python alarm.py run --no-sound
```

#### Add an alarm whose time already passed today

If it is currently 16:00 and you run:

```bash
python alarm.py add 09:00 Standup
```

The alarm schedules for **tomorrow at 09:00**, not immediately.

---

## Data format

`alarms.json` is created and managed automatically:

```json
{
  "version": 1,
  "next_id": 3,
  "alarms": [
    {
      "id": 1,
      "time": "07:30",
      "label": "Wake up",
      "enabled": true,
      "once": true
    }
  ]
}
```

Manual edits are supported but must remain valid — corrupt or duplicate ids will be rejected on load with a clear error.

---

## Exit codes


| Code  | Meaning                                                 |
| ----- | ------------------------------------------------------- |
| `0`   | Success                                                 |
| `1`   | Runtime error (invalid time, alarm not found, bad JSON) |
| `2`   | Usage error (invalid arguments)                         |
| `130` | Interrupted with Ctrl+C during `run`                    |


---

## What I would build with more time

Given another hour or two, these would be the highest-value additions in order:

1. **Unit tests** — `parse_time`, `next_fire_at`, `get_next_alarm`, and JSON load/save edge cases (`unittest`, still stdlib).
2. **Daily recurring alarms** — optional `--daily` flag on `add`, with `last_fired` tracking to avoid double-rings.
3. **Snooze** — interactive prompt after ring (`Snooze 5m? [y/N]`) or a `snooze` subcommand.
4. `**.gitignore` + sample config** — ignore `alarms.json`, ship `alarms.example.json`.
5. **Better cross-platform sound on Linux** — optional subprocess fallback to `paplay` / `afplay` behind a flag, while keeping stdlib as default.
6. **File locking** — simple lockfile to prevent two terminals from clobbering each other's writes.
7. `**next` command** — print only the next alarm without blocking (useful for scripts).
8. **Packaging** — `[project.scripts]` entry point in `pyproject.toml` so `alarm add 07:30` works after `pip install -e .`.

---

## License

MIT (or adjust to match your repository preference).