#!/usr/bin/env bash
set -euo pipefail

STAGE="${HOME}/aprendix-android-build"
VENV_DIR="${HOME}/.venvs/aprendix-android"
export PATH="${VENV_DIR}/bin:${PATH}"
export VIRTUAL_ENV="${VENV_DIR}"
cd "${STAGE}"
exec "${VENV_DIR}/bin/buildozer" -v android debug
