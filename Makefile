# LifeHack OS — Makefile
# Run `make help` to see all targets.

# ── Configuration ────────────────────────────────────────────────────────────
PYTHON      := python3
VENV        := .venv
VENV_BIN    := $(VENV)/bin
PIP         := $(VENV_BIN)/pip
RUFF        := $(VENV_BIN)/ruff
APP_DIR     := web

.DEFAULT_GOAL := help

# ── Help ─────────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@printf "\nLifeHack OS — available targets:\n\n"
	@printf "  %-18s %s\n" "make setup"       "Create venv, install deps, copy .env.example → .env"
	@printf "  %-18s %s\n" "make run"         "Run the Flask web app locally (requires venv)"
	@printf "  %-18s %s\n" "make lint"        "Lint the codebase with ruff"
	@printf "  %-18s %s\n" "make test"        "Run tests (placeholder — add pytest when tests exist)"
	@printf "  %-18s %s\n" "make docker"      "Build image and start containers (docker compose up --build)"
	@printf "  %-18s %s\n" "make docker-down" "Stop and remove containers (docker compose down)"
	@printf "  %-18s %s\n" "make clean"       "Remove __pycache__, *.db, .ruff_cache, etc."
	@printf "\n"

# ── Local development ─────────────────────────────────────────────────────────
.PHONY: setup
setup: $(VENV)/bin/activate
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Copied .env.example → .env — edit it before running the app."; \
	else \
		echo ".env already exists, skipping copy."; \
	fi

$(VENV)/bin/activate: requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	# Install web-only deps; skip desktop GUI packages (customtkinter, pillow)
	$(PIP) install \
		"flask>=3.0.0" \
		"flask-cors>=4.0.0" \
		"requests>=2.31.0" \
		"python-dotenv>=1.0.0" \
		"toml>=0.10.2" \
		ruff
	@touch $(VENV)/bin/activate

.PHONY: run
run:
	@if [ ! -f $(VENV_BIN)/flask ]; then \
		echo "Run 'make setup' first to create the virtual environment."; exit 1; \
	fi
	@if [ ! -f .env ]; then \
		echo "Run 'make setup' first — .env file is missing."; exit 1; \
	fi
	cd $(APP_DIR) && $(PYTHON_RUN) app.py
# Use the venv python so the env var below resolves at recipe time
PYTHON_RUN := ../$(VENV_BIN)/python

# ── Code quality ──────────────────────────────────────────────────────────────
.PHONY: lint
lint:
	@if [ ! -f $(RUFF) ]; then \
		echo "Run 'make setup' first to install ruff."; exit 1; \
	fi
	$(RUFF) check .

.PHONY: test
test:
	@echo "No tests yet. Add pytest to the venv and create a tests/ directory."
	@echo "Then update this target to: cd web && ../$(VENV_BIN)/pytest ../tests/ -v"

# ── Docker ────────────────────────────────────────────────────────────────────
.PHONY: docker
docker:
	@if [ ! -f .env ]; then \
		echo "Run 'make setup' first — .env file is required for docker compose."; exit 1; \
	fi
	docker compose up --build -d
	@echo "App is starting at http://localhost:8420"
	@echo "Follow logs with: docker compose logs -f lifehack-os"

.PHONY: docker-down
docker-down:
	docker compose down

# ── Cleanup ───────────────────────────────────────────────────────────────────
.PHONY: clean
clean:
	find . -type d -name "__pycache__" -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc"      -not -path "./.venv/*" -delete 2>/dev/null || true
	find . -type f -name "*.db"       -not -path "./data/*"   -delete 2>/dev/null || true
	rm -rf .ruff_cache .pytest_cache
	@echo "Clean complete."
