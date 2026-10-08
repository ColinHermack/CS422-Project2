# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

CS 422 (Computer Networks, Fall 2026) Assignment 2: iPerf, TCP Statistics, and Congestion Control. Full spec in `assignment-2.pdf`. Due Oct 21, 2026 11:45 PM ET; graded by oral exam the week of Oct 26, so the user must be able to explain every line. See **Code style** below: readability and documentation are the top priority.

`iperf3_client.py` holds the iperf3 protocol client and `run_experiment()` (Part 1a/1c). `destinations.py` loads the server list and picks n working servers by probing with short tests (Part 1b). `run_experiments.py` is the single entry point: selects destinations, runs every (repetition, destination, algorithm) test, writes `samples.csv` + `metadata.json` to `results/<timestamp>/`, then calls `report.py`, which writes `goodput_summary.csv` and `goodput_over_time.pdf` (Part 1c) from `samples.csv` only.

Commands:
- Self-checks (any OS, no network): `python3 iperf3_client.py`, `python3 destinations.py`, `.venv/bin/python report.py`.
- Full run (Linux only): `python3 run_experiments.py listed_iperf3_servers.csv -n 10 --duration 60 --interval 1 --repetitions 3 --algorithms cubic reno bbr`.
- Rebuild summary/plots from saved data (any OS): `python3 run_experiments.py --report-only results/<dir>`.
- Linux smoke test from macOS: `docker build -t cs422-a2 . && docker run --rm --network host --cap-add NET_ADMIN -v "$PWD/results":/app/results cs422-a2 listed_iperf3_servers.csv -n 2 --duration 5 --algorithms cubic reno` (Docker Desktop's kernel has no bbr, so the default CMD exits at the algorithm check there).

`Dockerfile` runs `run_experiments.py` with the full campaign as its default `CMD`; its header comment documents the host setup and `docker run` flags.

## Code style

Code must be easy for a human to read and understand. The user will be orally examined on every line, so readability is the top priority and overrides brevity, cleverness, and minimal diffs.

- **Readability first.** Prefer plain, explicit code: descriptive names, short functions with one job, straightforward control flow. Avoid dense one-liners, nested comprehensions, clever tricks, and unnecessary abstraction. If a simpler version is a few lines longer but easier to follow, use it.
- **Comprehensive documentation.** Every module gets a docstring explaining its purpose and how it fits the pipeline. Every function gets a docstring covering what it does, its arguments (with units), return value, and exceptions raised.
- **Explain the why, not just the what.** Comment non-obvious logic, especially protocol steps (cite the iperf3 state or source file they mirror), `struct` formats and byte layouts, socket options, timing math, and units (bytes vs. bits, microseconds vs. seconds, segments vs. bytes).
- **Name constants.** No magic numbers: protocol state codes, sizes, and timeouts are named constants with a comment on their meaning and source.
- **Document error paths.** For each failure case (timeout, busy server, rejected params, premature termination), say in a comment what triggers it and how it is handled.

## Setup

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Keep dependencies minimal: the iperf3 client and stats use only the stdlib (`socket`, `struct`, `json`, `statistics`); `matplotlib` is only for PDF plots (use the `Agg` backend).

## Hard constraints from the spec

- **Python iperf3 client written from scratch with raw sockets.** Must talk to real public iperf3 servers: control connection, JSON parameter exchange, data connection, timed send, proper iperf3 termination. Not allowed: invoking the `iperf3` binary, or running a custom receiver to simplify the protocol. Reading iperf3 source and tcpdump/wireshark captures is allowed.
- **Robustness required:** unresponsive/overloaded servers (iperf3 servers are single-client and often busy), rejected parameter negotiation, connect timeouts, premature termination. On failure, log it and try a replacement server with a bounded number of attempts; report any shortfall vs. requested `n`.
- **Stats come from the data socket, not the control socket**, via `getsockopt(TCP_INFO)`. Goodput = delta of cumulative acked bytes (e.g. `tcpi_bytes_acked`) over actual elapsed sample time, times 8. Also log `snd_cwnd`, `srtt`, a loss signal (retransmits/lost/total_retrans), and recommended `rttvar`, pacing rate, byte counters, delivery rate.
- **Congestion control selected per data socket before connect** via `setsockopt(TCP_CONGESTION)`; read it back and record the algorithm actually used. Compare `cubic`, `reno`, `bbr` with the same destinations, duration, sampling interval, and repetitions.
- **Output:** raw measurements as CSV/JSON (with units, destination, algorithm, run id), auto-generated PDF plots (time series + scatter vs goodput, consistent axes across algorithms), summary tables (min/median/mean/p95 goodput per destination and algorithm).
- **Single entry-point script** taking a server-list file plus CLI options for number of destinations, duration, sampling interval, repetitions.
- **Docker:** `FROM ubuntu:24.04`, runs the full pipeline.

## Platform

The dev machine is macOS, but the code must run on Linux (or WSL2). `TCP_INFO` layout and `TCP_CONGESTION` are Linux-specific; the `struct tcp_info` decoding format depends on the host kernel version and must be documented in the report. Docker on macOS uses a Linux VM kernel, which may lack `bbr`; real runs should happen on a Linux host. Do not expect socket-stat code to work natively on macOS. Docker Desktop on macOS also proxies outbound TCP, so `TCP_INFO` there describes the hop to Docker's proxy (sub-ms RTT, cwnd stuck near 10), not the real path: fine for protocol testing, useless for measurements.

## Server list

`listed_iperf3_servers.csv` (from iperf3serverlist.net), columns `IP/HOST,PORT,GB/S,CONTINENT,COUNTRY,SITE,PROVIDER`. `PORT` is either a single port (`5201`) or an inclusive range (`5201-5210`, `30001-30009`); parse ranges and pick a port from them. `GB/S` may be blank or non-numeric (`2x10`).
