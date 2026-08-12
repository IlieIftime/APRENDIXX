#!/usr/bin/env bash
set -euo pipefail

# Buildozer checks the configured tag as if it were a branch. Keep a local
# branch with that stable name so the checkout is reused instead of recloned.
ROOT="${1:?project root is required}"
P4A_DIR="${ROOT}/.buildozer/android/platform/python-for-android"
mkdir -p "$(dirname "${P4A_DIR}")"
if [[ ! -d "${P4A_DIR}/.git" ]]; then
  git clone --branch v2026.05.09 --single-branch \
    https://github.com/kivy/python-for-android.git "${P4A_DIR}"
fi
git -C "${P4A_DIR}" checkout -B v2026.05.09 58d21141f17c889bf8585f5665921d72028f8831

# pip 26 leaves mixed bootstrap files in p4a's generated Python 3.11 venv.
# Patch only the disposable pinned toolchain checkout and verify the result.
BUILD_PY="${P4A_DIR}/pythonforandroid/build.py"
if grep -q 'pip install -U pip"' "${BUILD_PY}"; then
  sed -i "s/pip install -U pip\"/pip install -U 'pip<26'\"/" "${BUILD_PY}"
fi
if grep -q "shprint(host_python, '-m', 'venv', 'venv')" "${BUILD_PY}"; then
  sed -i "s/shprint(host_python, '-m', 'venv', 'venv')/shprint(host_python, '-m', 'venv', '--clear', 'venv')/" "${BUILD_PY}"
fi
grep -q "pip install -U 'pip<26'" "${BUILD_PY}" || {
  echo "Não foi possível aplicar o pin compatível de pip ao toolchain." >&2
  exit 4
}
grep -q "venv', '--clear', 'venv'" "${BUILD_PY}" || {
  echo "Não foi possível tornar atómica a venv temporária Android." >&2
  exit 5
}
