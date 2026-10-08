# Plan: Part 1 iperf3 client experiment function

## Context

Part 1(a) needs a from-scratch Python TCP client that completes a real test against a public iperf3 server: control connection, JSON parameter exchange, data connection, timed send, proper iperf3 termination. Part 1(c) needs goodput sampled from the data socket's `TCP_INFO` (`tcpi_bytes_acked`) during the send. Parts 2 and 3 reuse the same samples (cwnd, RTT, retransmits) and congestion control selection, so the function should capture them now.

Scope: one function, `run_experiment(...)`, plus its small helpers. Out of scope for now: server-list parsing, random destination selection and replacement retries (1b), CSV/JSON output, plots, entry point.

## File

`iperf3_client.py` (new, repo root). Stdlib only: `socket`, `struct`, `json`, `select`, `time`, `random`, `string`.

## Documentation and readability

Follows **Code style** in `CLAUDE.md`. The user is orally examined on every line, so readability wins over brevity.

- **Module docstring:** what the file does, the full iperf3 message sequence (steps 1-10 below) as a numbered list, and a note that it is Linux-only (`TCP_INFO`, `TCP_CONGESTION`).
- **Function docstrings:** each function (`run_experiment`, `decode_tcp_info`, `recv_exact`, `read_state`, `send_json`, `recv_json`, and the steps below) documents purpose, args with units (seconds, bytes, bits/s), return value, and `IperfError` cases.
- **Split `run_experiment` into one function per protocol phase** so each one is short and maps to one step of the sequence: `connect_control`, `exchange_params`, `open_data_stream`, `wait_for_test_running`, `send_and_sample`, `exchange_results`, `finish_test`. `run_experiment` then reads like the protocol outline.
- **Named constants with comments:** every state code (with its meaning and `iperf_api.h` as the source), `COOKIE_SIZE = 37`, `BLOCK_SIZE = 131072`, default timeouts, and the `TCP_INFO` struct format.
- **`TCP_INFO` format:** build the format string from a list of `(field_name, struct_code)` pairs, one per line with a comment giving the unit, rather than one opaque string. Field names come from the same list, so the decoder and its documentation can't drift apart.
- **Why comments:** the cookie (the server uses it to match the data connection to the control connection), setting `TCP_CONGESTION` before `connect` (the algorithm must be chosen before the handshake), non-blocking send with `select` (keeps samples on schedule and watches for early server exit), the goodput formula with units, and each required key in the results JSON (the server rejects results without them).
- **Error paths:** each `raise IperfError` has a comment saying which failure it represents (timeout, busy server, rejected params, premature termination) and what the caller should do.
- **No dense code:** explicit loops and plain `if` blocks, with no nested comprehensions or chained one-liners.

## iperf3 protocol (sender mode, 1 TCP stream)

Taken from iperf3 source (`src/iperf_api.h`, `iperf_client_api.c`, `iperf_api.c`). State byte is a signed char on the control socket.

| Const | Value |
|---|---|
| TEST_START | 1 |
| TEST_RUNNING | 2 |
| TEST_END | 4 |
| PARAM_EXCHANGE | 9 |
| CREATE_STREAMS | 10 |
| SERVER_TERMINATE | 11 |
| CLIENT_TERMINATE | 12 |
| EXCHANGE_RESULTS | 13 |
| DISPLAY_RESULTS | 14 |
| IPERF_DONE | 16 |
| ACCESS_DENIED | -1 (server busy) |
| SERVER_ERROR | -2 (followed by two 4-byte ints: i_errno, errno) |

Sequence:

1. Connect control socket to `host:port`. Send 37-byte cookie (36 random chars from `a-z2-7` + `\0`).
2. Read state: expect `PARAM_EXCHANGE`.
3. Send params as 4-byte big-endian length + JSON:
   `{"tcp": true, "omit": 0, "time": duration, "num": 0, "blockcount": 0, "parallel": 1, "len": 131072, "pacing_timer": 1000, "client_version": "3.16"}`
4. Read state: expect `CREATE_STREAMS`.
5. Create data socket, `setsockopt(IPPROTO_TCP, TCP_CONGESTION, algo)` **before connect**, connect to same `host:port`, send the same cookie. Read back `TCP_CONGESTION` and record actual algorithm.
6. Read states until `TEST_RUNNING` (server sends `TEST_START` then `TEST_RUNNING`).
7. Send loop for `duration` seconds (below), sampling `TCP_INFO` every `interval`.
8. Send `TEST_END` on control.
9. Read `EXCHANGE_RESULTS`. Send client results (length + JSON), read server results (length + JSON). Server requires these keys or it errors:
   `{"cpu_util_total": 0, "cpu_util_user": 0, "cpu_util_system": 0, "sender_has_retransmits": 1, "streams": [{"id": 1, "bytes": bytes_sent, "retransmits": total_retrans, "jitter": 0, "errors": 0, "packets": 0, "start_time": 0, "end_time": elapsed}]}`
