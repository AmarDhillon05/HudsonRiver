# Use the repo's .venv when it exists (`make setup`), so nothing needs activating.
PY := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
# The CDK CLI: a global `cdk` if installed, otherwise run through npx.
CDK ?= $(if $(shell command -v cdk),cdk,npx --yes aws-cdk@2)
# Public ntfy.sh topic: anyone who knows the name can read it or post to it.
NTFY_TOPIC ?= hudson-river
INTERVAL_MINUTES ?= 30
#: Extra `cdk deploy` flags. CI passes `--require-approval never`.
CDK_DEPLOY_FLAGS ?=
GITHUB_REPO ?= AmarDhillon05/hudsonriver
GITHUB_BRANCH ?= main
CONTEXT = -c ntfyTopic=$(NTFY_TOPIC) -c intervalMinutes=$(INTERVAL_MINUTES) $(if $(BESTBUY_API_KEY),-c bestbuyApiKey=$(BESTBUY_API_KEY))

.PHONY: setup test dry-run synth setup-ci bootstrap deploy deploy-github-role destroy

setup: ## Create .venv and install everything (run once)
	python3 -m venv .venv
	.venv/bin/python -m pip install -q --upgrade pip
	.venv/bin/python -m pip install -q -e ".[dev]"
	@echo "ready: no need to activate .venv, the Makefile uses it directly"

test:
	$(PY) -m pytest -q

dry-run:
	PYTHONPATH=src $(PY) -m dealalert.cli $(ARGS)

synth:
	cd infrastructure && $(CDK) synth $(CONTEXT) > /dev/null && echo "synth ok"

setup-ci:
	python3 -m pip install -q -e ".[dev]"
	npm install -g aws-cdk@2

bootstrap:
	cd infrastructure && $(CDK) bootstrap $(CONTEXT)

deploy: test
	cd infrastructure && $(CDK) deploy LaptopDealAlert $(CONTEXT) $(CDK_DEPLOY_FLAGS)

deploy-github-role: ## Once: the role GitHub Actions uses to auto-deploy
	cd infrastructure && $(CDK) deploy LaptopDealAlertGitHubDeploy $(CONTEXT) \
	  -c githubRepo=$(GITHUB_REPO) -c githubBranch=$(GITHUB_BRANCH) \
	  $(if $(CREATE_OIDC_PROVIDER),-c githubCreateOidcProvider=true)

destroy:
	cd infrastructure && $(CDK) destroy LaptopDealAlert $(CONTEXT)
