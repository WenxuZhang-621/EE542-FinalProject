#!/usr/bin/env bash
# On the GPU instance (g5.xlarge, A10G 24 GB, Deep Learning AMI Ubuntu). Run once per boot.
#   bash infra/vllm_serve.sh                 # Qwen/Qwen3-8B on port 8000 (instance-local)
# Clients reach it through the SSH tunnel in infra/tunnel.sh as http://localhost:8001/v1.
set -euo pipefail
MODEL=${MODEL:-Qwen/Qwen3-8B}
PORT=${PORT:-8000}
: "${VLLM_API_KEY:?set VLLM_API_KEY to the key the clients will send (LLM_API_KEY in .env)}"
python3 -m pip install -q --upgrade "vllm>=0.8"
exec vllm serve "$MODEL" \
  --host 127.0.0.1 --port "$PORT" \
  --api-key "$VLLM_API_KEY" \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --enable-auto-tool-choice --tool-call-parser hermes   # tool calling for M3; harmless for extraction
