# llama.cpp rerank_for_dify

## 快速开始 （Quick Start） 直接调用ollama的二进制程序，没有的话会自动下载ollama

```
# 下载脚本到本地文件 startup_llama.cpp.sh
# 如需代理请在github的http前面追加https://gh-proxy.org/https://raw.git...
wget "https://raw.githubusercontent.com/AuditAIH/audit-tool-skills/main/Rerank/startup_llama.cpp.sh" -O startup_llama.cpp.sh
# 运行脚本
bash startup_llama.cpp.sh
```

## 或从源码手动编译
```
# 1、下载编译工具
sudo apt update && apt install -y cmake gcc g++ libcurl4-openssl-dev
```
如需下载cuda，apt install -y nvidia-cuda-toolkit [参考NVDIA官网](https://developer.nvidia.com/CUDA-TOOLKIT-ARCHIVE)
```
# 下载最新版本的llama.cpp (指定截止2025.12.24的标签）
git clone --depth 1 https://github.com/ggml-org/llama.cpp # -b b7524 #指定版本

cd llama.cpp

 # -DGGML_NATIVE=OFF 非本地GPU构建，可以迁移到别的不同GPU
cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF

# 2. 并行编译（核心加速！-j 后接线程数，$(nproc) 自动获取 CPU 核心数）
cmake --build build --config Release -j$(nproc)
```
编译完成后，运行
`./build/bin/llama-server -h` 测试

# 请求方式
```
curl -X POST http://host.docker.internal:11435/v1/rerank \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3-reranker",
    "query": "Apple",
    "documents": [
      "apple",
      "banana",
      "fruit",
      "vegetable"
    ]
  }'
```

# 集成Dify：
https://github.com/AuditAIH/dify-official-plugins/blob/ollama_rerank_readme/models/ollama/README.md

#### 5. Integrate Ollama Rerank in Dify
Hint: ollama officially does not support rerank models, please try locally deploying tools like vllm, llama.cpp, tei, xinference, etc., and fill in the complete URL ending with "rerank". Deployment reference [llama.cpp deployment tutorial for Qwen3-Reranker](https://github.com/AuditAIH/rerank_for_dify)

In `Settings > Model Providers > Ollama`, fill in:

<img width="2264" height="1478" alt="image" src="https://github.com/user-attachments/assets/b827c485-d943-4599-93e6-9e63c8b8c434" />


- Model Name：`Qwen3-Reranker`
- Base URL: `http://<your-ollama-endpoint-domain>:11434` or Ending with “rerank” `http://<your-ollama-endpoint-domain>:11434/api/rerank`
- Enter the base URL where the Ollama service is accessible.
- If Dify is deployed using Docker, consider using the local network IP address, e.g., `http://192.168.1.100:11434` or `http://172.17.0.1:11434` or `http://host.docker.internal:11434` to access the service.
- from llama.cpp , consider using the local network `http://host.docker.internal:11435/v1/rerank`
- Model Type: `Rerank`
- Model Context Length: `4096`

Click "Add" to use the model in the application after verifying that there are no errors.

