#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="${HOME}/.venvs/aprendix-android"
SIGN_DIR="${APRENDIX_SIGNING_DIR:-${HOME}/.config/aprendix/signing}"
bash "${SOURCE_ROOT}/mobile/scripts/setup_android_signing.sh"
# shellcheck disable=SC1090
source "${SIGN_DIR}/android-release.env"
export P4A_RELEASE_KEYSTORE P4A_RELEASE_KEYALIAS P4A_RELEASE_KEYSTORE_PASSWD P4A_RELEASE_KEYALIAS_PASSWD
export PATH="${VENV_DIR}/bin:${PATH}" VIRTUAL_ENV="${VENV_DIR}"
[[ -x "${VENV_DIR}/bin/buildozer" ]] || { echo "Executa setup_android_wsl.sh primeiro." >&2; exit 2; }
ROOT="${SOURCE_ROOT}"
if [[ "${ROOT}" == /mnt/* ]]; then
  ROOT="${HOME}/aprendix-android-build"
  mkdir -p "${ROOT}"
  rsync -a --delete --exclude='.venv*' --exclude='build' --exclude='dist' --exclude='.buildozer' "${SOURCE_ROOT}/" "${ROOT}/"
fi
export PIP_CONSTRAINT="${ROOT}/mobile/android/pip-constraints.txt"
cd "${ROOT}"
bash "${ROOT}/mobile/scripts/prepare_android_toolchain.sh" "${ROOT}"
PYTHONPATH="src:mobile" "${VENV_DIR}/bin/python" -m pytest tests/mobile \
  --confcutdir=tests/mobile -c /dev/null -p no:cacheprovider -q
"${VENV_DIR}/bin/buildozer" -v android release
APK_SOURCE="$(find bin -maxdepth 1 -type f -name '*release*.apk' -printf '%T@ %p\n' | sort -nr | head -n1 | cut -d' ' -f2-)"
[[ -n "${APK_SOURCE}" && -f "${APK_SOURCE}" ]] || { echo "Build sem APK release." >&2; exit 3; }
APK_NAME="Aprendix-1.0.0-android-arm64-release.apk"
mkdir -p "${ROOT}/dist/mobile" "${SOURCE_ROOT}/dist/mobile"
cp -f "${APK_SOURCE}" "${ROOT}/dist/mobile/${APK_NAME}"
cp -f "${ROOT}/dist/mobile/${APK_NAME}" "${SOURCE_ROOT}/dist/mobile/${APK_NAME}"
unzip -tq "${SOURCE_ROOT}/dist/mobile/${APK_NAME}"
sha256sum "${SOURCE_ROOT}/dist/mobile/${APK_NAME}"
