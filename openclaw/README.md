# OpenClaw + WhatsApp (local setup)

OpenClaw links to **WhatsApp Web** and stores **all session credentials under your home directory**, not in this repo.

- **Secrets location (never commit):** `~/.openclaw/` — especially `~/.openclaw/credentials/` and `~/.openclaw/openclaw.json`
- **Official docs:** [Getting started](https://docs.openclaw.ai/start/getting-started) · [WhatsApp channel](https://docs.openclaw.ai/channels/whatsapp)

## Requirements

- **Node.js ≥ 22.14** (OpenClaw will refuse older Node). This machine was set up with:

  ```bash
  export NVM_DIR="$HOME/.nvm" && . "$NVM_DIR/nvm.sh"
  nvm install 22
  nvm use 22
  ```

  Optional: `nvm alias default 22` so new terminals use Node 22.

- **CLI:** `npm install -g openclaw@latest` (re-run under Node 22 if you switch versions)

## One-time: gateway + local mode (done via CLI)

From a terminal (Node 22 active):

```bash
export NVM_DIR="$HOME/.nvm" && . "$NVM_DIR/nvm.sh"
nvm use 22

# Fix permissions, session dirs, gateway token, LaunchAgent (macOS)
openclaw doctor --fix

# Required so the gateway can start
openclaw config set gateway.mode local

# WhatsApp ships disabled — enable and restart the gateway service
openclaw plugins enable whatsapp
launchctl kickstart -k "gui/$(id -u)/ai.openclaw.gateway"
```

Full interactive wizard (model keys, etc.): `openclaw onboard --install-daemon`

## Link WhatsApp (QR code)

**Run this in Terminal.app / iTerm** (not a dead script): you must scan within ~1–2 minutes while the process stays running.

1. `nvm use 22`
2. ```bash
   openclaw channels login --channel whatsapp --verbose
   ```
3. In WhatsApp on your phone: **Settings → Linked devices → Link a device** — scan the **terminal QR**.
4. When it succeeds, verify:

   ```bash
   openclaw channels list
   ```

If the QR expires, run the login command again for a fresh code.

Do **not** copy files from `~/.openclaw/` into `market_research/` or any git-tracked path.

## Run the gateway

If you used `--install-daemon`, the gateway should run as a user service. Otherwise:

```bash
openclaw gateway --port 18789 --verbose
```

## Send a test message (after gateway + channel are up)

```bash
openclaw message send --to +1234567890 --message "Hello from OpenClaw"
```

Use the E.164 phone format for `--to`. For groups/channels, see [Groups](https://docs.openclaw.ai/channels/groups) in the docs.

## Troubleshooting

- `openclaw doctor` — config and policy checks  
- `Node.js v22.12+ is required` — run `nvm use 22` (or install 24) before `openclaw`
