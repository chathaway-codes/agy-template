.PHONY: help test test-issues issues issues-ready issues-ui clean docker-build docker-test docker-shell docker-yolo

DOCKER_IMAGE ?= agent-workspace:latest

help: ## Show this help message
	@echo "Available targets:"
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

test: test-issues ## Run test suite

test-issues: ## Run unit tests for git issue tracker CLI and server
	python3 tests/test_issue_tooling.py

issues: ## List git issues in tabular format
	@python3 scripts/issue.py list

issues-ready: ## List open issues ready for pickup (no blockers)
	@python3 scripts/issue.py ready

issues-ui: ## Launch read-only issue browser Web UI on port 8080
	python3 scripts/issue_server.py --port 8080

clean: ## Clean generated test caches and temporary files
	rm -rf __pycache__ tests/__pycache__ scripts/__pycache__

docker-build: ## Build containerized development Docker image
	docker build -t $(DOCKER_IMAGE) .

docker-test: ## Run test suite inside container
	docker run --rm -v $(CURDIR):/workspace -w /workspace $(DOCKER_IMAGE) make test

docker-shell: ## Launch interactive shell inside container
	docker run --rm -it \
		-v $(CURDIR):/workspace \
		-v agy-sandbox-data:/home/developer/.gemini/antigravity-cli \
		-v $(HOME)/.gemini/antigravity-cli/antigravity-oauth-token:/home/developer/.gemini/antigravity-cli/antigravity-oauth-token:ro \
		-w /workspace \
		$(DOCKER_IMAGE) /bin/bash

docker-yolo: ## Launch containerized Antigravity daemon in isolated YOLO mode
	docker rm -f agy-sandbox 2>/dev/null || true
	docker run -d --name agy-sandbox \
		-v $(CURDIR):/workspace \
		-v agy-sandbox-data:/home/developer/.gemini/antigravity-cli \
		-v $(HOME)/.gemini/antigravity-cli/antigravity-oauth-token:/home/developer/.gemini/antigravity-cli/antigravity-oauth-token:ro \
		-w /workspace \
		$(DOCKER_IMAGE) \
		bash -c '\
			mkdir -p ~/.gemini/config/projects ~/.gemini/antigravity-cli && \
			echo "{\"userSettings\": {\"cliRemoteControlHostname\": \"agy-sandbox\", \"remoteControlHostname\": \"agy-sandbox\", \"autoExecutionPolicy\": \"always-proceed\", \"globalPermissionGrants\": {\"allow\": [\"command(*)\", \"read_url(*)\", \"mcp(*)\"]}}}" > ~/.gemini/config/config.json && \
			echo "{\"id\": \"agent-workspace\", \"name\": \"workspace\", \"projectResources\": {\"resources\": [{\"gitFolder\": {\"folderUri\": \"file:///workspace\", \"defaultBranch\": \"main\"}}]}, \"settings\": {}, \"isWorkspaceOnly\": false}" > ~/.gemini/config/projects/workspace.json && \
			python3 -c "import json, os; p = os.path.expanduser(\"~/.gemini/antigravity-cli/settings.json\"); d = json.load(open(p)) if os.path.exists(p) else {}; d[\"autoExecutionPolicy\"] = \"always-proceed\"; d[\"trustedWorkspaces\"] = [\"/workspace\", \"/tmp\", \"/home/developer\"]; json.dump(d, open(p, \"w\"), indent=2)" && \
			exec agy --dangerously-skip-permissions remote-control serve'
