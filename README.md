# CS422 Assignment 2

From-scratch Python iperf3 client that measures goodput and TCP statistics (`TCP_INFO`) against public iperf3 servers, comparing congestion control algorithms.

Requires Linux 5.4+ (or WSL2) for experiments: `TCP_INFO` and `TCP_CONGESTION` are Linux socket options, and the decoded `struct tcp_info` prefix ends at `tcpi_snd_wnd` (added in 5.4).

## AI Use Disclaimer
Claude Code and OpenAI Codex were used for code generation and report compilation during this project. All AI-generated code and reports were reviewed and verified by human groupmembers.

## Setup

No manual Python setup is required. If a plotting dependency is missing,
`run_experiments.py` creates `.venv`, installs `requirements.txt`, and
restarts itself with that environment. To prepare the environment without
starting a campaign:

```sh
python3 run_experiments.py --check-environment --algorithms cubic reno
```

## Run

```sh
python3 run_experiments.py
```

With no arguments this uses the bundled server list and runs the complete
campaign: 10 destinations, 60 seconds, a 1-second sample interval, three
repetitions, and `cubic reno bbr`. Options can override any default:

| Option | Default | Meaning |
|---|---|---|
| `server_list` | bundled list | CSV server list (`IP/HOST,PORT,...`, from iperf3serverlist.net) |
| `-n`, `--destinations` | 10 | number of destination servers |
| `--duration` | 60 | seconds of sending per test |
| `--interval` | 1.0 | seconds between `TCP_INFO` samples |
| `--repetitions` | 3 | tests per destination per algorithm |
| `--algorithms` | `cubic reno bbr` | congestion control algorithms to test |
| `--output` | `results/<YYYYmmdd-HHMMSS>` | results directory |
| `--seed` | random | seed for destination selection order |
| `--representative HOST:PORT` | automatic | destination for the TCP stats plots (default: the destination with data for every algorithm whose mean goodput is the median) |
| `--report-only DIR` | | rebuild summary and plots from an existing results directory |
| `--check-environment` | | install/check dependencies and TCP algorithms, then exit |

Test order: for each repetition, for each destination, every algorithm back to back.

When run directly on Linux/WSL2, the script attempts to load `tcp_bbr`
automatically when BBR is requested. It may ask for the user's sudo password.

## Docker

Runs the full pipeline in `ubuntu:24.04`. The container uses the host's kernel,
so the automated launcher first loads BBR on the WSL2/Linux host, builds the
image, verifies all three algorithms inside the container, and starts the
campaign:

```sh
./run_wsl_docker.sh
```

The launcher may request the sudo password once to load `tcp_bbr`. Pass normal
experiment arguments after the script to replace the Docker defaults, for
example `./run_wsl_docker.sh -n 2 --duration 5 --repetitions 1`.
Graded measurements require Docker Engine installed directly inside the WSL2
distribution (or native Linux). The launcher rejects experiment runs when it
detects Docker Desktop because Desktop proxies outbound TCP even with host
networking; in that environment, `TCP_INFO` describes the local proxy instead
of the public-server path. `--check-environment` remains available under Docker
Desktop for dependency and algorithm checks, but it does not validate the
measurement path.

- `--network host`: with native Docker Engine, sockets use the host's network stack directly, with no NAT layer.
- `--cap-add NET_ADMIN`: needed to select algorithms outside `net.ipv4.tcp_allowed_congestion_control` (usually bbr).
- `-v ...`: keeps the results on the host.

With no arguments the image runs `-n 10 --duration 60 --interval 1 --repetitions 3 --algorithms cubic reno bbr`; arguments after the launcher replace that (same options as above). The kernel version and congestion-control configuration are saved in `metadata.json` automatically.

## Output (in the results directory)

- `samples.csv`: one row per sample: run id, repetition, destination, requested and actual algorithm, time, goodput, retransmitted segments in the interval (loss proxy), and every decoded `TCP_INFO` field.
- `metadata.json`: arguments, host kernel, default and available congestion control, the kernel's `struct tcp_info` length, `TCP_INFO` struct format, units of every measured column, selected destinations, selection failures and shortfall, destinations whose every run failed (`destinations_without_data`, `effective_destination_shortfall`), per-run records (bytes sent/acked, server-reported bytes, errors).
- `goodput_summary.csv`: min / median / mean / p95 goodput (Mbit/s) per destination and algorithm.
- `goodput_over_time.pdf`: goodput over time, one panel per destination.
- `tcp_timeseries_<algorithm>.pdf`: cwnd, RTT, retransmissions, and goodput over time for the representative destination (same axes for every algorithm).
- `tcp_scatter_<algorithm>.pdf`: cwnd, RTT, and retransmissions against goodput for the representative destination.

## Report

`report/report.md` is the written report. Build it from the repository root (needs pandoc and a LaTeX engine; it embeds the PDF plots directly):

```sh
pandoc report/report.md -o report/report.pdf
```

## Self-checks (any OS, no network)

```sh
python3 iperf3_client.py
python3 destinations.py
.venv/bin/python report.py
```
