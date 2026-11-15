# infra/ — cloud GPU for the LLM (owner: C)

Target: one **g5.xlarge** (NVIDIA A10G, 24 GB) running **vLLM** with `Qwen/Qwen3-8B`, reached from
laptops only through an SSH tunnel. Nothing is exposed on the public internet except SSH.

## Status

- [ ] Service quota "Running On-Demand G and VT instances" ≥ 8 vCPU requested (approval takes 1–3 days)
- [ ] Instance launched (Deep Learning AMI, Ubuntu; 100 GB disk; security group: SSH from our IPs only)
- [ ] `bash infra/vllm_serve.sh` answers `curl http://localhost:8001/v1/models` through the tunnel
- [ ] `python extract/eval.py --label M2-gpu` run against it

Until the quota is approved the pipeline uses an API provider (`LLM_BASE_URL` empty = OpenAI).

## Steps

1. **Quota**: AWS console → Service Quotas → EC2 → *Running On-Demand G and VT instances* → request 8.
2. **Launch**: g5.xlarge, "Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)", key pair
   `ee542-gpu`, security group allowing TCP 22 from your IP. Cost about $1.0/hour: **stop it when idle**.
3. **Serve** (on the instance):
   ```sh
   export VLLM_API_KEY=<pick a long random string>
   bash infra/vllm_serve.sh            # first start downloads ~16 GB of weights
   ```
4. **Tunnel** (on your laptop, keep the window open):
   ```sh
   GPU_HOST=ubuntu@<public-ip> bash infra/tunnel.sh
   curl -H "Authorization: Bearer $VLLM_API_KEY" http://localhost:8001/v1/models
   ```
5. **Point the pipeline at it** in `.env`:
   ```
   LLM_BASE_URL=http://localhost:8001/v1
   LLM_MODEL=Qwen/Qwen3-8B
   LLM_API_KEY=<the same key>
   LLM_DISABLE_THINKING=1
   ```
   then `python extract/eval.py --label M2-gpu`.

## Ports (team convention)

front end 3100 · FastAPI 8000 · Streamlit 8501 · vLLM via tunnel 8001 · bge-m3 via tunnel 8002 (M3).
