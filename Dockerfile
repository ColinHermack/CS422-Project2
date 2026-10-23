# Container for the full measurement pipeline (run_experiments.py):
# destination selection, iperf3 tests with each congestion control
# algorithm, raw CSV/JSON output, summary tables, and PDF plots.
#
# The container standardizes only user space (Python, matplotlib, scripts).
# It shares the host's Linux kernel, so TCP behavior, the tcp_info layout,
# and the available congestion control algorithms all come from the host.
# metadata.json records the host kernel version (platform.release() inside
# a container reports the host kernel).
#
# Build and run with native Docker Engine on Linux (or directly inside the
# WSL2 distribution), not Docker Desktop on any operating system. Docker
# Desktop's TCP proxy makes TCP_INFO describe the hop to the proxy:
#
#   ./run_wsl_docker.sh
#
#   --network host     with native Docker Engine, use the host network stack
#                      directly so sockets see the host path and TCP settings.
#   --cap-add NET_ADMIN  setsockopt(TCP_CONGESTION) needs this capability for
#                      algorithms not in tcp_allowed_congestion_control
#                      (usually bbr); Docker does not grant it by default.
#   -v ...results      keep the results after the container exits.
#
# run_wsl_docker.sh performs the module check, image build, container
# preflight, and docker run command above automatically.
#
# Arguments after the image name replace the default CMD below, e.g.
#   docker run ... cs422-a2 listed_iperf3_servers.csv -n 2 --duration 5

FROM ubuntu:24.04

# Ubuntu's own matplotlib package instead of pip: Ubuntu 24.04 blocks
# system-wide pip installs (PEP 668), and the plots only use basic
# matplotlib features, so the distribution version (older than the
# requirements.txt pin used for local development) works. Removing the apt
# lists afterwards keeps the image smaller.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3 python3-matplotlib \
    && rm -rf /var/lib/apt/lists/*

# Print output immediately instead of buffering it, so progress and the
# summary table show up in `docker run` output (and `docker logs`) as they
# happen.
ENV PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app
COPY *.py requirements.txt listed_iperf3_servers.csv ./

# The image runs the pipeline; CMD holds the default campaign (the options
# in README.md), which any arguments given to `docker run` replace.
ENTRYPOINT ["python3", "run_experiments.py"]
CMD ["listed_iperf3_servers.csv", "-n", "10", "--duration", "60", "--interval", "1", \
     "--repetitions", "3", "--algorithms", "cubic", "reno", "bbr"]
