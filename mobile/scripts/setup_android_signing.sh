#!/usr/bin/env bash
set -euo pipefail

# The signing identity is intentionally kept outside the repository. Losing it
# makes in-place Android upgrades impossible, so back up this directory safely.
SIGN_DIR="${APRENDIX_SIGNING_DIR:-${HOME}/.config/aprendix/signing}"
ENV_FILE="${SIGN_DIR}/android-release.env"
KEYSTORE="${SIGN_DIR}/aprendix-release.jks"
mkdir -p "${SIGN_DIR}"
chmod 700 "${SIGN_DIR}"
if [[ -f "${ENV_FILE}" && -f "${KEYSTORE}" ]]; then
  echo "A identidade de assinatura existente será reutilizada em ${SIGN_DIR}."
  exit 0
fi
command -v keytool >/dev/null || { echo "keytool/JDK em falta." >&2; exit 2; }
PASSWORD="$(openssl rand -hex 24)"
keytool -genkeypair -noprompt -keystore "${KEYSTORE}" -storepass "${PASSWORD}" \
  -keypass "${PASSWORD}" -alias aprendix -keyalg RSA -keysize 4096 -validity 10000 \
  -dname "CN=Aprendix Local Release, OU=Offline Learning, O=Aprendix, C=PT"
{
  printf 'export P4A_RELEASE_KEYSTORE=%q\n' "${KEYSTORE}"
  printf 'export P4A_RELEASE_KEYALIAS=%q\n' "aprendix"
  printf 'export P4A_RELEASE_KEYSTORE_PASSWD=%q\n' "${PASSWORD}"
  printf 'export P4A_RELEASE_KEYALIAS_PASSWD=%q\n' "${PASSWORD}"
} > "${ENV_FILE}"
chmod 600 "${ENV_FILE}" "${KEYSTORE}"
echo "Identidade criada fora do repositório em ${SIGN_DIR}. Faz uma cópia de segurança privada."
