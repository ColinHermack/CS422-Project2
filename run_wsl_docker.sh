#!/usr/bin/env bash
set -Eeuo pipefail

# Automated WSL2/Linux launcher for the complete Docker experiment pipeline.
# It loads the host's BBR module, builds the Ubuntu 24.04 image, verifies that
# the container can select cubic/reno/bbr, and then runs the campaign. Any
# arguments are passed to run_experiments.py; no arguments use Docker's full
# default campaign.

PROJECT_DIRECTORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="${CS422_DOCKER_IMAGE:-cs422-a2}"
RESULTS_DIRECTORY="${PROJECT_DIRECTORY}/results"
REQUESTED_ALGORITHMS=(cubic reno bbr)
ENVIRONMENT_CHECK_ONLY=false

# Mirror argparse's `--algorithms NAME [NAME ...]` option so a smaller custom
# run does not require BBR unnecessarily. With no option, use the assignment's
# complete three-algorithm default.
arguments=("$@")
for argument in "${arguments[@]}"; do
    if [[ "${argument}" == "--check-environment" ]]; then
        ENVIRONMENT_CHECK_ONLY=true
        break
    fi
done

for ((index = 0; index < ${#arguments[@]}; index++)); do
    if [[ "${arguments[index]}" == "--algorithms" ]]; then
        REQUESTED_ALGORITHMS=()
        for ((index += 1; index < ${#arguments[@]}; index++)); do
            if [[ "${arguments[index]}" == --* ]]; then
                break
            fi
            REQUESTED_ALGORITHMS+=("${arguments[index]}")
        done
        break
    fi
done

if [[ ${#REQUESTED_ALGORITHMS[@]} -eq 0 ]]; then
    echo "error: --algorithms requires at least one algorithm name" >&2
    exit 2
fi

bbr_required=false
for algorithm in "${REQUESTED_ALGORITHMS[@]}"; do
    if [[ "${algorithm}" == "bbr" ]]; then
        bbr_required=true
        break
    fi
done

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "error: this experiment requires Linux or WSL2" >&2
    exit 1
fi

if grep -qi microsoft /proc/sys/kernel/osrelease; then
    echo "Detected WSL2 kernel: $(uname -r)"
else
    echo "Detected Linux kernel: $(uname -r)"
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "error: Docker is not installed or not on PATH" >&2
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    echo "error: Docker is not running or this user cannot access it" >&2
    exit 1
fi

docker_operating_system="$(docker info --format '{{.OperatingSystem}}')"
if [[ "${docker_operating_system}" == *"Docker Desktop"* ]]; then
    if [[ "${ENVIRONMENT_CHECK_ONLY}" == true ]]; then
        echo "warning: Docker Desktop was detected. Environment checking is safe," >&2
        echo "but do not collect assignment measurements with this runtime." >&2
    else
        echo "error: Docker Desktop was detected." >&2
        echo "Docker Desktop proxies outbound TCP even with --network host, so" >&2
        echo "TCP_INFO describes the local proxy rather than the public server." >&2
        echo "Install Docker Engine directly inside this WSL2 distribution (or use" >&2
        echo "native Linux), confirm 'docker info' no longer reports Docker Desktop," >&2
        echo "and rerun this launcher. Refusing to create invalid assignment data." >&2
        exit 1
    fi
fi

# Containers use the host kernel and cannot load a missing host module. WSL2
# ships tcp_bbr as a module, so load it before building/running the image.
if [[ "${bbr_required}" == true ]] \
        && ! grep -qw bbr /proc/sys/net/ipv4/tcp_available_congestion_control; then
    if ! command -v modprobe >/dev/null 2>&1 || ! modinfo tcp_bbr >/dev/null 2>&1; then
        echo "error: this kernel does not provide tcp_bbr" >&2
        echo "On WSL2, run 'wsl --update' and 'wsl --shutdown' in Windows, then retry." >&2
        exit 1
    fi

    echo "Loading the host tcp_bbr module (sudo may ask for your password)..."
    if [[ "$(id -u)" -eq 0 ]]; then
        modprobe tcp_bbr
    else
        sudo modprobe tcp_bbr
    fi
fi

if [[ "${bbr_required}" == true ]] \
        && ! grep -qw bbr /proc/sys/net/ipv4/tcp_available_congestion_control; then
    echo "error: tcp_bbr was loaded but BBR is still unavailable" >&2
    exit 1
fi

mkdir -p "${RESULTS_DIRECTORY}"

echo "Building ${IMAGE_NAME} from ${PROJECT_DIRECTORY}/Dockerfile..."
docker build --tag "${IMAGE_NAME}" "${PROJECT_DIRECTORY}"

echo "Checking Python dependencies and congestion-control algorithms in the container..."
docker run --rm \
    --network host \
    --cap-add NET_ADMIN \
    "${IMAGE_NAME}" \
    --check-environment --algorithms "${REQUESTED_ALGORITHMS[@]}"

echo "Starting the experiment pipeline..."
docker run --rm \
    --network host \
    --cap-add NET_ADMIN \
    --volume "${RESULTS_DIRECTORY}:/app/results" \
    "${IMAGE_NAME}" "$@"
