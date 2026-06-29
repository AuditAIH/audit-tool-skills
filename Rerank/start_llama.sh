#!/bin/bash

# 替换为ollama内置llama-server，直接指定cuda13后端环境，按需调整为v12
# 请先运行ollama pull AuditAid/Qwen3_Reranker #手动拉取模型
# 按需增加`--ubatch-size 4096  --batch-size 4096`参数，开启调试  --verbose
export GGML_BACKEND_PATH=/usr/local/lib/ollama/cuda_v13/libggml-cuda.so
export LD_LIBRARY_PATH=/usr/local/lib/ollama:/usr/local/lib/ollama/cuda_v13
export CUDA_VISIBLE_DEVICES=0

/usr/local/lib/ollama/llama-server \
  --model /usr/share/ollama/.ollama/models/blobs/sha256-22c9979ce4fbcdc5acdc310c6641c32797eff1aa980b8f7a2db8a8ea23429a48 \
  --host 0.0.0.0 \
  --port 11435 \
  --no-webui \
  --rerank \
  --ctx-size 8192 \
  --n-gpu-layers 99
