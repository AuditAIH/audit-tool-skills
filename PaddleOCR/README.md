# 快速开始 （Quick Start） 
## 如需代理请在github的http前面追加https://gh-proxy.org/https://raw.git...
```
wget https://raw.githubusercontent.com/AuditAIH/audit-tool-skills/main/PaddleOCR/start_llama_ppocrvl1.6.sh -O start_llama_ppocrvl1.6.sh
bash start_llama_ppocrvl1.6.sh
```
```
# PaddleOCR-VL-1.6 一键自动化部署脚本 start_llama_ppocrvl1.6.sh
## 一、脚本自动完成安装/部署清单
### 1. 环境检测类
1. 自动检测 NVIDIA GPU、读取 CUDA 版本，自动匹配 cu118 / cu126 / cu129 / cu130 源
2. 无 GPU 时交互式询问是否继续使用 CPU 模式
3. 自动检测 uv 包管理器，不存在则执行官方脚本安装并刷新环境变量
4. 自动检测 Ollama，不存在则一键安装 Ollama 大模型运行工具

### 2. Ollama 模型拉取
自动拉取视觉OCR大模型：`AuditAid/PaddleOCR-VL-1.6-0.9B`

### 3. 项目目录创建
根据硬件自动生成对应项目文件夹：
- 有GPU：`PaddleOCR-VL-1.6-gpu`
- 无GPU：`PaddleOCR-VL-1.6-cpu`
文件夹存在则直接退出，提示删除命令避免冲突

### 4. Python 虚拟环境构建
使用 uv 创建独立 Python3.12 虚拟环境 venv，隔离项目依赖，不污染系统Python

### 5. 自动安装全套Python依赖（子shell自动激活环境，无需手动切换）
1. GPU环境：`paddlepaddle-gpu==3.3.1`（自动匹配对应CUDA镜像源）
2. CPU环境：`paddlepaddle==3.3.0`（官方CPU专属源）
3. 完整OCR套件：`paddleocr[all]` 全量OCR依赖
4. 更新虚拟环境内pip工具：`uv pip install pip`
5. PaddleX推理服务插件：`paddlex --install serving`（FastAPI/Uvicorn推理服务）

### 6. 自动生成并修改推理配置文件
1. 执行 `paddlex --get_pipeline_config` 生成 `PaddleOCR-VL-1.6.yaml` 流水线配置
2. sed 自动替换 genai_config 配置段，对接本地 Ollama 11434 服务：
   - backend：llama-cpp-server
   - 服务地址：http://localhost:11434/v1
   - 默认模型：AuditAid/PaddleOCR-VL-1.6-0.9B

### 7. 端口自动适配 & 一键启动推理服务
1. 默认优先使用 8080 端口
2. 8080被占用则自动随机分配 10000~20000 空闲端口
3. 自动执行 `paddlex --serve` 启动HTTP推理API服务
```

## 直接执行二进制程序

```
# 下载并安装ollama
curl -fsSL https://ollama.com/install.sh | sh

# 拉取PaddleOCR-VL-1.6模型
ollama pull AuditAid/PaddleOCR-VL-1.6-0.9B

# 直接启动ollama预编译的二进制文件和相应的OCR模型。
export GGML_BACKEND_PATH=/usr/local/lib/ollama/cuda_v13/libggml-cuda.so
export LD_LIBRARY_PATH=/usr/local/lib/ollama:/usr/local/lib/ollama/cuda_v13
export CUDA_VISIBLE_DEVICES=0

/usr/local/lib/ollama/llama-server \
--model /usr/share/ollama/.ollama/models/blobs/sha256-e791f710e32aef14c3c0bcdebe54f46883d49e8882ad554dab11f74f584c9387 \
--mmproj /usr/share/ollama/.ollama/models/blobs/sha256-204d757d7610d9b3faab10d506d69e5b244e32bf765e2bab2d0167e65e0a058a \
--port 8118 \
--host 0.0.0.0 \
--temp 0

# 加速启动 --temp 0 --parallel 12 --flash-attn on -b 2048

```

