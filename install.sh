#!/bin/bash

set -e  # Exit on any error
export DEBIAN_FRONTEND=noninteractive # Suppress interactive apt prompts

echo "🚀 Setting up development environment..."

# Update package manager
echo "📦 Updating package manager..."
sudo apt-get update || echo "⚠️  apt-get update returned an error (likely a broken repo), continuing..."

# Install Python (usually pre-installed in Codespaces, but ensure we have pip)
echo "🐍 Setting up Python..."
if ! command -v python3 &> /dev/null || ! command -v pip3 &> /dev/null; then
    sudo apt-get install -y python3 python3-pip python3-venv
else
    echo "Python3 and pip3 already installed, skipping apt-get install..."
fi

# Install Node.js and npm
echo "📗 Installing Node.js..."
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
    sudo apt-get install -y nodejs
else
    echo "Node.js already installed, skipping..."
fi

## Verify Node.js installation
echo "Node.js version: $(node --version)"
echo "npm version: $(npm --version)"

# Install yarn
echo "📦 Installing yarn..."
if ! command -v yarn &> /dev/null; then
    npm install -g yarn
    echo "yarn version: $(yarn --version)"
else
    echo "yarn already installed, skipping..."
fi

# Install Docker
echo "🐳 Installing Docker..."
## Docker is often pre-installed in Codespaces, but let's ensure it's properly set up
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    rm get-docker.sh
fi

# Add user to docker group (for Codespaces)
if ! groups "$USER" | grep -q '\bdocker\b'; then
    sudo usermod -aG docker "$USER"
fi

# Install uv (Python package manager)
echo "⚡ Installing uv..."
if ! command -v uv &> /dev/null && [ ! -f "$HOME/.local/bin/uv" ]; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
else
    echo "uv already installed, skipping..."
fi

## Add uv to PATH for current session - uv installs to ~/.local/bin
export PATH="$HOME/.local/bin:$PATH"

