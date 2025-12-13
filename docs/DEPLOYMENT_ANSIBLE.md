# Deployment – Docker & Ansible

The bot is designed to run as a small stack:

- **cryptobot-db** – PostgreSQL 17 (inside Docker)
- **cryptobot-app** – the bot container

You can deploy it in two main ways:

1. **Local Docker / Docker Compose** (manual)
2. **Remote deployment with Ansible** (`deploy_v2.sh`)

---

## Docker Setup (local or on the server)

1. Copy the template and create your `.env` file **next to** `docker-compose.stack.yml`:

```env
# --- Solana / Helius / Notifications ---
HELIUS_API_KEY=your_helius_api_key
SOLANA_PRIVATE_KEY=your_base58_private_key
DISCORD_TOKEN=your_discord_bot_token
BIRD_EYE=your_birdeye_key
DEX=Pumpfun

# --- Database (for the stack Postgres) ---
DB_NAME=sniper_db
DB_HOST=db          # IMPORTANT: must be "db" for docker-compose stack
DB_PORT=5432
DB_USER=sniper_user
DB_PASSWORD=super_secret_password

PYTHONUNBUFFERED=1
---
```
2. docker compose -f docker-compose.stack.yml up -d --build

```env
docker compose -f docker-compose.stack.yml up -d --build
```
---
## Important Notes

- DB_HOST=db – this is the service name of the Postgres container inside the Docker network.
- If you still have an old standalone Postgres container (e.g. postgres on localhost:5432), that’s separate. For the new stack, keep DB_HOST=db so the bot talks to the stack Postgres, not the old one.

---

## Ansible Deployment (remote server)

- ### The repo ships example config files:
  - infra/ansible/inventory.example.ini
  - infra/ansible/group_vars/sniper_lab.example.yml
  - infra/ansible/env.example
- Do not edit the *.example files directly. Copy them to files without the .example suffix and edit those.The real files (inventory.ini, sniper_lab.yml, .env) are usually in .gitignore so your secrets stay local.

1. Inventory (inventory.ini)
2. Sniper stack variables (sniper_lab.yml or the playbook vars)
3. deploy_v2.sh on your local machine

---
- inventory.ini

```env
[sniper_lab]
sniper_vm ansible_host=SERVER_IP ansible_user=YOUR_SERVER_NAME
---

- sniper_lab.yml
```env
# Where the project will live on the remote server
sniper_app_dir: /home/REMOTE_USER/sniper_stack

# How we ship the code
sniper_project_tar: project.tar

# Docker compose file names
sniper_docker_compose_src: docker-compose.stack.yml
sniper_docker_compose_dest: docker-compose.yml

# Env file handling
sniper_env_template: env.example   # shipped from repo
sniper_env_file: .env              # actual runtime env on server

# Docker compose project name
sniper_compose_project_name: sniper_stack
```
---

- deploy_v2.sh
```env
#!/bin/bash
set -e

# ── Local deploy config (Ansible controller) ──────────────────────────────
ANSIBLE_VENV="${ANSIBLE_VENV:-$HOME/ansible-venv}"
INVENTORY_FILE="infra/ansible/inventory.ini"
PLAYBOOK_FILE="infra/ansible/crypto_stack.yml"
ARCHIVE_PATH="infra/ansible/project.tar"
# ──────────────────────────────────────────────────────────────────────────

# Activate Ansible venv
source "$ANSIBLE_VENV/bin/activate"

echo "[deploy_v2] Creating $ARCHIVE_PATH from current Git HEAD..."
git archive -o "$ARCHIVE_PATH" HEAD

echo "[deploy_v2] Running Ansible playbook..."
ansible-playbook \
  -i "$INVENTORY_FILE" \
  "$PLAYBOOK_FILE" \
  --ask-pass --ask-become-pass
```
---

-usage
    - chmod +x deploy_v2.sh # once
    - ./deploy_v2.sh # deploy/update stack on the server


