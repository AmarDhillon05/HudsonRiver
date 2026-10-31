# Use the repo's .venv when it exists (`make setup`), so nothing needs activating.
PY := $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
# The CDK CLI: a global `cdk` if installed, otherwise run through npx.
CDK ?= $(if $(shell command -v cdk),cdk,npx --yes aws-cdk@2)
# Public ntfy.sh topic: anyone who knows the name can read it or post to it.
NTFY_TOPIC ?= hudson-river
INTERVAL_MINUTES ?= 30
#: When the daily summary is pushed, in UTC (13 = 9am Eastern in summer, 8am in winter).
SUMMARY_HOUR_UTC ?= 13
#: Extra `cdk deploy` flags. CI passes `--require-approval never`.
CDK_DEPLOY_FLAGS ?=
GITHUB_REPO ?= AmarDhillon05/hudsonriver
GITHUB_BRANCH ?= main
CONTEXT = -c ntfyTopic=$(NTFY_TOPIC) -c intervalMinutes=$(INTERVAL_MINUTES) -c summaryHourUtc=$(SUMMARY_HOUR_UTC) $(if $(BESTBUY_API_KEY),-c bestbuyApiKey=$(BESTBUY_API_KEY))

.PHONY: setup test dry-run synth setup-ci bootstrap deploy deploy-github-role destroy reset-low

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

reset-low: ## Forget a laptop's lowest price (e.g. after a pricing error): make reset-low ITEM=p14s-gen6-amd
	@test -n "$(ITEM)" || (echo "set ITEM=<id from src/dealalert/watchlist.json>" >&2; exit 2)
	aws dynamodb delete-item --table-name "$$(aws cloudformation describe-stacks --stack-name LaptopDealAlert \
	  --query "Stacks[0].Outputs[?OutputKey=='TableName'].OutputValue" --output text)" \
	  --key '{"pk": {"S": "low#$(ITEM)"}}'
	@echo "reset: $(ITEM) starts over from the watchlist's start price"
