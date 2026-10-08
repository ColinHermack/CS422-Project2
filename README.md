# CS422 Assignment 2

From-scratch Python iperf3 client that measures goodput and TCP statistics (`TCP_INFO`) against public iperf3 servers, comparing congestion control algorithms.

Requires Linux (or WSL2) for experiments: `TCP_INFO` and `TCP_CONGESTION` are Linux socket options.

## Setup

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## Run

```sh
.venv/bin/python run_experiments.py listed_iperf3_servers.csv \
    -n 10 --duration 60 --interval 1 --repetitions 3 --algorithms cubic reno bbr
```

| Option | Default | Meaning |
|---|---|---|
| `server_list` | | CSV server list (`IP/HOST,PORT,...`, from iperf3serverlist.net) |
| `-n`, `--destinations` | 10 | number of destination servers |
| `--duration` | 60 | seconds of sending per test |
| `--interval` | 1.0 | seconds between `TCP_INFO` samples |
| `--repetitions` | 1 | tests per destination per algorithm |
| `--algorithms` | `cubic reno bbr` | congestion control algorithms to test |
| `--output` | `results/<YYYYmmdd-HHMMSS>` | results directory |
| `--seed` | random | seed for destination selection order |
| `--report-only DIR` | | rebuild summary and plots from an existing results directory |

Test order: for each repetition, for each destination, every algorithm back to back.

`bbr` usually needs `sudo modprobe tcp_bbr` first; the script exits early if an algorithm can't be set.

## Output (in the results directory)

- `samples.csv`: one row per sample: run id, repetition, destination, requested and actual algorithm, time, goodput, and every decoded `TCP_INFO` field.
- `metadata.json`: arguments, host kernel, `TCP_INFO` struct format, units of every measured column, selected destinations, selection failures and shortfall, per-run records (bytes sent/acked, server-reported bytes, errors).
- `goodput_summary.csv`: min / median / mean / p95 goodput (Mbit/s) per destination and algorithm.
- `goodput_over_time.pdf`: goodput over time, one panel per destination.

## Self-checks (any OS, no network)

```sh
python3 iperf3_client.py
python3 destinations.py
.venv/bin/python report.py
```
