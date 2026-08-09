#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APK="${1:-${ROOT}/dist/mobile/Aprendix-1.0.0-android-arm64-release.apk}"
SDK="${HOME}/.buildozer/android/platform/android-sdk"
BUILD_TOOLS="$(find "${SDK}/build-tools" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -n 1)"

test -f "${APK}"
unzip -tq "${APK}"
"${BUILD_TOOLS}/apksigner" verify --verbose --print-certs "${APK}"
BADGING="$("${BUILD_TOOLS}/aapt" dump badging "${APK}")"
printf '%s\n' "${BADGING}"
grep -q "targetSdkVersion:'35'" <<< "${BADGING}"
"${BUILD_TOOLS}/aapt" dump xmltree "${APK}" AndroidManifest.xml > "${APK}.manifest-check"
if grep -qi 'debuggable.*0xffffffff' "${APK}.manifest-check"; then
  echo "O APK release não pode ser debuggable." >&2
  rm -f "${APK}.manifest-check"
  exit 7
fi
rm -f "${APK}.manifest-check"
echo "PERMISSIONS"
PERMISSIONS="$("${BUILD_TOOLS}/aapt" dump permissions "${APK}")"
printf '%s\n' "${PERMISSIONS}"
if grep -q 'android.permission.INTERNET' <<< "${PERMISSIONS}"; then
  echo "A permissão INTERNET é proibida no APK offline." >&2
  exit 4
fi
echo "ASSETS_AND_ABIS"
unzip -l "${APK}" | grep -E 'lib/.+\.so|knowledge-lite.db|seed-manifest.json' | tail -n 20
BUNDLE_DIRECTORY="$(mktemp -d)"
trap 'rm -rf "${BUNDLE_DIRECTORY}"' EXIT
unzip -Z1 "${APK}" > "${BUNDLE_DIRECTORY}/apk-files.txt"
grep -q 'lib/arm64-v8a/libpython' "${BUNDLE_DIRECTORY}/apk-files.txt"
if grep -Eq 'lib/(armeabi-v7a|x86|x86_64)/' "${BUNDLE_DIRECTORY}/apk-files.txt"; then
  echo "O APK arm64 contém bibliotecas de outra ABI." >&2
  exit 5
fi
unzip -p "${APK}" assets/private.tar > "${BUNDLE_DIRECTORY}/private.tar"
tar -tf "${BUNDLE_DIRECTORY}/private.tar" > "${BUNDLE_DIRECTORY}/private-files.txt"
grep -q 'mobile/assets/knowledge-lite.db' "${BUNDLE_DIRECTORY}/private-files.txt"
grep -q 'mobile/assets/seed-manifest.json' "${BUNDLE_DIRECTORY}/private-files.txt"
grep -q 'mobile/aprendix_mobile/contracts.pyc' "${BUNDLE_DIRECTORY}/private-files.txt"
if grep -Eq '(^|/)(scripts|tests)/|BASELINE|aprendix-phase|(^|/)cryptography/' "${BUNDLE_DIRECTORY}/private-files.txt"; then
  echo "O payload contém artefactos de desenvolvimento." >&2
  exit 6
fi
if grep -Eq 'lib/(arm64-v8a/)?lib(ssl|crypto)1[._]1' "${BUNDLE_DIRECTORY}/apk-files.txt"; then
  echo "O APK ainda contém OpenSSL 1.1 obsoleto." >&2
  exit 8
fi
APK_BYTES="$(stat -c '%s' "${APK}")"
if (( APK_BYTES > 262144000 )); then
  echo "O APK excede o orçamento de 250 MiB." >&2
  exit 9
fi
echo "APK_BYTES=${APK_BYTES}"
sha256sum "${APK}"
