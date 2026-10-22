---
title: "CS 422 Assignment 2: iPerf, TCP Statistics, and Congestion Control"
author: Colin Hermack
date: Fall 2026
geometry: margin=1in
colorlinks: true
---

<!--
Build from the repository root (pandoc resolves image paths from there):

    pandoc report/report.md -o report/report.pdf

Data source: results/20261021-152852 (real campaign, 10 destinations,
60s duration, 1.0s interval, 3 repetitions, cubic+reno+bbr, host kernel
6.18.54.1-microsoft-standard-WSL2, WSL2 after `wsl --update`).
NOTE: this run used `.venv/bin/python run_experiments.py` directly, not the
Docker image — the spec wants the experiment pipeline run via Docker on a
host with bbr available. TODO before submission: re-run (or at least
smoke-test) via `docker build/run` per README.md on this same host and
confirm results match, or document why the direct run stands in.

Before submitting:
  - Replace "blob/main" in code links with "blob/<final commit hash>" so the
    line ranges stay correct, and re-check every line range.
  - Fill in every remaining TODO (Part 1 writeup, Part 3 discussion,
    anomalous-behavior observations, AI tool use).
-->

Repository: <https://github.com/ColinHermack/CS422-Project2>

# 1. iPerf Throughput Application

TODO (Part 1).

# 2. TCP Stats Tracing During Transfer

All measurements, plots, and observations in this section use **CUBIC**, the
default congestion control on the measurement host
(`net.ipv4.tcp_congestion_control = cubic`). The client still selects
`cubic` explicitly on the data socket and records the algorithm the kernel
reports back (`algorithm_used` in `samples.csv`); every run used `cubic`.
The data is the cubic subset of the full campaign in
`results/20261021-152852` (10 destinations, 60 s duration per test, 1.0 s
sampling interval, 3 repetitions; test order: for each repetition, for each
destination, every algorithm back to back).

## 2(a) Extracting TCP socket statistics

