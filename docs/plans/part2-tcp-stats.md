# Plan: Part 2, TCP stats tracing, plots, and report sections

## Context

Part 2 (40 pts) asks for: (a) TCP_INFO stats from the data socket at the goodput sampling interval (required: timestamp, snd_cwnd, srtt, a loss signal, goodput; recommended: rttvar, pacing rate, byte counters, delivery rate), stored with units/destination/algorithm/run id, plus documentation of the kernel decoding format, interval math, and loss proxy; (b) auto-generated PDF plots for one representative destination: time series of cwnd, RTT, loss proxy, goodput, and scatters of cwnd/RTT/loss vs goodput; (c) written observations. Algorithm: CUBIC (Linux default), recorded as actually used.

Current state (main, bcac37b): most of 2(a) is done. `iperf3_client.take_sample()` (iperf3_client.py:553) logs every decoded `TCP_INFO_FIELDS` entry plus `t`, `unix_time`, `goodput_bps` per sample; `run_experiments.py` writes them to `samples.csv` with run columns and units in `metadata.json`. Missing: a per-interval loss proxy, kernel/config details in metadata, the 2(b) plots, and the report text.

The final report is markdown converted with **pandoc + LaTeX**, which embeds the PDF plots directly as vector images, so no PNG copies are needed.

Step 0 on approval: copy this plan to `docs/plans/part2-tcp-stats.md` (user rule: plans live in the repo).

## 1. `iperf3_client.py`

**Extend `TCP_INFO_FIELDS`** (line 114) past `delivery_rate` through `snd_wnd`, matching `include/uapi/linux/tcp.h` (verified layout, all naturally aligned, so `=` format still works):

| field | code | unit | why |
|---|---|---|---|
| busy_time | Q | microseconds | time spent sending |
| rwnd_limited | Q | microseconds | time limited by server's receive window (anomaly diagnosis) |
| sndbuf_limited | Q | microseconds | time limited by our send buffer |
| delivered | I | segments | spec's "delivered/retrans counters" |
| delivered_ce | I | segments | ECN-marked deliveries |
| bytes_sent | Q | bytes | kernel bytes sent incl. retransmits |
| bytes_retrans | Q | bytes | byte-level loss proxy |
| dsack_dups | I | count | spurious retransmits |
| reord_seen | I | count | reordering events |
| rcv_ooopack | I | segments | out-of-order packets received |
| snd_wnd | I | bytes | peer's advertised receive window |

- `TCP_INFO_SIZE` becomes 232 (update the `# 168 bytes` comment, the module comment "up to and including tcpi_snd_wnd", and the self-check `assert TCP_INFO_SIZE == 232`; padding in the fake raw buffer becomes `bytes(24)`).
- Update the `decode_tcp_info` error message with the minimum kernel. During implementation, confirm which release added `tcpi_snd_wnd` (expected 5.4) from the kernel git log; Ubuntu 22.04+ (5.15+) is fine either way.
- `TCP_INFO_BUFFER_SIZE = 256` stays (still larger than 232).

**Loss proxy in `take_sample`**: add `retrans_segs_interval = total_retrans - previous total_retrans` (None for the baseline sample), next to `goodput_bps`. Docstring/comment explains the choice: `retransmits` resets on every ACK and `lost` is an instantaneous snapshot, while the delta of the cumulative `total_retrans` counts every retransmission in the interval, the same way goodput uses the delta of `bytes_acked`.

**Naming clash**: the new tcp_info `bytes_sent` (kernel, includes retransmits) vs run_experiment's `bytes_sent` (bytes our app handed to `send()`). Rename only the metadata run-record key in run_experiments.py:341 to `app_bytes_sent`, with a comment saying how it differs.

## 2. `run_experiments.py`

- `sample_csv_columns()` / `measurement_units()`: add `retrans_segs_interval` ("segments retransmitted during the interval ending at t").
- New `read_kernel_tcp_settings()`: returns `{"default_congestion_control", "available_congestion_control", "tcp_info_kernel_size_bytes"}` from `/proc/sys/net/ipv4/tcp_congestion_control`, `.../tcp_available_congestion_control`, and `len(getsockopt(TCP_INFO, 512))` on a throwaway socket (works unconnected on Linux). Saved in `metadata.json` next to `host_kernel`; this is the "decoding format for your host kernel" evidence (kernel struct length vs the 232-byte prefix we decode).
- New option `--representative HOST:PORT` (default: auto, see below), passed to `report.generate_report`; works with `--report-only` so the destination can be re-picked after looking at the data.