10. Read `DISPLAY_RESULTS`, send `IPERF_DONE`, close both sockets.

## Send loop + sampling

Data socket set non-blocking after the cookie is sent. Loop until `end = t0 + duration`:

```
ready_r, ready_w = select([ctrl], [data], [], min(next_sample, end) - now)
if ctrl readable: any byte or EOF mid-test = server ended early -> raise
if data writable: n = data.send(buf); bytes_sent += n   (partial sends fine; payload is arbitrary)
if now >= next_sample: take sample; next_sample += interval
```

`select` with a timeout keeps samples on schedule even when the send buffer is full, and watches the control socket for premature termination at the same time. Take a baseline sample at `t0` and a final sample at `end` before `TEST_END`.

Sample: `t` (s since t0, `time.monotonic()` taken right after `getsockopt`), all decoded `tcp_info` fields, and
`goodput_bps = (bytes_acked - prev_bytes_acked) * 8 / (t - prev_t)`.

## TCP_INFO decoding

`decode_tcp_info(raw: bytes) -> dict` using one `struct` format string for Linux `struct tcp_info` (`include/uapi/linux/tcp.h`), native byte order, no padding (`=`):

- `8B`: state, ca_state, retransmits, probes, backoff, options, wscale bits, app_limited bits
- `24I`: rto, ato, snd_mss, rcv_mss, unacked, sacked, lost, retrans, fackets, last_data_sent, last_ack_sent, last_data_recv, last_ack_recv, pmtu, rcv_ssthresh, rtt, rttvar, snd_ssthresh, snd_cwnd, advmss, reordering, rcv_rtt, rcv_space, total_retrans
- `4Q`: pacing_rate, max_pacing_rate, bytes_acked, bytes_received
- `6I`: segs_out, segs_in, notsent_bytes, min_rtt, data_segs_in, data_segs_out
- `Q`: delivery_rate
- ... stop at the fields we need (through `delivery_rate`, 168 bytes, Linux 4.9+).

Call `getsockopt(IPPROTO_TCP, TCP_INFO, 256)` and decode the first `struct.calcsize(FMT)` bytes; raise if the kernel returned fewer. Units: `rtt`/`rttvar`/`min_rtt` in microseconds, `snd_cwnd` in segments, rates in bytes/s.

## Function signature

```python
def run_experiment(host, port, duration=60, interval=1.0, congestion=None,
                   timeout=10) -> dict
```

Returns `{"host", "port", "congestion" (actual), "bytes_sent", "samples": [...], "server_results": {...}}`.

## Error handling

`class IperfError(Exception)`: single exception type the future retry loop (1b) catches, logs, and moves to a replacement server.

| Failure | Detection |
|---|---|
| Unresponsive server | `settimeout(timeout)` on connect and every control read; `socket.timeout` |
| Busy / overloaded | `ACCESS_DENIED` state |
| Rejected params | `SERVER_ERROR` (log i_errno/errno) or unexpected state |
| Premature termination | `recv` returns `b''`, control readable mid-test, `ConnectionError` on send |

All wrapped as `IperfError(reason)`. `finally`: best-effort send `CLIENT_TERMINATE` if the test started but did not finish (frees the shared server sooner), then close both sockets.

Helpers: `recv_exact(sock, n)` (loop until n bytes, EOF -> IperfError), `read_state(sock)`, `send_json(sock, obj)`, `recv_json(sock)`.

## Verification

1. Self-check in `if __name__ == "__main__":` block: `struct.pack` a known tcp_info buffer, assert `decode_tcp_info` returns the right `snd_cwnd`, `rtt`, `bytes_acked`; assert goodput math on two fake samples.
2. Live run on Linux (macOS lacks `TCP_INFO`/`TCP_CONGESTION`), e.g. via Docker:
   `docker run --rm -v "$PWD":/app -w /app ubuntu:24.04 sh -c "apt-get update -qq && apt-get install -y -qq python3 && python3 -c 'import iperf3_client as c, json; print(json.dumps(c.run_experiment(\"<host>\", 5201, duration=10, congestion=\"cubic\"), indent=1)[:2000])'"`
   Check: returns without error, ~10 samples, goodput plausible, `server_results` bytes roughly equal `bytes_sent`, `congestion == "cubic"`.
3. Point at a dead host / closed port and a busy server: confirm `IperfError` with a clear reason within `timeout` seconds.
