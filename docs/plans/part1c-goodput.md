# Plan: Part 1(c) goodput recording, plots, and summary table

## Context

Part 1(c) asks for goodput sampled at a regular interval from the data socket's cumulative acked-byte counter, a plot of throughput over time for all destinations, and a summary table (min, median, mean, p95) per destination and algorithm.

Current state (branch `part1-iperf3-client`, commit 9a12761):
- `iperf3_client.py` already does the measurement core: `take_sample()` (line 542) reads `TCP_INFO` from the data socket and `compute_goodput_bps()` (line 228) computes `delta(bytes_acked) * 8 / delta(t)` using real elapsed monotonic time. `run_experiment()` (line 722) returns `{"host", "port", "server_ip", "congestion", "bytes_sent", "samples", "server_results"}`. First sample has `goodput_bps = None` (baseline).
- `destinations.py` has `load_servers()` and `select_destinations()` (1b).
- Missing for 1(c): nothing runs experiments over many destinations, nothing saves samples, no plot, no summary table. There is no entry-point script yet.

So 1(c) is mostly orchestration + output, and it naturally becomes the single entry-point script the Report section requires. Parts 2 and 3 will reuse the same saved CSV (it already holds every `tcp_info` field), so the layout is chosen with them in mind, but no Part 2/3 plots are built now.

Step 0 on approval: copy this plan to `docs/plans/part1c-goodput.md` (user rule: plans live in the repo).

## Files

### 1. `iperf3_client.py` (small edit): machine-readable units

Spec 2(a) wants units stored with the measurements. Units currently live only in comments on `TCP_INFO_FIELDS`. Change each entry from `(name, code)` to `(name, code, unit)`, e.g. `("rtt", "I", "microseconds")`, keeping the meaning comment. Update the two loops that unpack it (`build_tcp_info_format`, `decode_tcp_info`) and the self-check. Single source of truth: the decoder and the saved units can't drift.

### 2. `run_experiments.py` (new): single entry point

CLI (`argparse`, every option documented in `--help`):

| Option | Default | Meaning |
|---|---|---|
| `server_list` (positional) | | CSV file of servers |
| `-n/--destinations` | 10 | number of destinations |
| `--duration` | 60 | seconds per test |
| `--interval` | 1.0 | sampling interval, seconds |
| `--repetitions` | 1 | runs per destination per algorithm |
| `--algorithms` | `cubic reno bbr` | congestion controls to test |
| `--output` | `results/<YYYYmmdd-HHMMSS>` | output directory |
| `--seed` | None | destination-selection seed |
| `--report-only DIR` | | skip experiments, regenerate summary + plots from an existing results dir |

Functions (one job each):
- `check_algorithms_available(algorithms)`: open a throwaway socket, `setsockopt(TCP_CONGESTION)` for each name; exit with a clear message listing the missing ones before spending minutes on selection. Catches the "bbr not loaded" / "not in tcp_allowed_congestion_control" case up front.
- `run_with_retries(destination, algorithm, args)`: call `iperf3_client.run_experiment`; on `IperfError` log, wait a few seconds (named constant), retry up to a bounded count (named constant, e.g. 3). Busy is usually transient. We retry the *same* destination instead of replacing it, because Part 3 requires the same destinations for every algorithm; a run that still fails is recorded as a failure, not silently dropped.
- `run_all(destinations, args, writer)`: loop order `for repetition: for destination: for algorithm:` so the three algorithms run back-to-back on the same path, which limits time-of-day bias between them (Part 3 asks for the test order). Assign `run_id` as an increasing integer = execution order.
- `write_samples(writer, run_info, result)`: append one CSV row per sample, flushing after each run so a crash mid-campaign keeps finished runs.
- `main()`: parse args, check algorithms, `load_servers` + `select_destinations` (reused from `destinations.py`), run, write metadata, call `report.generate_report(output_dir)`.

