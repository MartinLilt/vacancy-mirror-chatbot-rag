SHELL := /bin/bash

# Tunnel config (override from env if needed)
SSH_KEY ?= /Users/$(shell whoami)/.ssh/vacancy_mirror_deploy
SSH_PORT ?= 2222
SCRAPER_SERVER_IP ?= 178.104.110.28
BACKEND_SERVER_IP ?= 178.104.113.58

RUN_DIR := .tunnels
SCRAPER_PID := $(RUN_DIR)/scraper.pid
BACKEND_PID := $(RUN_DIR)/backend.pid
SCRAPER_LOG := $(RUN_DIR)/scraper.log
BACKEND_LOG := $(RUN_DIR)/backend.log
DASHBOARD_SRC := infra/monitoring/grafana/provisioning/dashboards/scraper.json
DASHBOARD_DST := /etc/vacancy-mirror/grafana/provisioning/dashboards/scraper.json

.PHONY: help panels panels-up panels-open panels-down panels-restart panels-status scraper-grafana-dashboard scraper-panel scraper-panel-up scraper-panel-open scraper-panel-status scraper-panel-down scraper-panel-restart

help:
	@echo "Available targets:"
	@echo "  make panels         # Start all tunnels + open 3 browser windows"
	@echo "  make panels-up      # Start scraper/backend tunnel processes"
	@echo "  make panels-open    # Open scraper/backend/chatwoot URLs locally"
	@echo "  make panels-status  # Show PID/process and local port status"
	@echo "  make panels-down    # Stop tunnel processes started by this Makefile"
	@echo "  make panels-restart # Restart tunnels and open URLs"
	@echo "  make scraper-grafana-dashboard # Upload scraper dashboard JSON and restart Grafana on scraper server"
	@echo "  make scraper-panel       # Start scraper tunnel + open scraper Grafana"
	@echo "  make scraper-panel-up    # Start scraper-only tunnel (3000, 8000)"
	@echo "  make scraper-panel-open  # Open scraper Grafana URL"
	@echo "  make scraper-panel-status# Show scraper-only tunnel and ports"
	@echo "  make scraper-panel-down  # Stop scraper-only tunnel"

panels: panels-up panels-open panels-status

panels-up:
	@set -euo pipefail; \
	mkdir -p "$(RUN_DIR)"; \
	if [[ -f "$(SCRAPER_PID)" ]] && kill -0 "$$(cat "$(SCRAPER_PID)")" 2>/dev/null; then \
	  echo "scraper tunnel already running (pid=$$(cat "$(SCRAPER_PID)"))"; \
	else \
	  rm -f "$(SCRAPER_PID)"; \
	  remote_grafana_host="$$(ssh -p "$(SSH_PORT)" -i "$(SSH_KEY)" "root@$(SCRAPER_SERVER_IP)" "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' grafana 2>/dev/null || true")"; \
	  if [[ -z "$$remote_grafana_host" ]]; then remote_grafana_host="127.0.0.1"; fi; \
	  echo "using remote grafana target: $$remote_grafana_host:3000"; \
	  nohup ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
	    -i "$(SSH_KEY)" -p "$(SSH_PORT)" \
	    -L 3000:$$remote_grafana_host:3000 -L 8000:127.0.0.1:8000 \
	    root@$(SCRAPER_SERVER_IP) >"$(SCRAPER_LOG)" 2>&1 & \
	  echo $$! > "$(SCRAPER_PID)"; \
	  echo "started scraper tunnel (pid=$$(cat "$(SCRAPER_PID)"))"; \
	  for i in $$(seq 1 20); do \
	    if lsof -nP -iTCP:3000 -sTCP:LISTEN >/dev/null 2>&1 && lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then \
	      echo "scraper tunnel ports are ready"; \
	      break; \
	    fi; \
	    sleep 0.2; \
	  done; \
	fi; \
	if [[ -f "$(BACKEND_PID)" ]] && kill -0 "$$(cat "$(BACKEND_PID)")" 2>/dev/null; then \
	  echo "backend tunnel already running (pid=$$(cat "$(BACKEND_PID)"))"; \
	else \
	  rm -f "$(BACKEND_PID)"; \
	  nohup ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
	    -i "$(SSH_KEY)" -p "$(SSH_PORT)" \
	    -L 3001:127.0.0.1:3001 -L 3002:127.0.0.1:3002 \
	    root@$(BACKEND_SERVER_IP) >"$(BACKEND_LOG)" 2>&1 & \
	  echo $$! > "$(BACKEND_PID)"; \
	  echo "started backend tunnel (pid=$$(cat "$(BACKEND_PID)"))"; \
	fi; \
	sleep 1

