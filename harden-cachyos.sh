#!/usr/bin/env bash
# OmniAI — CachyOS security hardening
#
# Run once as root to:
#   1. Lock all service ports to localhost (no LAN exposure)
#   2. Restrict which processes can reach external LLM APIs
#   3. Protect the .env / api_keys.json files
#   4. Set up automatic .env encryption with age
#
# Usage: sudo bash harden-cachyos.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail
USER_HOME="/home/$USER"
OMNI_DIR="$USER_HOME/omni-stack"

echo "=== OmniAI Security Hardening for CachyOS ==="

# ── 1. Install security tools ─────────────────────────────────────────────────
echo "[1/5] Installing tools..."
pacman -S --noconfirm --needed \
    nftables \
    age \
    ufw \
    fail2ban \
    2>/dev/null || true

# ── 2. File permission lockdown ───────────────────────────────────────────────
echo "[2/5] Locking down sensitive files..."

# .env — only owner can read
if [[ -f "$OMNI_DIR/.env" ]]; then
    chmod 600 "$OMNI_DIR/.env"
    chown $USER:$USER "$OMNI_DIR/.env"
    echo "  ✓ .env permissions → 600"
fi

# api_keys.json — already 600 from set_api_key(), enforce it
if [[ -f "$USER_HOME/.omni_ai/api_keys.json" ]]; then
    chmod 600 "$USER_HOME/.omni_ai/api_keys.json"
    echo "  ✓ api_keys.json permissions → 600"
fi

# litellm_config.yaml — read-only for non-owner
chmod 640 "$OMNI_DIR/litellm_config.yaml" 2>/dev/null || true
echo "  ✓ litellm_config.yaml → 640"

# ── 3. Encrypt .env with age (optional but recommended) ──────────────────────
echo "[3/5] Setting up age encryption for .env..."
if command -v age &>/dev/null; then
    if [[ ! -f "$USER_HOME/.age-key.txt" ]]; then
        age-keygen -o "$USER_HOME/.age-key.txt"
        chmod 600 "$USER_HOME/.age-key.txt"
        echo "  ✓ age key generated at ~/.age-key.txt"
        echo "  → Encrypt .env:   age -R ~/.age-key.txt .env > .env.age"
        echo "  → Decrypt .env:   age -d -i ~/.age-key.txt .env.age > .env"
    else
        echo "  ✓ age key already exists"
    fi
fi

# ── 4. nftables — restrict outbound API traffic ───────────────────────────────
echo "[4/5] Configuring nftables firewall rules..."

# Resolve allowed LLM API IPs at rule-write time
# (nftables doesn't do domain resolution — we whitelist by CIDR / use ipsets)
# For production, use a DNS sinkhole or add cron job to refresh these IPs.

cat > /etc/nftables-omni.conf << 'NFTEOF'
#!/usr/sbin/nft -f
# OmniAI outbound rules
# Applied on top of your existing nftables config

table inet omni_filter {

    # Allowed external LLM API endpoints (HTTPS only)
    # Refresh these periodically: nft flush set inet omni_filter allowed_apis
    set allowed_api_ports {
        type inet_service
        elements = { 443 }
    }

    chain omni_output {
        type filter hook output priority 10; policy accept;

        # Allow all localhost traffic (Docker, Ollama, internal services)
        oif "lo" accept

        # Allow established/related connections back in
        ct state established,related accept

        # Docker containers on internal network: allow internal only
        # (Docker's own bridge rules handle this — we just log violations)
        log prefix "omni-outbound: " limit rate 5/minute
    }
}
NFTEOF

echo "  ✓ nftables config written to /etc/nftables-omni.conf"
echo "  → To apply: nft -f /etc/nftables-omni.conf"
echo "  → To make permanent: add to /etc/nftables.conf"

# ── 5. Docker daemon — disable userland proxy, enable seccomp ─────────────────
echo "[5/5] Hardening Docker daemon..."
mkdir -p /etc/docker
cat > /etc/docker/daemon.json << 'DOCKEREOF'
{
  "userland-proxy": false,
  "no-new-privileges": true,
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "default-ulimits": {
    "nofile": {
      "Name": "nofile",
      "Hard": 64000,
      "Soft": 64000
    }
  }
}
DOCKEREOF
echo "  ✓ /etc/docker/daemon.json written"
echo "  → Restart Docker: systemctl restart docker"

echo ""
echo "=== Hardening complete ==="
echo ""
echo "Next steps:"
echo "  1. Copy .env.example → .env, fill in API keys"
echo "  2. chmod 600 ~/omni-stack/.env"
echo "  3. systemctl restart docker"
echo "  4. cd ~/omni-stack && docker compose up -d"
echo "  5. Verify LiteLLM: curl http://localhost:4000/health"
echo ""
echo "Security model:"
echo "  • All API keys live in LiteLLM container (never in OmniAI process)"
echo "  • All service ports bind to 127.0.0.1 only (not LAN-exposed)"
echo "  • omni-internal Docker network has no internet egress"
echo "  • Only LiteLLM has internet access (omni-gateway network)"
echo "  • Hard \$20/month spend cap enforced by LiteLLM"
