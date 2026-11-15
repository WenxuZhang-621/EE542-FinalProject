#!/usr/bin/env bash
# On your laptop: map the GPU box's vLLM (8000) to localhost:8001 and bge-m3 (8002) to localhost:8002.
#   GPU_HOST=ubuntu@<public-ip> KEY=~/.ssh/ee542-gpu.pem bash infra/tunnel.sh
# Then in .env:  LLM_BASE_URL=http://localhost:8001/v1  LLM_MODEL=Qwen/Qwen3-8B  LLM_DISABLE_THINKING=1
set -euo pipefail
: "${GPU_HOST:?GPU_HOST=ubuntu@<ip>}"
KEY=${KEY:-$HOME/.ssh/ee542-gpu.pem}
exec ssh -i "$KEY" -N -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes \
  -L 8001:localhost:8000 -L 8002:localhost:8002 "$GPU_HOST"
