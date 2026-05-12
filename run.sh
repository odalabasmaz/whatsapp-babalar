#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

case "${1:-up}" in
  up)
    echo "Starting Babalar..."
    docker compose up -d
    echo ""
    echo "Frontend:  http://localhost:5173"
    echo "Backend:   http://localhost:8000"
    echo "API Docs:  http://localhost:8000/docs"
    ;;
  down)
    docker compose down
    ;;
  restart)
    docker compose restart
    ;;
  logs)
    docker compose logs -f "${2:-}"
    ;;
  status)
    docker compose ps
    ;;
  *)
    echo "Usage: $0 [up|down|restart|logs [service]|status]"
    exit 1
    ;;
esac
