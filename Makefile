VENV_PYTEST ?= .venv/bin/pytest
VENV_PYTHON ?= .venv/bin/python3
AUTH_PROXY_ENV ?= deploy/auth-proxy/.env.auth-proxy
AUTH_PROXY_COMPOSE ?= deploy/auth-proxy/docker-compose.yml
AUTH0_APP_CLIENT_ID ?= wurcUczBBZFgWH5xWOomOwa7ixwAPS0x
AUTH0_PORT ?= 8088

.PHONY: stress stress-tests stress-plumbing stress-env mongo-check proxy-cookie-secret auth-proxy-up auth-proxy-down dev-auth-up dev-auth-down dev-auth-restart auth0-sync check-auth-stack dev-auth-doctor

stress: stress-env stress-tests stress-plumbing
	@echo "stress: complete"

stress-env:
	@echo "Recommended large-dataset env:"
	@echo "  ANON_MODE=standalone"
	@echo "  ANON_WORKERS=8"
	@echo "  ANON_RAW_INPUT_BACKEND=mongo"
	@echo "  ANON_MONGO_URI=mongodb://localhost:27017/anon_studio"
	@echo "  ANON_MONGO_WRITE_BATCH=5000"

stress-tests:
	TLDEXTRACT_CACHE=/tmp/tldextract-cache $(VENV_PYTEST) -q tests/test_tasks_large.py

stress-plumbing:
	$(VENV_PYTHON) scripts/stress_plumbing.py

mongo-check:
	$(VENV_PYTHON) scripts/mongo_check.py

proxy-cookie-secret:
	@$(VENV_PYTHON) -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"

auth-proxy-up:
	docker compose --env-file $(AUTH_PROXY_ENV) -f $(AUTH_PROXY_COMPOSE) up -d

auth-proxy-down:
	docker compose --env-file $(AUTH_PROXY_ENV) -f $(AUTH_PROXY_COMPOSE) down

dev-auth-up:
	bash scripts/dev_auth_stack.sh --with-proxy

dev-auth-down:
	bash scripts/dev_auth_down.sh --with-proxy

dev-auth-restart:
	bash scripts/dev_auth_down.sh --with-proxy
	bash scripts/dev_auth_stack.sh --with-proxy

auth0-sync:
	bash scripts/auth0_update_app.sh --port $(AUTH0_PORT) --app-client-id $(AUTH0_APP_CLIENT_ID)

check-auth-stack:
	bash scripts/check_auth_stack.sh

dev-auth-doctor:
	bash scripts/dev_auth_doctor.sh
