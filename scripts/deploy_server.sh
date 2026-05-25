#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/MoyinEngine_ai}"
REPO_URL="${REPO_URL:-https://github.com/HaozaiGo/MoyinEngine_ai.git}"
BRANCH="${BRANCH:-master}"
SERVICE_NAME="${SERVICE_NAME:-director-ai}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
APP_USER="${APP_USER:-$(id -un)}"
APP_GROUP="${APP_GROUP:-$(id -gn)}"
WEB_DIR="$APP_DIR/web"
VENV_DIR="$WEB_DIR/.venv"

log() {
  printf '[deploy] %s\n' "$*"
}

ensure_app_dir() {
  local parent
  parent="$(dirname "$APP_DIR")"

  if [ ! -d "$parent" ]; then
    sudo mkdir -p "$parent"
  fi

  if [ ! -e "$APP_DIR" ]; then
    sudo mkdir -p "$APP_DIR"
    sudo chown "$APP_USER:$APP_GROUP" "$APP_DIR"
    return
  fi

  if [ ! -d "$APP_DIR/.git" ] && [ -n "$(find "$APP_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
    local backup_dir
    backup_dir="${APP_DIR}.backup-$(date +%Y%m%d%H%M%S)"
    log "Existing non-git directory found. Moving it to $backup_dir"
    sudo mv "$APP_DIR" "$backup_dir"
    sudo mkdir -p "$APP_DIR"
  fi

  sudo chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"
}

sync_code() {
  ensure_app_dir

  if [ ! -d "$APP_DIR/.git" ]; then
    log "Cloning $REPO_URL to $APP_DIR"
    git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
  else
    log "Pulling latest $BRANCH"
    git -C "$APP_DIR" remote set-url origin "$REPO_URL"
    git -C "$APP_DIR" fetch origin "$BRANCH"
    git -C "$APP_DIR" checkout "$BRANCH"
    git -C "$APP_DIR" reset --hard "origin/$BRANCH"
  fi
}

ensure_python_env() {
  log "Preparing Python environment"

  if ! "$PYTHON_BIN" -m venv "$VENV_DIR" >/tmp/director-ai-venv.log 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
      log "Installing python3-venv"
      sudo apt-get update
      sudo apt-get install -y python3-venv
      "$PYTHON_BIN" -m venv "$VENV_DIR"
    else
      cat /tmp/director-ai-venv.log
      exit 1
    fi
  fi

  "$VENV_DIR/bin/python" -m pip install --upgrade pip
  "$VENV_DIR/bin/pip" install -r "$WEB_DIR/requirements.txt"
}

ensure_runtime_files() {
  log "Preparing runtime directories"
  mkdir -p \
    "$WEB_DIR/assets/characters" \
    "$WEB_DIR/assets/scenes" \
    "$WEB_DIR/assets/props" \
    "$WEB_DIR/assets/styles" \
    "$WEB_DIR/outputs" \
    "$WEB_DIR/projects" \
    "$WEB_DIR/uploads" \
    "$WEB_DIR/exports"

  if [ ! -f "$WEB_DIR/.env" ]; then
    log "No .env found on server. Creating one from .env.example; fill real keys before production use."
    cp "$WEB_DIR/.env.example" "$WEB_DIR/.env"
  fi

  sudo chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"
}

install_systemd_service() {
  local service_file
  service_file="/etc/systemd/system/${SERVICE_NAME}.service"

  log "Installing systemd service $SERVICE_NAME"
  sudo tee "$service_file" >/dev/null <<SERVICE
[Unit]
Description=Director AI Gradio Web App
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_GROUP
WorkingDirectory=$WEB_DIR
Environment=PYTHONUNBUFFERED=1
Environment=GRADIO_HOST=0.0.0.0
Environment=GRADIO_PORT=8862
ExecStart=$VENV_DIR/bin/python app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

  sudo systemctl daemon-reload
  sudo systemctl enable "$SERVICE_NAME"
  sudo systemctl restart "$SERVICE_NAME"
}

print_status() {
  log "Deployment finished"
  sudo systemctl --no-pager --full status "$SERVICE_NAME" || true
}

main() {
  sync_code
  ensure_python_env
  ensure_runtime_files
  install_systemd_service
  print_status
}

main "$@"
