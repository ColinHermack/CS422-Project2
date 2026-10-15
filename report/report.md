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

Before submitting:
  - Replace RESULTS_DIR below with the committed results directory of the
    real Linux campaign (e.g. results/20261015-140000).
  - Replace "blob/main" in code links with "blob/<final commit hash>" so the
    line ranges stay correct, and re-check every line range.
  - Fill in every TODO.
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
The data is the cubic subset of the full campaign in `RESULTS_DIR`
(TODO: number of destinations, duration, interval, repetitions from
`metadata.json`).

## 2(a) Extracting TCP socket statistics

**Source socket.** Statistics come from the data socket, the TCP connection
that carries the test payload, never from the iperf3 control socket.
[`take_sample`](https://github.com/ColinHermack/CS422-Project2/blob/main/iperf3_client.py#L567-L617)
calls
[`read_tcp_info`](https://github.com/ColinHermack/CS422-Project2/blob/main/iperf3_client.py#L230-L240),
which runs `getsockopt(IPPROTO_TCP, TCP_INFO)` on the data socket and decodes
the returned `struct tcp_info` with
[`decode_tcp_info`](https://github.com/ColinHermack/CS422-Project2/blob/main/iperf3_client.py#L200-L227).

**Host kernel.** TODO from `RESULTS_DIR/metadata.json`: `host_kernel`
(`uname -r`), `host_platform`, and `kernel_tcp_settings`
(default and available congestion control, and the length of
`struct tcp_info` this kernel returns, `tcp_info_kernel_size_bytes`).

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

**Stored format.** `RESULTS_DIR/samples.csv` has one row per sample with the
run id, repetition, destination host, port and IP, requested and actually
used algorithm, `t`, `unix_time`, `goodput_bps`, `retrans_segs_interval`,
and every decoded `tcp_info` field. `metadata.json` maps every measured
column to its unit and records the host kernel, the struct format, the
selected destinations, and each run's outcome.

## 2(b) Visualization

The plots are generated automatically at the end of every campaign
([`plot_tcp_stats`](https://github.com/ColinHermack/CS422-Project2/blob/main/report.py#L615-L656)).
The representative destination, TODO host:port, is picked by
[`choose_representative_destination`](https://github.com/ColinHermack/CS422-Project2/blob/main/report.py#L391-L450):
among the destinations with data for every algorithm and no failed
repetition, the one whose mean goodput is the median, so the plots show a
typical path rather than the fastest or slowest. Each repetition is one
line (time series) or one color (scatter).

![TCP stats over time (CUBIC). From top: congestion window, smoothed RTT (dashed: minimum RTT), retransmitted segments per interval, goodput. Generated by `report.plot_time_series`.](RESULTS_DIR/tcp_timeseries_cubic.pdf)

Generated by
[`plot_time_series`](https://github.com/ColinHermack/CS422-Project2/blob/main/report.py#L510-L568).
cwnd and RTT are snapshots at each sample time, drawn as lines;
retransmissions and goodput describe a whole interval, drawn as steps.

![Congestion window, smoothed RTT, and retransmissions against goodput (CUBIC). Generated by `report.plot_scatter`.](RESULTS_DIR/tcp_scatter_cubic.pdf)

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

TODO (Part 3).

# Reproducing the results

TODO: host kernel, `sudo modprobe tcp_bbr`, Docker build and run commands
(see `README.md`), and the exact command line from `metadata.json`.

# Use of AI tools

TODO.