## 3. `report.py` (extend; reads only `samples.csv`)

- `load_samples`: also load `snd_cwnd` (segments), `rtt_ms` and `min_rtt_ms` (µs / 1000), `retrans_segs_interval`.
- `choose_representative_destination(samples)`: candidates = destinations with data for every algorithm present; keep those with the most runs; pick the one whose mean goodput is the median among them (typical, not best or worst). Comment the reasoning.
- `compute_axis_limits(samples)`: per metric, max over all algorithms at the representative destination, so every algorithm's figure uses the same scales (Part 3 needs this; harmless for Part 2). All metrics are non-negative, so limits are `(0, max * 1.05)`.
- `plot_time_series(samples, algorithm, limits, path)`: 4 stacked panels sharing the time axis: cwnd (segments), srtt (ms) with min_rtt dashed (queueing delay = gap), retransmitted segments per interval, goodput (Mbit/s). One line per repetition, legend "rep 1..n".
- `plot_scatter(samples, algorithm, limits, path)`: 3 panels side by side sharing the goodput y axis: cwnd, srtt, retransmits vs goodput; points colored by repetition. Comment the timing mismatch: x values are snapshots at the end of the interval, goodput is the interval average.
- Outputs per algorithm in the results dir: `tcp_timeseries_<algorithm>.pdf`, `tcp_scatter_<algorithm>.pdf`. Part 2 uses the cubic pair; the reno/bbr pairs come for free for Part 3. Figure titles name destination and algorithm actually used.
- `generate_report(results_dir, representative=None)`: after the goodput summary, pick/validate the representative destination, log it, draw both figures per algorithm.
- Self-check: extend the fake CSV with the new columns and two repetitions; assert the auto-picked destination on known data, the axis limits, and that all four PDFs exist.

## 4. Report: `report/report.md` (new)

Build: `pandoc report/report.md -o report/report.pdf --resource-path=.:report` (needs a LaTeX engine, e.g. BasicTeX on macOS). Figures referenced from the committed results directory of the real campaign, e.g. `![](results/<dir>/tcp_timeseries_cubic.pdf)`. Commit that one results directory (`results/` is not git-ignored).

Skeleton with Part 1 and Part 3 as stub headings; Part 2 written now:

- **2(a)**: data comes from the data socket (link to `take_sample` / `read_tcp_info` line ranges, GitHub permalinks at the final commit); host kernel, default/available algorithms, kernel struct size from `metadata.json`; table of decoded fields (offset, C type, struct code, unit), generated once by a throwaway snippet over `TCP_INFO_FIELDS` and pasted in; interval math (goodput from `bytes_acked` delta over measured monotonic time, retrans delta); loss proxy rationale.
- **2(b)**: the two cubic figures, each with "generated by `report.plot_time_series`" links.
- **2(c)**: draft now (data-independent): what cwnd, srtt, retransmits, goodput mean and their expected effect in congestion avoidance (goodput ≈ cwnd · MSS / RTT; RTT rising with queueing at fixed cwnd; CUBIC's cwnd cut on loss and cubic regrowth). Fill after the real run: anomalies, with a checklist to look for: slow-start overshoot then loss burst, cwnd flat with `rwnd_limited`/`snd_wnd` showing a receive-window cap, `sndbuf_limited`, RTO backoff (`backoff`, goodput near 0), RTT inflation (bufferbloat), goodput spikes after recovery (cumulative ACKs).
- AI-use acknowledgment stub.

## 5. Docs

- `README.md`: new output files, `--representative`, minimum kernel, report build command.
- `CLAUDE.md`: report path and pandoc command.
- Dockerfile: no change (`COPY *.py` already picks everything up).

## Verification

1. Self-checks (macOS, no network): `python3 iperf3_client.py`, `python3 destinations.py`, `.venv/bin/python report.py`.
2. Docker smoke test (plumbing only, numbers meaningless): the CLAUDE.md docker command with `-n 2 --duration 5 --algorithms cubic reno`. Check `samples.csv` has `retrans_segs_interval` and the new fields, `metadata.json` has the kernel settings and `tcp_info_kernel_size_bytes >= 232`, and 4 PDFs exist.
3. `python3 run_experiments.py --report-only results/<dir> --representative host:port` redraws for the chosen destination; an unknown host:port gives a clear error.
4. Real run on a Linux host (full campaign), then fill 2(c) anomalies from the cubic figures.
5. `pandoc` build: figures appear in `report/report.pdf`.