panels-open:
	@set -euo pipefail; \
	for url in http://localhost:3000 http://localhost:3001 http://localhost:3002; do \
	  if open -na "Google Chrome" --args --new-window "$$url" >/dev/null 2>&1; then \
	    echo "opened $$url in new Chrome window"; \
	  else \
	    open "$$url"; \
	    echo "opened $$url in default browser"; \
	  fi; \
	done

panels-status:
	@set -euo pipefail; \
	echo "== tunnel processes =="; \
	if [[ -f "$(SCRAPER_PID)" ]] && kill -0 "$$(cat "$(SCRAPER_PID)")" 2>/dev/null; then \
	  echo "scraper: up (pid=$$(cat "$(SCRAPER_PID)"))"; \
	else \
	  echo "scraper: down"; \
	fi; \
	if [[ -f "$(BACKEND_PID)" ]] && kill -0 "$$(cat "$(BACKEND_PID)")" 2>/dev/null; then \
	  echo "backend: up (pid=$$(cat "$(BACKEND_PID)"))"; \
	else \
	  echo "backend: down"; \
	fi; \
	echo "== local ports =="; \
	for p in 3000 3001 3002 8000; do \
	  if lsof -nP -iTCP:$$p -sTCP:LISTEN >/dev/null 2>&1; then \
	    echo "$$p: listening"; \
	  else \
	    echo "$$p: not listening"; \
	  fi; \
	done

panels-down:
	@set -euo pipefail; \
	for f in "$(SCRAPER_PID)" "$(BACKEND_PID)"; do \
	  if [[ -f "$$f" ]]; then \
	    pid="$$(cat "$$f")"; \
	    if kill -0 "$$pid" 2>/dev/null; then \
	      kill "$$pid" || true; \
	      echo "stopped pid=$$pid"; \
	    fi; \
	    rm -f "$$f"; \
	  fi; \
	done

panels-restart: panels-down panels-up panels-open panels-status

scraper-panel: scraper-panel-up scraper-panel-open scraper-panel-status

scraper-panel-up:
	@set -euo pipefail; \
	mkdir -p "$(RUN_DIR)"; \
	if [[ -f "$(SCRAPER_PID)" ]] && kill -0 "$$(cat "$(SCRAPER_PID)")" 2>/dev/null; then \
	  echo "scraper tunnel already running (pid=$$(cat "$(SCRAPER_PID)"))"; \
	else \
	  rm -f "$(SCRAPER_PID)"; \
	  remote_grafana_host="$$(ssh -p "$(SSH_PORT)" -i "$(SSH_KEY)" "root@$(SCRAPER_SERVER_IP)" "docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' grafana 2>/dev/null || true")"; \
	  if [[ -z "$$remote_grafana_host" ]]; then remote_grafana_host="127.0.0.1"; fi; \
	  echo "using remote grafana target: $$remote_grafana_host:3000"; \
	  nohup ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
	    -i "$(SSH_KEY)" -p "$(SSH_PORT)" \
	    -L 3000:$$remote_grafana_host:3000 -L 8000:127.0.0.1:8000 \
	    root@$(SCRAPER_SERVER_IP) >"$(SCRAPER_LOG)" 2>&1 & \
	  echo $$! > "$(SCRAPER_PID)"; \
	  echo "started scraper tunnel (pid=$$(cat "$(SCRAPER_PID)"))"; \
	  for i in $$(seq 1 20); do \
	    if lsof -nP -iTCP:3000 -sTCP:LISTEN >/dev/null 2>&1 && lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then \
	      echo "scraper tunnel ports are ready"; \
	      break; \
	    fi; \
	    sleep 0.2; \
	  done; \
	fi

