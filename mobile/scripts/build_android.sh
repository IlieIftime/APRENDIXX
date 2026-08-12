#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE_ROOT="${ROOT}"
VENV_DIR="${HOME}/.venvs/aprendix-android"
if [[ ! -x "${VENV_DIR}/bin/buildozer" ]]; then
  echo "Executa primeiro mobile/scripts/setup_android_wsl.sh" >&2
  exit 2
fi
export PATH="${VENV_DIR}/bin:${PATH}"
export VIRTUAL_ENV="${VENV_DIR}"
if [[ "${ROOT}" == /mnt/* ]]; then
  STAGE="${HOME}/aprendix-android-build"
  mkdir -p "${STAGE}"
  rsync -a --delete --exclude='.venv*' --exclude='build' --exclude='dist' --exclude='.buildozer' "${ROOT}/" "${STAGE}/"
  ROOT="${STAGE}"
fi
export PIP_CONSTRAINT="${ROOT}/mobile/android/pip-constraints.txt"
cd "${ROOT}"
bash "${ROOT}/mobile/scripts/prepare_android_toolchain.sh" "${ROOT}"
PYTHONPATH="src:mobile" "${VENV_DIR}/bin/python" -m pytest tests/mobile \
  --confcutdir=tests/mobile -c /dev/null -p no:cacheprovider -q
"${VENV_DIR}/bin/buildozer" -v android debug
mkdir -p "${ROOT}/dist/mobile"
APK_SOURCE="$(find bin -maxdepth 1 -type f -name '*.apk' -printf '%T@ %p\n' | sort -nr | head -n1 | cut -d' ' -f2-)"
if [[ -z "${APK_SOURCE}" || ! -f "${APK_SOURCE}" ]]; then
  echo "O build terminou sem produzir um APK." >&2
  exit 3
fi
APK_NAME="Aprendix-1.0.0-android-arm64-debug.apk"
cp -f "${APK_SOURCE}" "${ROOT}/dist/mobile/${APK_NAME}"
unzip -tq "${ROOT}/dist/mobile/${APK_NAME}"
if [[ "${SOURCE_ROOT}" != "${ROOT}" ]]; then
  mkdir -p "${SOURCE_ROOT}/dist/mobile"
  cp -f "${ROOT}/dist/mobile/${APK_NAME}" "${SOURCE_ROOT}/dist/mobile/${APK_NAME}"
fi
sha256sum "${ROOT}/dist/mobile/${APK_NAME}"
