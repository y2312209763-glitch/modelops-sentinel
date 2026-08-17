.PHONY: install test audit start-vllm smoke monitor-up monitor-down monitor-gpu-up

install:
	python3 -m venv .venv
	.venv/bin/python -m pip install --upgrade pip
	.venv/bin/python -m pip install -e .

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

audit:
	.venv/bin/modelops-sentinel --format table

start-vllm:
	@test -f config/vllm.env || (echo "Copy config/vllm.env.example to config/vllm.env first" && exit 1)
	@set -a; . ./config/vllm.env; set +a; ./scripts/start_vllm.sh

smoke:
	@test -f config/vllm.env || (echo "Copy config/vllm.env.example to config/vllm.env first" && exit 1)
	@set -a; . ./config/vllm.env; set +a; ./scripts/smoke_test.sh

monitor-up:
	cd deploy && docker compose up -d

monitor-gpu-up:
	cd deploy && PROMETHEUS_CONFIG_FILE=./prometheus/prometheus-gpu.yml docker compose --profile gpu up -d

monitor-down:
	cd deploy && docker compose --profile gpu down