# Install prek
echo "🪝 Installing prek..."
if ! command -v prek &> /dev/null; then
    PREK_LATEST=$(curl -s https://api.github.com/repos/j178/prek/releases/latest | grep '"tag_name"' | cut -d'"' -f4)
    curl --proto '=https' --tlsv1.2 -LsSf "https://github.com/j178/prek/releases/download/${PREK_LATEST}/prek-installer.sh" | sh
else
    echo "prek already installed, skipping..."
fi

# Register apt sources (gh CLI + gcloud) — then single update + install
echo "📦 Registering apt sources..."
APT_SOURCES_CHANGED=0

if ! command -v gh &> /dev/null; then
    (type -p wget >/dev/null || sudo apt-get install -y wget)
    sudo mkdir -p -m 755 /etc/apt/keyrings
    out=$(mktemp)
    wget -nv -O "$out" https://cli.github.com/packages/githubcli-archive-keyring.gpg
    cat "$out" | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null
    rm -f "$out"
    sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
    sudo mkdir -p -m 755 /etc/apt/sources.list.d
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
    APT_SOURCES_CHANGED=1
fi

# Single apt-get update if any sources were added, then install everything
if [ "$APT_SOURCES_CHANGED" -eq 1 ]; then
    sudo apt-get update || echo "⚠️  apt-get update returned an error, continuing..."
fi

echo "🐙 Installing GitHub CLI..."
if ! command -v gh &> /dev/null; then
    sudo apt-get install -y gh
else
    echo "GitHub CLI already installed, skipping..."
fi

echo "🔍 Installing ripgrep (rg)..."
if ! command -v rg &> /dev/null; then
    sudo apt-get install -y ripgrep
else
    echo "ripgrep already installed, skipping..."
fi

# Install Playwright CLI
echo "🎭 Installing Playwright CLI..."
if command -v npm &> /dev/null; then
    if ! command -v playwright-cli &> /dev/null; then
        npm install -g @playwright/cli@latest
        # Install the browser using the new CLI's native command
        playwright-cli install-browser chromium --only-shell --with-deps
    else
        echo "Playwright CLI already installed, skipping npm install..."
    fi

else
    echo "⚠️  npm not available, skipping Playwright CLI"
fi

# Install ngrok
echo "🔌 Installing ngrok..."
if ! command -v ngrok &> /dev/null; then
    curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
      | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null \
      && echo "deb https://ngrok-agent.s3.amazonaws.com bookworm main" \
      | sudo tee /etc/apt/sources.list.d/ngrok.list \
      && sudo apt update \
      && sudo apt install -y ngrok
else
    echo "ngrok already installed, skipping..."
fi

# Configure ngrok authtoken
if command -v ngrok &> /dev/null; then
    if [ -n "$NGROK_AUTH_TOKEN" ]; then
        echo "🔑 Configuring ngrok authtoken..."
        ngrok config add-authtoken "$NGROK_AUTH_TOKEN"
    else
        echo "⚠️  NGROK_AUTH_TOKEN not set, skipping authtoken configuration"
    fi
fi

# Install Claude Code
echo "🤖 Installing Claude Code..."
if ! command -v claude &> /dev/null; then
    # Native installer is the recommended method (self-contained, no Node.js dependency)
    curl -fsSL https://claude.ai/install.sh | bash
else
    echo "Claude Code already installed, skipping..."
fi

# Install SpecStory CLI
echo "📖 Installing SpecStory CLI..."
if ! command -v specstory &> /dev/null; then
    wget -q https://github.com/specstoryai/getspecstory/releases/latest/download/SpecStoryCLI_Linux_x86_64.tar.gz
    tar -xzf SpecStoryCLI_Linux_x86_64.tar.gz
    sudo mv specstory /usr/local/bin/
    sudo chmod +x /usr/local/bin/specstory
    rm SpecStoryCLI_Linux_x86_64.tar.gz
else
    echo "SpecStory CLI already installed, skipping..."
fi

# Install npm global tools
echo "📦 Installing npm global tools..."
if command -v npm &> /dev/null; then
    NPM_PKGS=()
    command -v chub     &> /dev/null || NPM_PKGS+=("@aisuite/chub")
    command -v firecrawl &> /dev/null || NPM_PKGS+=("firecrawl-cli")

    if [ ${#NPM_PKGS[@]} -gt 0 ]; then
        npm install -g "${NPM_PKGS[@]}"
    else
        echo "All npm tools already installed, skipping..."
    fi
else
    echo "⚠️  npm not available, skipping npm tools"
fi

# Add uv to PATH permanently
touch ~/.bashrc
if ! grep -Fxq 'export PATH="$HOME/.local/bin:$PATH"' ~/.bashrc; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
fi

# Create useful aliases
echo "🔧 Setting up aliases..."
if ! grep -Fq '# dotfiles install aliases' ~/.bashrc; then
    cat >> ~/.bashrc << 'EOF'

# dotfiles install aliases
alias ll='ls -alF'
alias la='ls -A'
alias l='ls -CF'
alias python=python3
alias pip=pip3
alias dc='docker-compose'
alias dps='docker ps'
alias di='docker images'
alias cc='specstory run claude'
alias ccc='specstory run claude -c "claude --dangerously-skip-permissions"'
alias uvr='uv run'
alias uvi='uv init'
alias uva='uv add'
alias gs='git status'
alias ga='git add'
alias gc='git commit'
alias gp='git push'
alias gl='git pull'
alias search='rg'

EOF
else
    echo "Aliases already configured, skipping..."
fi

# Install some useful Python packages globally via uv
echo "📚 Installing useful Python packages..."
# Check if tools already exist before installing
if ! command -v ipython &> /dev/null; then
    ~/.local/bin/uv tool install ipython
else
    echo "ipython already installed, skipping..."
fi

if ! command -v jupyter &> /dev/null; then
    ~/.local/bin/uv tool install jupyter
else
    echo "jupyter already installed, skipping..."
fi

if ! command -v ruff &> /dev/null; then
    ~/.local/bin/uv tool install ruff
else
    echo "ruff already installed, skipping..."
fi

# Verify installations
echo "✅ Verifying installations..."
echo "Python: $(python3 --version)"
echo "Node.js: $(node --version)"
echo "npm: $(npm --version)"
echo "Docker: $(docker --version)"
echo "uv: $(~/.local/bin/uv --version)"

# Check ngrok
if command -v ngrok &> /dev/null; then
    echo "ngrok: $(ngrok version)"
else
    echo "⚠️  ngrok installation may need verification"
fi

# Check GitHub CLI
if command -v gh &> /dev/null; then
    echo "GitHub CLI: $(gh --version | head -1)"
else
    echo "⚠️  GitHub CLI installation may need verification"
fi

# Check ripgrep
if command -v rg &> /dev/null; then
    echo "ripgrep: $(rg --version | head -1)"
else
    echo "⚠️  ripgrep installation may need verification"
fi

# Check Context Hub
if command -v chub &> /dev/null; then
    echo "Context Hub: $(chub --version 2>/dev/null || echo 'installed')"
else
    echo "⚠️  Context Hub installation may need verification"
fi

# Check Playwright CLI
if command -v playwright-cli &> /dev/null; then
    echo "Playwright CLI: $(playwright-cli --version)"
else
    echo "⚠️  Playwright CLI installation may need verification"
fi

# Check Firecrawl CLI
if command -v firecrawl &> /dev/null; then
    echo "Firecrawl CLI: $(firecrawl --version 2>/dev/null || echo 'installed')"
else
    echo "⚠️  Firecrawl CLI installation may need verification"
fi

# Check if Claude Code installed successfully
if command -v claude &> /dev/null; then
    echo "Claude Code: $(claude --version)"
elif npm list -g @anthropic-ai/claude-cli &> /dev/null; then
    echo "Claude Code: installed via npm"
else
    echo "⚠️  Claude Code installation may need manual setup"
    echo "💡 You can install it later with: curl -fsSL https://claude.ai/install.sh | bash"
fi

# Check SpecStory CLI
if command -v specstory &> /dev/null; then
    echo "SpecStory CLI: $(specstory version 2>/dev/null || echo 'installed')"
else
    echo "⚠️  SpecStory CLI installation may need verification"
fi

echo "🎉 Development environment setup complete!"
echo "🔄 Please restart your terminal or run 'source ~/.bashrc' to load new PATH and aliases"
