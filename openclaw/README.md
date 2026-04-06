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

## One-time: install gateway + AI (recommended)

From a terminal (Node 22 active):

```bash
openclaw onboard --install-daemon
```

Follow prompts for model/API keys and gateway. (You can skip what you do not need yet; WhatsApp login is separate.)

## Link WhatsApp (QR code)

1. Use **Node 22** in the same terminal (`nvm use 22`).
2. Run:

   ```bash
   openclaw channels login --channel whatsapp
   ```

3. **Scan the QR code** with WhatsApp on your phone (**Linked devices**).

4. Confirm:

   ```bash
   openclaw channels list
   ```

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
