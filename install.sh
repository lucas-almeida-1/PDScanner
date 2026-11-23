#!/usr/bin/env bash
# Bootstrap do PDScanner: instala git, python3 e pipx (se faltarem) e depois o próprio pdscanner.
# Uso: curl -fsSL https://raw.githubusercontent.com/lucas-almeida-1/PDScanner/main/install.sh | bash
set -euo pipefail

REPO="git+https://github.com/lucas-almeida-1/PDScanner.git"
SUDO=""
[ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1 && SUDO="sudo"

pm_install() {
  if command -v apt-get >/dev/null 2>&1; then $SUDO apt-get update && $SUDO apt-get install -y "$@"
  elif command -v dnf >/dev/null 2>&1; then $SUDO dnf install -y "$@"
  elif command -v yum >/dev/null 2>&1; then $SUDO yum install -y "$@"
  elif command -v pacman >/dev/null 2>&1; then $SUDO pacman -S --noconfirm "$@"
  elif command -v zypper >/dev/null 2>&1; then $SUDO zypper --non-interactive install "$@"
  elif command -v apk >/dev/null 2>&1; then $SUDO apk add "$@"
  elif command -v brew >/dev/null 2>&1; then brew install "$@"
  else echo "Gerenciador de pacotes não reconhecido. Instale manualmente: $*" >&2; exit 1
  fi
}

echo "==> Verificando git, python3 e pipx"
command -v git >/dev/null 2>&1 || { echo "Instalando git..."; pm_install git; }
command -v python3 >/dev/null 2>&1 || { echo "Instalando python3..."; pm_install python3; }
command -v pipx >/dev/null 2>&1 || { echo "Instalando pipx..."; pm_install pipx; }

echo "==> Instalando o PDScanner"
pipx install --force "$REPO"
pipx ensurepath >/dev/null 2>&1 || true

echo
echo "Pronto! Abra um novo terminal (ou rode: export PATH=\"\$HOME/.local/bin:\$PATH\") e execute 'pdscanner' na pasta do projeto."
