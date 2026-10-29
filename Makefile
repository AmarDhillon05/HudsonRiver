CDK ?= cdk
# Public ntfy.sh topic: anyone who knows the name can read it or post to it.
NTFY_TOPIC ?= hudson-river
INTERVAL_MINUTES ?= 30
CONTEXT = -c ntfyTopic=$(NTFY_TOPIC) -c intervalMinutes=$(INTERVAL_MINUTES) $(if $(BESTBUY_API_KEY),-c bestbuyApiKey=$(BESTBUY_API_KEY))

.PHONY: test dry-run synth bootstrap deploy destroy check-topic

test:
	python3 -m pytest -q

dry-run:
	PYTHONPATH=src python3 -m dealalert.cli $(ARGS)

synth:
	cd infrastructure && $(CDK) synth -c ntfyTopic=synth-only > /dev/null && echo "synth ok"

check-topic:
	@test -n "$(NTFY_TOPIC)" || (echo "set NTFY_TOPIC=<your private ntfy topic>" >&2; exit 2)

bootstrap:
	cd infrastructure && $(CDK) bootstrap -c ntfyTopic=bootstrap-only

deploy: check-topic test
	cd infrastructure && $(CDK) deploy $(CONTEXT)

destroy: check-topic
	cd infrastructure && $(CDK) destroy $(CONTEXT)
