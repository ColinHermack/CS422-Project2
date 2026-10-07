# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

CS 422 (Computer Networks, Fall 2026) Assignment 2: iPerf, TCP Statistics, and Congestion Control. Full spec in `assignment-2.pdf`. Due Oct 21, 2026 11:45 PM ET; graded by oral exam the week of Oct 26, so the user must be able to explain every line. Keep code readable over clever.

No code exists yet. Update this file with real commands once the entry-point script and Dockerfile are written.

## Hard constraints from the spec

- **Python iperf3 client written from scratch with raw sockets.** Must talk to real public iperf3 servers: control connection, JSON parameter exchange, data connection, timed send, proper iperf3 termination. Not allowed: invoking the `iperf3` binary, or running a custom receiver to simplify the protocol. Reading iperf3 source and tcpdump/wireshark captures is allowed.
- **Robustness required:** unresponsive/overloaded servers (iperf3 servers are single-client and often busy), rejected parameter negotiation, connect timeouts, premature termination. On failure, log it and try a replacement server with a bounded number of attempts; report any shortfall vs. requested `n`.
- **Stats come from the data socket, not the control socket**, via `getsockopt(TCP_INFO)`. Goodput = delta of cumulative acked bytes (e.g. `tcpi_bytes_acked`) over actual elapsed sample time, times 8. Also log `snd_cwnd`, `srtt`, a loss signal (retransmits/lost/total_retrans), and recommended `rttvar`, pacing rate, byte counters, delivery rate.
- **Congestion control selected per data socket before connect** via `setsockopt(TCP_CONGESTION)`; read it back and record the algorithm actually used. Compare `cubic`, `reno`, `bbr` with the same destinations, duration, sampling interval, and repetitions.
- **Output:** raw measurements as CSV/JSON (with units, destination, algorithm, run id), auto-generated PDF plots (time series + scatter vs goodput, consistent axes across algorithms), summary tables (min/median/mean/p95 goodput per destination and algorithm).
- **Single entry-point script** taking a server-list file plus CLI options for number of destinations, duration, sampling interval, repetitions.
- **Docker:** `FROM ubuntu:24.04`, runs the full pipeline.

## Platform

The dev machine is macOS, but the code must run on Linux (or WSL2). `TCP_INFO` layout and `TCP_CONGESTION` are Linux-specific; the `struct tcp_info` decoding format depends on the host kernel version and must be documented in the report. Docker on macOS uses a Linux VM kernel, which may lack `bbr`; real runs should happen on a Linux host. Do not expect socket-stat code to work natively on macOS.

## Server list

`listed_iperf3_servers.csv` (from iperf3serverlist.net), columns `IP/HOST,PORT,GB/S,CONTINENT,COUNTRY,SITE,PROVIDER`. `PORT` is either a single port (`5201`) or an inclusive range (`5201-5210`, `30001-30009`); parse ranges and pick a port from them. `GB/S` may be blank or non-numeric (`2x10`).
