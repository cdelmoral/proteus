#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '\n==> %s\n' "$1"
}

require_ubuntu() {
  if [[ ! -r /etc/os-release ]]; then
    printf 'Cannot read /etc/os-release\n' >&2
    exit 1
  fi

  . /etc/os-release

  if [[ "${ID:-}" != "ubuntu" ]]; then
    printf 'This bootstrap expects Ubuntu, found %s\n' "${ID:-unknown}" >&2
    exit 1
  fi
}

install_base_packages() {
  log "Installing base packages"
  sudo apt-get update
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    ca-certificates \
    curl \
    fzf \
    git \
    gnupg \
    jq \
    neovim \
    pipx \
    python3 \
    python3-venv \
    ripgrep \
    unzip \
    wget \
    build-essential
}

configure_apt_repositories() {
  log "Configuring Docker and GitHub CLI apt repositories"
  . /etc/os-release

  sudo install -m 0755 -d /etc/apt/keyrings /usr/share/keyrings

  if [[ ! -f /etc/apt/keyrings/docker.asc ]]; then
    curl -fsSL "https://download.docker.com/linux/ubuntu/gpg" | sudo tee /etc/apt/keyrings/docker.asc >/dev/null
    sudo chmod a+r /etc/apt/keyrings/docker.asc
  fi

  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' \
    "$(dpkg --print-architecture)" \
    "${VERSION_CODENAME}" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

  if [[ ! -f /usr/share/keyrings/githubcli-archive-keyring.gpg ]]; then
    curl -fsSL "https://cli.github.com/packages/githubcli-archive-keyring.gpg" | sudo tee /usr/share/keyrings/githubcli-archive-keyring.gpg >/dev/null
    sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
  fi

  printf 'deb [arch=%s signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\n' \
    "$(dpkg --print-architecture)" | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
}

install_docker_and_gh() {
  log "Installing Docker Engine, Compose plugin, and GitHub CLI"
  sudo apt-get update
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    containerd.io \
    docker-buildx-plugin \
    docker-ce \
    docker-ce-cli \
    docker-compose-plugin \
    gh

  sudo usermod -aG docker "$USER"
  sudo systemctl enable --now docker
}

install_mise() {
  log "Installing mise"
  if [[ ! -x "$HOME/.local/bin/mise" ]]; then
    curl -fsSL "https://mise.run" | sh
  fi

  mkdir -p "$HOME/.config/mise" "$HOME/projects"

  if ! grep -Fq 'mise activate bash' "$HOME/.bashrc" 2>/dev/null; then
    {
      printf '\n# mise\n'
      printf 'export PATH="$HOME/.local/bin:$PATH"\n'
      printf 'eval "$(mise activate bash)"\n'
    } >>"$HOME/.bashrc"
  fi

  export PATH="$HOME/.local/bin:$PATH"
  eval "$(mise activate bash)"
}

install_node_and_pnpm() {
  log "Installing Node LTS through mise and pnpm through Corepack"
  export MISE_YES=1
  export MISE_NODE_COREPACK=1
  mise use --global node@lts

  if ! mise exec node@lts -- corepack --version >/dev/null 2>&1; then
    mise exec node@lts -- npm install --global corepack@latest
    mise reshim node
  fi

  mkdir -p "$HOME/.local/bin"
  mise exec node@lts -- corepack enable --install-directory "$HOME/.local/bin"
  mise exec node@lts -- corepack prepare pnpm@latest --activate
}

finish() {
  log "Bootstrap complete"
  printf 'Open a new shell before running Docker so docker group membership is active.\n'
  printf 'Next manual steps are documented in vm/README.md.\n'
}

require_ubuntu
install_base_packages
configure_apt_repositories
install_docker_and_gh
install_mise
install_node_and_pnpm
pipx ensurepath >/dev/null
finish
