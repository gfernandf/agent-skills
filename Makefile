.PHONY: install bootstrap test lint format check serve mcp clean help

REGISTRY_DIR ?= ../agent-skill-registry
REGISTRY_URL ?= https://github.com/gfernandf/agent-skill-registry.git

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

bootstrap: ## Clone registry + install (one-command setup)
	@if [ ! -d "$(REGISTRY_DIR)" ]; then \
		echo "Cloning agent-skill-registry..."; \
		git clone $(REGISTRY_URL) $(REGISTRY_DIR); \
	else \
		echo "Registry already present at $(REGISTRY_DIR)"; \
	fi
	python -m pip install -e ".[all,dev]"
	@echo "\n✓ Ready — run 'make test' or 'agent-skills doctor' to verify."

install: ## Install in dev mode with all extras
	python -m pip install -e ".[all,dev]"

test: ## Run full test suite
	python -m pytest -o "addopts=" -q

lint: ## Run ruff linter
	python -m ruff check --output-format=github .

format: ## Auto-format with ruff
	python -m ruff format .

check: lint ## Lint + format check + tests
	python -m ruff format --check .
	python -m pytest -o "addopts=" -q

serve: ## Start HTTP server (localhost:8080)
	python -m cli.main serve

mcp: ## Start MCP server (stdio)
	python -m official_mcp_servers

clean: ## Remove build artifacts
	rm -rf build/ dist/ *.egg-info __pycache__ .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
