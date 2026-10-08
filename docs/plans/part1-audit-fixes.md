# Plan: Part 1 audit fixes

## Context

Audited `iperf3_client.py`, `destinations.py`, `run_experiments.py`, `report.py` against Part 1 of `assignment-2.pdf`. Self-checks pass. Met:

- 1(a): control connection + cookie, JSON param exchange, data connection, timed send, TEST_END / EXCHANGE_RESULTS / DISPLAY_RESULTS / IPERF_DONE termination. Busy (ACCESS_DENIED), rejected params (SERVER_ERROR), timeouts, premature termination (EOF, reset, control readable mid-test) all map to `IperfError`. `struct tcp_info` layout verified field by field against `include/uapi/linux/tcp.h` (168 bytes, offsets aligned).
- 1(b): random shuffle, `-n` configurable, addresses/ports/IP recorded in `metadata.json`, failures logged, bounded probe budget, shortfall logged + saved.
- 1(c): goodput = delta `tcpi_bytes_acked` * 8 / measured delta t from the data socket; per-destination panel plot; min/median/mean/p95 table per destination and algorithm.

Gaps found (two real, one minor):

1. **Probe too short to catch rate limits.** `DEFAULT_PROBE_SECONDS = 2` (`destinations.py:30`). iperf3's `--server-bitrate-limit` averages over a window (5 s by default) before aborting, so a rate-limited server passes the 2 s probe, then every real 60 s test fails. 1(b) says a rate-limiting server must be replaced; today it is not.
2. **Shortfall after selection is not reported.** `run_with_retries` (`run_experiments.py:207`) retries the same server and then records the run as failed (correct: Part 3 needs the same destinations for every algorithm). But a destination whose runs *all* failed is silently absent from the table and plot; `metadata.json` only has a `failed_runs` count. 1(b) asks to report any shortfall vs. requested n.
3. **Two crash paths on a malformed server reply** (escape `run_with_retries`, which only catches `IperfError`, and abort the whole campaign):
   - `recv_json` (`iperf3_client.py:362`): non-UTF-8 payload raises `UnicodeDecodeError`, not caught by the `json.JSONDecodeError` handler at line 777.
   - Server results JSON that is not an object (e.g. a list) makes `server_bytes_received` (`run_experiments.py:254`) raise `AttributeError` after an otherwise successful test.

Out of scope (not Part 1): Dockerfile, Part 2/3 plots.

Step 0 on approval: copy this plan to `docs/plans/part1-audit-fixes.md` (user rule: plans live in the repo).

## Changes

### 1. `destinations.py`: longer probe

- `DEFAULT_PROBE_SECONDS = 10`. Update its comment: long enough to outlast iperf3's server bitrate-limit averaging window (5 s default), so rate-limited servers fail the probe and get replaced; still short next to a 60 s test. Cost: about 8 s more per probe.
- Self-check unaffected (fake `run_experiment`).

### 2. `run_experiments.py`: report destinations with no data

- New function `destinations_without_data(selected, runs)`: returns the selected destinations (`host`, `port`) with no run whose `status == "ok"`. Plain loop, docstring explains it is the post-selection shortfall.
- `write_metadata`: add
  - `"destinations_without_data"`: that list,
  - `"effective_destinations"`: `len(selected) - len(that list)`,
  - keep `"destination_shortfall"` (selection), add `"effective_destination_shortfall"`: `args.destinations - effective_destinations`.
- `main()`: after the `with` block (normal completion only), if the list is non-empty, `logger.warning("shortfall: only %d of %d requested destinations produced data", ...)` so it shows in the terminal, not only in JSON.
- README: one line under Output describing the new metadata keys.

### 3. `iperf3_client.py`: malformed replies become `IperfError`

- `run_experiment` line 777: `except (json.JSONDecodeError, UnicodeDecodeError)` with the comment updated ("not valid UTF-8 JSON"). Do not catch bare `ValueError`: that would swallow the deliberate "algorithm unavailable" `ValueError` from `open_data_stream`.
- `recv_json`: after `json.loads`, if the result is not a `dict`, raise `IperfError("server sent JSON that is not an object")`. Docstring "Raises" updated. Every iperf3 message is an object, so this is a protocol check, and it protects `server_bytes_received`.
- Self-check: `socket.socketpair()` (stdlib, local, no network), `send_json(a, [1])`, assert `recv_json(b)` raises `IperfError`; also assert a dict round-trips.

## Verification

1. Self-checks: `python3 iperf3_client.py`, `python3 destinations.py`, `.venv/bin/python report.py`.
2. Docker smoke test (CLAUDE.md command, `-n 2 --duration 5 --algorithms cubic reno`): completes; `metadata.json` has `effective_destinations: 2`, empty `destinations_without_data`; probes log 10 s tests.
3. Shortfall path, no network: `python3 -c` calling `destinations_without_data` with two fake destinations and runs where one has only `"failed"` records; expect that one back.
