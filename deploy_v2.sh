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