## 或从源码编译
```
# 1、下载编译工具
sudo apt update && apt install -y cmake gcc g++ libcurl4-openssl-dev

# 如需下载cuda，apt install -y nvidia-cuda-toolkit [参考NVDIA官网](https://developer.nvidia.com/CUDA-TOOLKIT-ARCHIVE)

# 下载最新版本的llama.cpp
git clone --depth 1 https://github.com/ggml-org/llama.cpp

cd llama.cpp

 # -DGGML_NATIVE=OFF 非本地GPU构建，可以迁移到别的不同GPU
cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=OFF

# 2. 并行编译（核心加速！-j 后接线程数，$(nproc) 自动获取 CPU 核心数）
cmake --build build --config Release -j$(nproc)

编译完成后，运行
./build/bin/llama-server -h 测试

## 下载PaddleOCR-VL1.6模型文件
modelscope download --model PaddlePaddle/PaddleOCR-VL-1.6-GGUF README.md PaddleOCR-VL-1.6-GGUF-mmproj.gguf PaddleOCR-VL-1.6-GGUF.gguf
# 或使用wget下载
# 下载投影文件
wget -c https://www.modelscope.cn/models/PaddlePaddle/PaddleOCR-VL-1.6-GGUF/resolve/master/PaddleOCR-VL-1.6-GGUF-mmproj.gguf
# 下载主模型文件
wget -c https://www.modelscope.cn/models/PaddlePaddle/PaddleOCR-VL-1.6-GGUF/resolve/master/PaddleOCR-VL-1.6-GGUF.gguf

## 启动OCR识别
# 直接启动8118端口
llama-server \
    -m /path/to/PaddleOCR-VL-1.6-GGUF.gguf \
    --mmproj /path/to/PaddleOCR-VL-1.6-GGUF-mmproj.gguf  \
    --port 8118  \
    --host 0.0.0.0 \
    --temp 0
# 或者加速启动
#!/bin/bash
#cd /root/llama.cpp/build/bin || exit
#export LD_LIBRARY_PATH=/usr/local/lib/ollama/cuda_v13:$LD_LIBRARY_PATH
./llama-server \
  -m ./PaddleOCR-VL-1.6-GGUF.gguf \
  --mmproj ./PaddleOCR-VL-1.6-GGUF-mmproj.gguf  \
  --port 8118  \
  --host 0.0.0.0 \
  --temp 0 --parallel 12 --flash-attn on -b 2048

# 直接请求
wget -O ./paddleocr_vl_demo.png https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/paddleocr_vl_demo.png && llama-cli -m ./PaddleOCR-VL-1.6-GGUF.gguf --mmproj ./PaddleOCR-VL-1.6-GGUF-mmproj.gguf -p 'OCR:' --image ./paddleocr_vl_demo.png --single-turn

## 或者从8118端口直接解析
curl -L -o ./paddleocr_vl_demo.png https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/paddleocr_vl_demo.png && \
cat << EOF | curl -s -X POST http://localhost:8118/v1/chat/completions -H "Content-Type: application/json" -d @- | jq -r '.choices[0].message.content'
{
  "model": "paddleocr-vl",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "OCR:"
        },
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/png;base64,$(base64 -w0 ./paddleocr_vl_demo.png)"
          }
        }
      ]
    }
  ],
  "temperature": 0
}
EOF
```

## 或者结合PaddleOCR进行版面解析 (提前安装好PaddlePaddle和PaddleOCR）
### [参考官网安装步骤](https://www.paddleocr.ai/main/quick_start.html)
```
python -m pip install paddlepaddle-gpu==3.3.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu130/
# uv pip install paddlepaddle-gpu==3.3.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu130/
python -m pip install "paddleocr[all]"
# uv pip install "paddleocr[all]"

# 用版面解析前，请先确保按照前序步骤启动好8118端口的vlm后端或安装好ollama并下载好模型。
paddleocr doc_parser --input https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/paddleocr_vl_demo.png --vl_rec_backend llama-cpp-server --vl_rec_server_url http://localhost:8118/v1

paddleocr doc_parser   --input https://paddle-model-ecology.bj.bcebos.com/paddlex/imgs/demo_image/paddleocr_vl_demo.png   --vl_rec_backend llama-cpp-server   --vl_rec_server_url http://localhost:11434/v1   --vl_rec_api_model_name "AuditAid/PaddleOCR-VL-1.6-0.9B"


# [服务化部署，请参考官方](https://www.paddleocr.ai/main/version3.x/pipeline_usage/PaddleOCR-VL.html#441)
paddlex --install serving
paddlex --get_pipeline_config PaddleOCR-VL-1.6

# 替换配置文件，增加8118后端，也可以由ollama的11434接管
sed -i '/genai_config:/,/      backend: native/c\    genai_config:\n      backend: llama-cpp-server\n      server_url: http://localhost:8118/v1' PaddleOCR-VL-1.6.yaml

# 或者直接用ollama的11434端口
ollama pull AuditAid/PaddleOCR-VL-1.6-0.9B

sed -i '/    genai_config:/,/      backend: native/c\    genai_config:\n      backend: llama-cpp-server\n      server_url: http://localhost:11434/v1\n      client_kwargs:\n        model_name: "AuditAid/PaddleOCR-VL-1.6-0.9B"' PaddleOCR-VL-1.6.yaml

# 默认开放在8080端口，请先确保端口不被占用
paddlex --serve --pipeline ./PaddleOCR-VL-1.6.yaml --port 8080

```
