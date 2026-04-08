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

.PHONY: help panels panels-up panels-open panels-down panels-restart panels-status

help:
	@echo "Available targets:"
	@echo "  make panels         # Start all tunnels + open 3 browser windows"
	@echo "  make panels-up      # Start scraper/backend tunnel processes"
	@echo "  make panels-open    # Open scraper/backend/chatwoot URLs locally"
	@echo "  make panels-status  # Show PID/process and local port status"
	@echo "  make panels-down    # Stop tunnel processes started by this Makefile"
	@echo "  make panels-restart # Restart tunnels and open URLs"

panels: panels-up panels-open panels-status

panels-up:
	@set -euo pipefail; \
	mkdir -p "$(RUN_DIR)"; \
	if [[ -f "$(SCRAPER_PID)" ]] && kill -0 "$$(cat "$(SCRAPER_PID)")" 2>/dev/null; then \
	  echo "scraper tunnel already running (pid=$$(cat "$(SCRAPER_PID)"))"; \
	else \
	  rm -f "$(SCRAPER_PID)"; \
	  nohup ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
	    -i "$(SSH_KEY)" -p "$(SSH_PORT)" \
	    -L 3000:127.0.0.1:3000 -L 8000:127.0.0.1:8000 \
	    root@$(SCRAPER_SERVER_IP) >"$(SCRAPER_LOG)" 2>&1 & \
	  echo $$! > "$(SCRAPER_PID)"; \
	  echo "started scraper tunnel (pid=$$(cat "$(SCRAPER_PID)"))"; \
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

