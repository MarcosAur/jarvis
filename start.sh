#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

VENV_BIN="$ROOT_DIR/.venv/bin"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

WEB_LOG="$LOG_DIR/web.log"
CELERY_LOG="$LOG_DIR/celery.log"

WEB_PID=""
CELERY_PID=""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}   $1"; }
log_warn()  { echo -e "${YELLOW}[AVISO]${NC} $1"; }
log_error() { echo -e "${RED}[ERRO]${NC} $1" >&2; }

cleanup() {
  echo ""
  log_info "Encerrando serviços..."
  if [[ -n "$WEB_PID" ]] && kill -0 "$WEB_PID" 2>/dev/null; then
    kill "$WEB_PID" 2>/dev/null || true
    wait "$WEB_PID" 2>/dev/null || true
    log_info "Servidor Web encerrado."
  fi
  if [[ -n "$CELERY_PID" ]] && kill -0 "$CELERY_PID" 2>/dev/null; then
    kill "$CELERY_PID" 2>/dev/null || true
    wait "$CELERY_PID" 2>/dev/null || true
    log_info "Celery Worker + Beat encerrado."
  fi
}
trap cleanup EXIT INT TERM

# 1. Validar ambiente virtual
if [[ ! -x "$VENV_BIN/uvicorn" || ! -x "$VENV_BIN/celery" ]]; then
  log_error "Ambiente virtual não encontrado ou incompleto em $VENV_BIN."
  log_error "Verifique se .venv está criado e com uvicorn/celery instalados."
  exit 1
fi

# 2. Verificar / Iniciar Redis
log_info "Verificando Redis (broker Celery)..."
redis_ok() {
  if command -v redis-cli >/dev/null 2>&1; then
    [[ "$(redis-cli ping 2>/dev/null || true)" == "PONG" ]]
  else
    python3 -c "import socket; s = socket.create_connection(('127.0.0.1', 6379), 1); s.close()" 2>/dev/null
  fi
}

if redis_ok; then
  log_ok "Redis já está rodando na porta 6379."
else
  log_warn "Redis não está respondendo. Tentando iniciar..."
  if command -v redis-server >/dev/null 2>&1; then
    redis-server --daemonize yes >/dev/null 2>&1 || true
    sleep 1
  fi
  if ! redis_ok && command -v systemctl >/dev/null 2>&1; then
    sudo systemctl start redis-server >/dev/null 2>&1 || true
    sleep 1
  fi

  if redis_ok; then
    log_ok "Redis iniciado com sucesso."
  else
    log_error "Falha ao iniciar o Redis na porta 6379."
    log_error "Inicie o Redis manualmente (ex.: sudo systemctl start redis-server) e tente novamente."
    exit 1
  fi
fi

# 3. Iniciar Celery Worker + Beat
log_info "Iniciando Celery Worker + Beat..."
"$VENV_BIN/celery" -A pipeline.celery_app:celery_app worker --beat --loglevel=info >"$CELERY_LOG" 2>&1 &
CELERY_PID=$!

sleep 3
if ! kill -0 "$CELERY_PID" 2>/dev/null; then
  log_error "Falha ao iniciar o Celery Worker + Beat. Últimas linhas de $CELERY_LOG:"
  tail -n 25 "$CELERY_LOG" >&2 || true
  exit 1
fi
log_ok "Celery Worker + Beat ativo (PID $CELERY_PID) — log: $CELERY_LOG"

# 4. Iniciar Servidor Web (FastAPI / Uvicorn)
if python3 -c "import socket; s = socket.create_connection(('127.0.0.1', 8000), 1); s.close()" 2>/dev/null; then
  log_error "A porta 8000 já está em uso por outro processo."
  log_error "Finalize o processo existente na porta 8000 antes de rodar este script."
  exit 1
fi

log_info "Iniciando Servidor Web (Uvicorn em http://127.0.0.1:8000)..."
"$VENV_BIN/uvicorn" pipeline.web.app:app --host 0.0.0.0 --port 8000 --reload >"$WEB_LOG" 2>&1 &
WEB_PID=$!

WEB_READY=0
for _ in {1..15}; do
  if ! kill -0 "$WEB_PID" 2>/dev/null; then
    break
  fi
  if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/projects', timeout=1)" >/dev/null 2>&1; then
    WEB_READY=1
    break
  fi
  sleep 1
done

if [[ "$WEB_READY" -ne 1 ]]; then
  log_error "Falha ao iniciar o Servidor Web na porta 8000. Últimas linhas de $WEB_LOG:"
  tail -n 25 "$WEB_LOG" >&2 || true
  exit 1
fi
log_ok "Servidor Web ativo em http://127.0.0.1:8000 (PID $WEB_PID) — log: $WEB_LOG"

echo ""
log_ok "Toda a arquitetura está rodando! Pressione Ctrl+C para encerrar Web + Celery."
echo "  • Web:    http://127.0.0.1:8000"
echo "  • Logs:   $WEB_LOG | $CELERY_LOG"
echo ""

# Monitora os processos enquanto estiverem ativos
while true; do
  if ! kill -0 "$CELERY_PID" 2>/dev/null; then
    log_error "O processo do Celery (PID $CELERY_PID) parou inesperadamente. Verifique $CELERY_LOG:"
    tail -n 20 "$CELERY_LOG" >&2 || true
    exit 1
  fi
  if ! kill -0 "$WEB_PID" 2>/dev/null; then
    log_error "O Servidor Web (PID $WEB_PID) parou inesperadamente. Verifique $WEB_LOG:"
    tail -n 20 "$WEB_LOG" >&2 || true
    exit 1
  fi
  sleep 2
done