Outputs in the results dir:
- `samples.csv`: long format, one row per sample. Columns: `run_id, repetition, host, port, server_ip, algorithm_requested, algorithm_used, t, unix_time, goodput_bps`, then every `tcp_info` field.
- `metadata.json`: CLI args, `platform.release()` (host kernel, needed for the report), `TCP_INFO` format string and size, units for every CSV column (from `TCP_INFO_FIELDS` plus `t: seconds`, `goodput_bps: bits/second`), selected destinations, selection failures and shortfall from `select_destinations`, and per-run records (run_id, order, destination, algorithm, bytes_sent, server-reported bytes, failures).

### 3. `report.py` (new): summary table + plot, reads only `samples.csv`

Reading from the saved CSV (not in-memory results) means the plots and table can be regenerated without rerunning a 30+ minute campaign.

- `load_samples(path)`: `csv.DictReader`, convert the numeric columns used here to float; skip rows whose `goodput_bps` is empty (the baseline sample of each run).
- `percentile_95(values)`: `statistics.quantiles(values, n=100, method="inclusive")[94]`; comment why `inclusive` (treats data as the whole population, so p95 stays within observed min/max) and handle the 1-value case.
- `summarize_goodput(samples)`: group by `(host, port, algorithm_used)`, pooling all repetitions; return rows with sample count, min, median, mean, p95 in Mbit/s.
- `write_summary(rows, csv_path)` + `print_summary(rows)`: `goodput_summary.csv` and an aligned table on stdout.
- `plot_goodput_over_time(samples, pdf_path)`: `matplotlib.use("Agg")`; one panel per destination in a grid (`sharex`, `sharey` so destinations are comparable), one line per (algorithm, repetition), color by algorithm, legend, y in Mbit/s, x in seconds since send start, panel title `host:port`. Saves `goodput_over_time.pdf`.
- `generate_report(results_dir)`: calls the above.
- Self-check (`__main__`): fake samples for two destinations and two algorithms; assert summary min/median/mean/p95 on known numbers; write the PDF to the scratch temp dir and assert the file exists.

### 4. Docs

- `CLAUDE.md`: replace "Entry-point script ... not written yet" with the real commands.
- `README.md`: usage example and output file list (Report section requires documented CLI and reproduction commands).

## Decisions worth knowing for the oral exam

- Goodput uses `tcpi_bytes_acked`, so it counts only data the receiver acknowledged, not data parked in our send buffer. `bytes_sent` will exceed acked bytes by roughly the send buffer size at the end.
- Elapsed time is measured, not assumed, so a late sample does not inflate goodput.
- Summary excludes the t=0 baseline (no interval) and pools repetitions per destination and algorithm, as the spec asks.
- Not built now (YAGNI until Parts 2/3): cwnd/RTT/loss plots, scatter plots, Dockerfile.

## Verification

1. Self-checks on macOS, no network: `python3 iperf3_client.py`, `python3 destinations.py`, `.venv/bin/python report.py`.
2. Pipeline smoke test on Linux via Docker (Docker Desktop proxies TCP, so numbers are meaningless, but this proves the plumbing):
   `docker run --rm -v "$PWD":/app -w /app ubuntu:24.04 sh -c "apt-get update -qq && apt-get install -y -qq python3 python3-matplotlib && python3 run_experiments.py listed_iperf3_servers.csv -n 2 --duration 5 --interval 1 --algorithms cubic reno"`
   Check: `samples.csv` has about 2 x 2 x 6 rows, `algorithm_used` matches requested, `goodput_summary.csv` has 4 rows, `goodput_over_time.pdf` has 2 panels with 2 lines each, `metadata.json` lists kernel and units.
3. `python3 run_experiments.py --report-only results/<dir>` regenerates the same files.
4. `--algorithms bbr` on a kernel without bbr: exits immediately with the missing-algorithm message.
5. Real measurement run on a Linux host (not Docker Desktop) before writing the report.