**Source socket.** Statistics come from the data socket, the TCP connection
that carries the test payload, never from the iperf3 control socket.
[`take_sample`](https://github.com/ColinHermack/CS422-Project2/blob/main/iperf3_client.py#L567-L617)
calls
[`read_tcp_info`](https://github.com/ColinHermack/CS422-Project2/blob/main/iperf3_client.py#L230-L240),
which runs `getsockopt(IPPROTO_TCP, TCP_INFO)` on the data socket and decodes
the returned `struct tcp_info` with
[`decode_tcp_info`](https://github.com/ColinHermack/CS422-Project2/blob/main/iperf3_client.py#L200-L227).

**Host kernel.** From `results/20261021-152852/metadata.json`:
`host_kernel` (`uname -r`) is `6.18.54.1-microsoft-standard-WSL2`,
`host_platform` is
`Linux-6.18.54.1-microsoft-standard-WSL2-x86_64-with-glibc2.35`. The
kernel's default congestion control is `cubic`, with `reno`, `cubic`, and
`bbr` all available (`kernel_tcp_settings`). The kernel-reported
`struct tcp_info` length is 280 bytes (`tcpi_kernel_size_bytes`); we decode
the first 232 bytes as described below.

**Decoding format.** The layout is Linux's `struct tcp_info` from
`include/uapi/linux/tcp.h`. We decode the first 232 bytes, from
`tcpi_state` through `tcpi_snd_wnd` (the last field added in Linux 5.4), with
the Python `struct` format string

```
=BBBBBBBBIIIIIIIIIIIIIIIIIIIIIIIIQQQQIIIIIIQQQQIIQQIIII
```

`=` means native byte order with no automatic padding; this matches the
kernel struct because every field is already naturally aligned (each
`__u64` starts at a multiple of 8). Kernels newer than 5.4 append more
fields after `tcpi_snd_wnd`, so we request a 256-byte buffer and decode only
the 232-byte prefix; a kernel that returns fewer than 232 bytes is rejected.
The field list, format codes, and units live in one table in the code,
[`TCP_INFO_FIELDS`](https://github.com/ColinHermack/CS422-Project2/blob/main/iperf3_client.py#L115-L172),
so the decoder and the units saved in `metadata.json` cannot drift apart.

| Offset (bytes) | Field | C type | struct code | Unit |
|----:|----------------------|------|-----|-----------|
| 0 | `tcpi_state` | `__u8` | `B` | code |
| 1 | `tcpi_ca_state` | `__u8` | `B` | code |
| 2 | `tcpi_retransmits` | `__u8` | `B` | count |
| 3 | `tcpi_probes` | `__u8` | `B` | count |
| 4 | `tcpi_backoff` | `__u8` | `B` | count |
| 5 | `tcpi_options` | `__u8` | `B` | bit flags |
| 6 | `tcpi_wscale`\* | `__u8` | `B` | bit fields |
| 7 | `tcpi_app_limited_flags`\* | `__u8` | `B` | bit flags |
| 8 | `tcpi_rto` | `__u32` | `I` | microseconds |
| 12 | `tcpi_ato` | `__u32` | `I` | microseconds |
| 16 | `tcpi_snd_mss` | `__u32` | `I` | bytes |
| 20 | `tcpi_rcv_mss` | `__u32` | `I` | bytes |
| 24 | `tcpi_unacked` | `__u32` | `I` | segments |
| 28 | `tcpi_sacked` | `__u32` | `I` | segments |
| 32 | `tcpi_lost` | `__u32` | `I` | segments |
| 36 | `tcpi_retrans` | `__u32` | `I` | segments |
| 40 | `tcpi_fackets` | `__u32` | `I` | segments |
| 44 | `tcpi_last_data_sent` | `__u32` | `I` | milliseconds |
| 48 | `tcpi_last_ack_sent` | `__u32` | `I` | milliseconds |
| 52 | `tcpi_last_data_recv` | `__u32` | `I` | milliseconds |
| 56 | `tcpi_last_ack_recv` | `__u32` | `I` | milliseconds |
| 60 | `tcpi_pmtu` | `__u32` | `I` | bytes |
| 64 | `tcpi_rcv_ssthresh` | `__u32` | `I` | bytes |
| 68 | `tcpi_rtt` | `__u32` | `I` | microseconds |
| 72 | `tcpi_rttvar` | `__u32` | `I` | microseconds |
| 76 | `tcpi_snd_ssthresh` | `__u32` | `I` | segments |
| 80 | `tcpi_snd_cwnd` | `__u32` | `I` | segments |
| 84 | `tcpi_advmss` | `__u32` | `I` | bytes |
| 88 | `tcpi_reordering` | `__u32` | `I` | segments |
| 92 | `tcpi_rcv_rtt` | `__u32` | `I` | microseconds |
| 96 | `tcpi_rcv_space` | `__u32` | `I` | bytes |
| 100 | `tcpi_total_retrans` | `__u32` | `I` | segments |
| 104 | `tcpi_pacing_rate` | `__u64` | `Q` | bytes/second |
| 112 | `tcpi_max_pacing_rate` | `__u64` | `Q` | bytes/second |
| 120 | `tcpi_bytes_acked` | `__u64` | `Q` | bytes |
| 128 | `tcpi_bytes_received` | `__u64` | `Q` | bytes |
| 136 | `tcpi_segs_out` | `__u32` | `I` | segments |
| 140 | `tcpi_segs_in` | `__u32` | `I` | segments |
| 144 | `tcpi_notsent_bytes` | `__u32` | `I` | bytes |
| 148 | `tcpi_min_rtt` | `__u32` | `I` | microseconds |
| 152 | `tcpi_data_segs_in` | `__u32` | `I` | segments |
| 156 | `tcpi_data_segs_out` | `__u32` | `I` | segments |
| 160 | `tcpi_delivery_rate` | `__u64` | `Q` | bytes/second |
| 168 | `tcpi_busy_time` | `__u64` | `Q` | microseconds |
| 176 | `tcpi_rwnd_limited` | `__u64` | `Q` | microseconds |
| 184 | `tcpi_sndbuf_limited` | `__u64` | `Q` | microseconds |
| 192 | `tcpi_delivered` | `__u32` | `I` | segments |
| 196 | `tcpi_delivered_ce` | `__u32` | `I` | segments |
| 200 | `tcpi_bytes_sent` | `__u64` | `Q` | bytes |
| 208 | `tcpi_bytes_retrans` | `__u64` | `Q` | bytes |
| 216 | `tcpi_dsack_dups` | `__u32` | `I` | segments |
| 220 | `tcpi_reord_seen` | `__u32` | `I` | count |
| 224 | `tcpi_rcv_ooopack` | `__u32` | `I` | segments |
| 228 | `tcpi_snd_wnd` | `__u32` | `I` | bytes |

\* Bit fields, decoded as one byte each: `wscale` holds
`tcpi_snd_wscale:4` and `tcpi_rcv_wscale:4`; `app_limited_flags` holds
`tcpi_delivery_rate_app_limited:1` and `tcpi_fastopen_client_fail:2`.

**Sampling and interval measurements.** While sending,
[`send_and_sample`](https://github.com/ColinHermack/CS422-Project2/blob/main/iperf3_client.py#L634-L698)
uses `select()` with a timeout so that sending never blocks past the next
sample deadline. Sample *k* is due at `start + k * interval` (computed from
*k*, so lateness does not accumulate), with a baseline sample at *t* = 0 and
the final one clamped to the end of the test. Each sample's timestamp is
taken with `time.monotonic()` immediately after `getsockopt`, so it matches
the counters. Interval quantities use the difference between consecutive
samples $i-1$ and $i$ and the **measured** elapsed time, not the nominal
interval:

$$\text{goodput}_i = \frac{\texttt{bytes\_acked}_i - \texttt{bytes\_acked}_{i-1}}{t_i - t_{i-1}} \cdot 8 \quad \text{[bits/s]}$$

$$\text{retrans\_segs\_interval}_i = \texttt{total\_retrans}_i - \texttt{total\_retrans}_{i-1} \quad \text{[segments]}$$

`tcpi_bytes_acked` counts bytes the receiver acknowledged, so goodput
excludes data still sitting in our send buffer and counts retransmitted
data only once.

**Loss proxy.** TCP never observes loss directly; it infers it and
retransmits. We use **segments retransmitted per interval**, the change in
the cumulative counter `tcpi_total_retrans`. The alternatives are
snapshots that miss events between samples: `tcpi_retransmits` resets to 0
on every new ACK, and `tcpi_lost` counts only the segments presumed lost at
the instant of the sample. `total_retrans` includes spurious
retransmissions (also logged as `tcpi_dsack_dups`), so the proxy can
over-count loss on paths that reorder packets.

**Stored format.** `results/20261021-152852/samples.csv` has one row per sample with the
run id, repetition, destination host, port and IP, requested and actually
used algorithm, `t`, `unix_time`, `goodput_bps`, `retrans_segs_interval`,
and every decoded `tcp_info` field. `metadata.json` maps every measured
column to its unit and records the host kernel, the struct format, the
selected destinations, and each run's outcome.

## 2(b) Visualization

The plots are generated automatically at the end of every campaign
([`plot_tcp_stats`](https://github.com/ColinHermack/CS422-Project2/blob/main/report.py#L615-L656)).
The representative destination, `speed1.fiberby.dk:9213`, is picked by
[`choose_representative_destination`](https://github.com/ColinHermack/CS422-Project2/blob/main/report.py#L391-L450):
among the destinations with data for every algorithm and no failed
repetition, the one whose mean goodput is the median, so the plots show a
typical path rather than the fastest or slowest. Each repetition is one
line (time series) or one color (scatter).

![TCP stats over time (CUBIC). From top: congestion window, smoothed RTT (dashed: minimum RTT), retransmitted segments per interval, goodput. Generated by `report.plot_time_series`.](results/20261021-152852/tcp_timeseries_cubic.pdf)

Generated by
[`plot_time_series`](https://github.com/ColinHermack/CS422-Project2/blob/main/report.py#L510-L568).
cwnd and RTT are snapshots at each sample time, drawn as lines;
retransmissions and goodput describe a whole interval, drawn as steps.

![Congestion window, smoothed RTT, and retransmissions against goodput (CUBIC). Generated by `report.plot_scatter`.](results/20261021-152852/tcp_scatter_cubic.pdf)

Generated by
[`plot_scatter`](https://github.com/ColinHermack/CS422-Project2/blob/main/report.py#L571-L612).
Each point is one sample. Goodput is the average over the interval ending
at the sample, while cwnd and RTT are snapshots at its end, so a point
taken right after a sudden change pairs the new cwnd with the previous
interval's goodput.

## 2(c) Observations

**Congestion window (`snd_cwnd`, segments).** The largest number of
unacknowledged segments the sender allows in flight. A window-limited
sender delivers about one window per round trip, so in congestion
avoidance

$$\text{goodput} \approx \frac{\min(\text{cwnd} \cdot \text{MSS},\ \text{rwnd})}{\text{RTT}}.$$

CUBIC grows the window as a cubic function of the time since the last loss,
$W(t) = C (t - K)^3 + W_{max}$: it rises quickly, flattens near the window
$W_{max}$ where the last loss happened, then probes beyond it. On a loss it
cuts the window to $\beta = 0.7$ of its value. We therefore expect goodput to
follow cwnd (a roughly linear cwnd vs goodput scatter with slope
MSS / RTT) as long as the window is below the bandwidth-delay product (BDP).
Once cwnd exceeds the BDP, extra window only fills the bottleneck queue:
goodput stops growing and RTT rises instead.

**Smoothed RTT (`tcpi_rtt`, shown in ms) and minimum RTT.** `srtt` is an
exponentially weighted average of RTT samples (gain 1/8, RFC 6298), and
`rttvar` tracks its variation. `min_rtt` approximates the propagation delay,
so `srtt - min_rtt` estimates the queueing delay our own traffic and cross
traffic add. For a loss-based algorithm like CUBIC we expect RTT to climb
as the window grows past the BDP and the bottleneck buffer fills, while
goodput plateaus at the bottleneck rate; RTT drops back after each window
cut drains the queue. At a fixed window, higher RTT means lower goodput
(the formula above), so the RTT vs goodput scatter should show goodput
flat or falling as RTT grows, not rising.

**Retransmitted segments per interval (loss proxy).** Each loss event
detected by duplicate ACKs, SACK, or RACK triggers fast retransmit and a
multiplicative decrease, so we expect goodput to dip in the interval
containing the loss or the next one. A retransmission timeout is worse: the
window falls to 1 segment and slow start restarts, so goodput collapses for
several intervals (also visible as nonzero `tcpi_backoff`). Intervals with
retransmissions should therefore cluster at lower goodput in the scatter,
although a single retransmission costs little if the window recovers within
the same interval.

**Goodput.** Bytes acknowledged per second. It is bounded by the bottleneck
link capacity, our share of it against cross traffic, the server's receive
window (`tcpi_snd_wnd`), and any per-client rate limit on the server.

**Anomalous behavior.** TODO after the real run. Check the cubic traces
for:

- Slow-start overshoot: a large cwnd in the first seconds followed by a
  burst of retransmissions and a cwnd collapse.
- cwnd flat while goodput is also flat: compare `rwnd_limited` and
  `sndbuf_limited` (time limited by the receive window or our send buffer)
  with `busy_time`, and `snd_wnd` with cwnd times MSS. If the flow is
  receive-window limited, cwnd is not the bottleneck.
- Retransmission timeouts: nonzero `backoff`, goodput near zero for one or
  more intervals.
- RTT inflation (bufferbloat): srtt far above min_rtt during steady
  sending.
- Goodput spikes right after a recovery (a burst of cumulative ACKs covers
  data sent earlier).
- Differences between repetitions on the same path (cross traffic, route
  changes).

# 3. Compare Algorithms and Design a Congestion Control Algorithm

## 3(a) Compare CUBIC, Reno, and BBR

Same campaign as above, `results/20261021-152852`: the same 10 destinations,
60 s duration, 1.0 s sampling interval, and 3 repetitions, with
`--algorithms cubic reno bbr` so every destination gets all three
algorithms back to back within each repetition (test order: for each
repetition, for each destination, every algorithm). The algorithm is set on
the data socket before `connect()` and the actually-applied algorithm read
back afterward, both in
[`open_data_stream`](https://github.com/ColinHermack/CS422-Project2/blob/main/iperf3_client.py#L502-L551)
(`setsockopt(IPPROTO_TCP, TCP_CONGESTION, ...)` before connecting, then a
matching `getsockopt` readback). The kernel-reported algorithm actually used
(`algorithm_used` in `samples.csv`) matched the requested one on every run
except where noted below. Host kernel: `6.18.54.1-microsoft-standard-WSL2`
(the stock WSL2 kernel ships `tcp_bbr.ko`, loadable without root, once WSL
is updated past the 5.15 line — see "Reproducing the results").

Out of 90 scheduled runs (10 destinations x 3 algorithms x 3 repetitions),
89 completed; `la.speedtest.clouvider.net:5205` (bbr, repetition 2) failed
all 3 retry attempts with the server rejecting parameter exchange
(`server busy / ACCESS_DENIED`) and was skipped, per the bounded-retry
robustness requirement. No destination is missing data entirely
(`destinations_without_data: []` in `metadata.json`).

**Representative destination for the plots below: same as Part 2,**
`speed1.fiberby.dk:9213`.

![TCP stats over time (Reno).](results/20261021-152852/tcp_timeseries_reno.pdf)

![Congestion window, smoothed RTT, and retransmissions against goodput (Reno).](results/20261021-152852/tcp_scatter_reno.pdf)

![TCP stats over time (BBR).](results/20261021-152852/tcp_timeseries_bbr.pdf)

![Congestion window, smoothed RTT, and retransmissions against goodput (BBR).](results/20261021-152852/tcp_scatter_bbr.pdf)

**Goodput summary, all destinations (Mbit/s), from
`results/20261021-152852/goodput_summary.csv`:**

| host | port | algorithm | samples | min | median | mean | p95 |
|---|---:|---|---:|---:|---:|---:|---:|
| 123.53.44.221 | 5215 | bbr | 180 | 0.51 | 27.38 | 38.61 | 81.51 |
| 123.53.44.221 | 5215 | cubic | 180 | 0.63 | 83.17 | 80.31 | 88.10 |
| 123.53.44.221 | 5215 | reno | 180 | 1.22 | 89.11 | 85.88 | 91.96 |
| 156.146.40.65 | 5201 | bbr | 180 | 8.64 | 162.69 | 153.83 | 175.33 |
| 156.146.40.65 | 5201 | cubic | 180 | 3.77 | 163.04 | 135.89 | 175.85 |
| 156.146.40.65 | 5201 | reno | 180 | 12.79 | 161.70 | 152.46 | 174.58 |
| 189.25.101.151 | 30007 | bbr | 180 | 0.84 | 95.89 | 85.13 | 105.61 |
| 189.25.101.151 | 30007 | cubic | 180 | 0.19 | 2.44 | 35.68 | 106.07 |
| 189.25.101.151 | 30007 | reno | 180 | 0.01 | 51.98 | 42.63 | 96.87 |
| iperf.pendc.com | 5208 | bbr | 180 | 1.91 | 99.35 | 94.86 | 149.53 |
| iperf.pendc.com | 5208 | cubic | 180 | 0.51 | 94.50 | 76.56 | 141.76 |
| iperf.pendc.com | 5208 | reno | 180 | 0.35 | 20.51 | 51.16 | 131.28 |
| la.speedtest.clouvider.net | 5205 | bbr | 120\* | 35.39 | 129.51 | 140.17 | 216.92 |
| la.speedtest.clouvider.net | 5205 | cubic | 180 | 8.87 | 145.66 | 140.11 | 215.65 |
| la.speedtest.clouvider.net | 5205 | reno | 180 | 3.30 | 117.89 | 107.05 | 191.65 |
| ping-ams1.online.net | 5209 | bbr | 180 | 18.57 | 165.37 | 149.58 | 195.23 |
| ping-ams1.online.net | 5209 | cubic | 180 | 0.47 | 93.94 | 83.05 | 188.86 |
| ping-ams1.online.net | 5209 | reno | 180 | 21.23 | 121.19 | 122.44 | 171.63 |
| speed1.fiberby.dk | 9213 | bbr | 180 | 21.88 | 147.54 | 139.45 | 196.68 |
| speed1.fiberby.dk | 9213 | cubic | 180 | 10.97 | 41.30 | 54.80 | 160.03 |
| speed1.fiberby.dk | 9213 | reno | 180 | 3.67 | 22.28 | 47.42 | 198.34 |
| speedtest.wdc2.us.leaseweb.net | 5205 | bbr | 180 | 71.06 | 194.45 | 187.35 | 227.14 |
| speedtest.wdc2.us.leaseweb.net | 5205 | cubic | 180 | 31.22 | 191.05 | 175.85 | 224.78 |
| speedtest.wdc2.us.leaseweb.net | 5205 | reno | 180 | 2.54 | 182.14 | 128.50 | 223.89 |
| speedtest6.cwpanama.net | 5508 | bbr | 180 | 52.06 | 135.93 | 141.64 | 211.57 |
| speedtest6.cwpanama.net | 5508 | cubic | 180 | 33.78 | 162.37 | 163.47 | 224.56 |
| speedtest6.cwpanama.net | 5508 | reno | 180 | 0.89 | 98.88 | 76.96 | 138.59 |
| speedtestfl.telecom.mu | 5209 | bbr | 180 | 0.49 | 49.51 | 52.26 | 81.07 |
| speedtestfl.telecom.mu | 5209 | cubic | 180 | 0.28 | 1.41 | 15.48 | 80.71 |
| speedtestfl.telecom.mu | 5209 | reno | 180 | 0.22 | 6.96 | 20.07 | 79.06 |

\* 120 samples (2 of 3 repetitions) because the third repetition's run on
this destination/algorithm was skipped after 3 failed attempts (see above).

TODO (team): the actual discussion the assignment asks for —
- Identify, with these numbers and the plots, which network conditions
  favor each algorithm (look especially at `189.25.101.151`,
  `speed1.fiberby.dk`, and `speedtestfl.telecom.mu`, where bbr's median is
  far above cubic/reno's, versus `123.53.44.221`, where bbr loses) and
  relate it to cwnd, RTT, queueing, loss, and BDP.
- Discuss variability across the 3 repetitions per destination/algorithm
  (see per-repetition rows in `samples.csv`, not just the aggregated
  summary table) and the limitations of comparing algorithms over a
  real, changing public Internet path (cross traffic, route changes,
  server-side rate limits).
- Decide whether `123.53.44.221` (bbr's one clear loss) is worth a closer
  look in the writeup — check its RTT/retransmission plots for a hint
  (e.g., a short/low-BDP path where cubic's and reno's faster initial
  ramp matters more than bbr's loss tolerance).

## 3(b) Design a hand-written algorithm

TODO (team).

# Reproducing the results

**Host kernel for `results/20261021-152852`:**
`6.18.54.1-microsoft-standard-WSL2` (WSL2, Ubuntu 22.04 userspace), with
`reno`, `cubic`, and `bbr` all available
(`net.ipv4.tcp_available_congestion_control`). On this host `bbr` needed no
`sudo modprobe tcp_bbr` — it loads automatically once WSL itself is updated
past the kernel's 5.15 line (`wsl --update` from an elevated Windows
terminal, then `wsl --shutdown` to actually restart the VM onto the new
kernel). On a from-scratch Linux host, `sudo modprobe tcp_bbr` is the
expected step the README documents.

**Exact command line** (from `metadata.json` `arguments`):

```sh
.venv/bin/python run_experiments.py listed_iperf3_servers.csv \
    -n 10 --duration 60 --interval 1 --repetitions 3 \
    --algorithms cubic reno bbr
```

**Docker:** this run used `.venv/bin/python run_experiments.py` directly on
the host, not the `Dockerfile` in this repo. TODO before submission: run

```sh
docker build -t cs422-a2 .
docker run --rm --network host --cap-add NET_ADMIN \
    -v "$PWD/results":/app/results cs422-a2 \
    listed_iperf3_servers.csv -n 10 --duration 60 --interval 1 \
    --repetitions 3 --algorithms cubic reno bbr
```

on this same host (or any Linux/WSL2 host with `bbr` available) to confirm
the containerized pipeline reproduces equivalent results, since the
assignment spec wants the experiments executed through the Docker image,
and record that confirmation (or the container's own results directory)
here.

# Use of AI tools

TODO.