scraper-panel-open:
	@set -euo pipefail; \
	url="http://localhost:3000"; \
	if open -na "Google Chrome" --args --new-window "$$url" >/dev/null 2>&1; then \
	  echo "opened $$url in new Chrome window"; \
	else \
	  open "$$url"; \
	  echo "opened $$url in default browser"; \
	fi

scraper-panel-status:
	@set -euo pipefail; \
	echo "== scraper tunnel process =="; \
	if [[ -f "$(SCRAPER_PID)" ]] && kill -0 "$$(cat "$(SCRAPER_PID)")" 2>/dev/null; then \
	  echo "scraper: up (pid=$$(cat "$(SCRAPER_PID)"))"; \
	else \
	  echo "scraper: down"; \
	fi; \
	echo "== scraper local ports =="; \
	for p in 3000 8000; do \
	  if lsof -nP -iTCP:$$p -sTCP:LISTEN >/dev/null 2>&1; then \
	    echo "$$p: listening"; \
	  else \
	    echo "$$p: not listening"; \
	  fi; \
	done

scraper-panel-down:
	@set -euo pipefail; \
	if [[ -f "$(SCRAPER_PID)" ]]; then \
	  pid="$$(cat "$(SCRAPER_PID)")"; \
	  if kill -0 "$$pid" 2>/dev/null; then \
	    kill "$$pid" || true; \
	    echo "stopped scraper tunnel pid=$$pid"; \
	  fi; \
	  rm -f "$(SCRAPER_PID)"; \
	else \
	  echo "scraper tunnel pid file not found"; \
	fi

scraper-panel-restart: scraper-panel-down scraper-panel-up scraper-panel-open scraper-panel-status

scraper-grafana-dashboard:
	@set -euo pipefail; \
	if [[ ! -f "$(DASHBOARD_SRC)" ]]; then \
	  echo "dashboard file not found: $(DASHBOARD_SRC)"; \
	  exit 1; \
	fi; \
	echo "Ensuring remote directory exists: $(dir $(DASHBOARD_DST))"; \
	ssh -p "$(SSH_PORT)" -i "$(SSH_KEY)" "root@$(SCRAPER_SERVER_IP)" "mkdir -p '$(dir $(DASHBOARD_DST))'"; \
	echo "Uploading $(DASHBOARD_SRC) -> root@$(SCRAPER_SERVER_IP):$(DASHBOARD_DST)"; \
	scp -P "$(SSH_PORT)" -i "$(SSH_KEY)" "$(DASHBOARD_SRC)" "root@$(SCRAPER_SERVER_IP):$(DASHBOARD_DST)"; \
	echo "Restarting Grafana on scraper server (auto-detect service)..."; \
	ssh -p "$(SSH_PORT)" -i "$(SSH_KEY)" "root@$(SCRAPER_SERVER_IP)" \
	  'set -e; cd /etc/vacancy-mirror; \
	   svc=""; \
	   for s in grafana grafana-scraper grafana-backend; do \
	     if docker compose config --services 2>/dev/null | grep -qx "$$s"; then svc="$$s"; break; fi; \
	   done; \
	   if [ -n "$$svc" ]; then \
	     echo "Using compose service: $$svc"; \
	     docker compose restart "$$svc"; \
	     docker compose logs --tail 30 "$$svc" || true; \
	   elif docker ps --format "{{.Names}}" | grep -qx "grafana"; then \
	     echo "Compose service not found; restarting container: grafana"; \
	     docker restart grafana; \
	     docker logs --tail 30 grafana || true; \
	   else \
	     echo "WARN: Grafana service/container not found; dashboard file uploaded only."; \
	     docker compose ps || true; \
	   fi'; \
	echo "Done. Hard refresh Grafana UI (Cmd+Shift+R)."

