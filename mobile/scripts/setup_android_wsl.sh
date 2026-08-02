#!/usr/bin/env bash
set -euo pipefail

if ! grep -qi microsoft /proc/version; then
  echo "Este instalador foi preparado para Ubuntu/WSL2." >&2
  exit 2
fi
sudo apt-get update
sudo apt-get install -y git zip unzip openjdk-17-jdk python3-venv python3-pip \
  build-essential autoconf automake autopoint gettext libtool pkg-config cmake ninja-build \
  libffi-dev libssl-dev zlib1g-dev libncurses5-dev libncursesw5-dev \
  rustc cargo rsync

VENV_DIR="${HOME}/.venvs/aprendix-android"
python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip wheel setuptools
"${VENV_DIR}/bin/python" -m pip install "buildozer>=1.5,<2" "cython<3.1" pytest
echo "Toolchain Python pronta em ${VENV_DIR}. O primeiro build descarrega SDK/NDK no WSL."
