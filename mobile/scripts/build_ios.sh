#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "A criação e assinatura IPA exige macOS com Xcode." >&2
  exit 2
fi
command -v xcodebuild >/dev/null
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"
python3 -m venv .venv-aprendix-ios
.venv-aprendix-ios/bin/python -m pip install --upgrade pip
.venv-aprendix-ios/bin/python -m pip install -e '.[dev,beeware,mobile-build]'
PYTHONPATH="src:mobile" .venv-aprendix-ios/bin/python -m pytest tests/mobile \
  --confcutdir=tests/mobile -c /dev/null -q
.venv-aprendix-ios/bin/briefcase create iOS
if ! gem list --installed xcodeproj >/dev/null 2>&1; then
  gem install --user-install xcodeproj
fi
USER_GEM_BIN="$(ruby -e 'puts Gem.user_dir')/bin"
export PATH="${USER_GEM_BIN}:${PATH}"
ruby mobile/scripts/integrate_ios_bridge.rb
.venv-aprendix-ios/bin/briefcase build iOS
echo "Projeto iOS criado e compilado."
echo "O iOS nao suporta uma imagem de instalador generica; abre o projeto Xcode em build/aprendix/iOS para assinar e instalar no dispositivo."
