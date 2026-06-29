#!/bin/bash
set -euo pipefail

# 彩色日志函数
log_info() {
    echo -e "\033[34m[INFO] $1\033[0m"
}
log_warn() {
    echo -e "\033[33m[WARN] $1\033[0m"
}
log_error() {
    echo -e "\033[31m[ERROR] $1\033[0m"
}
log_success() {
    echo -e "\033[32m[SUCCESS] $1\033[0m"
}

# ====================== 1. 检测NVIDIA GPU & CUDA ======================
log_info "===== 1. 检测 NVIDIA GPU & CUDA 版本 ====="
HAS_GPU=0
CUDA_VERSION=""
CUDA_SHORT=""
if command -v nvidia-smi &> /dev/null; then
    CUDA_VERSION=$(nvidia-smi | grep -oP 'CUDA Version: \K[\d.]+')
    if [[ -n "$CUDA_VERSION" ]]; then
        HAS_GPU=1
        log_success "检测到NVIDIA显卡，CUDA版本：$CUDA_VERSION"
        CUDA_MAJOR=$(echo "$CUDA_VERSION" | cut -d'.' -f1)
        CUDA_MINOR=$(echo "$CUDA_VERSION" | cut -d'.' -f2)
        if [[ "$CUDA_MAJOR" -eq 11 && "$CUDA_MINOR" -ge 8 ]]; then
            CUDA_SHORT="118"
        elif [[ "$CUDA_MAJOR" -eq 12 && "$CUDA_MINOR" -ge 6 && "$CUDA_MINOR" -lt 9 ]]; then
            CUDA_SHORT="126"
        elif [[ "$CUDA_MAJOR" -eq 12 && "$CUDA_MINOR" -ge 9 ]]; then
            CUDA_SHORT="129"
        elif [[ "$CUDA_MAJOR" -eq 13 ]]; then
            CUDA_SHORT="130"
        else
            log_warn "当前CUDA $CUDA_VERSION 无匹配GPU源，切换CPU模式安装Paddle"
            HAS_GPU=0
        fi
        [[ $HAS_GPU -eq 1 ]] && log_info "自动匹配Paddle CUDA源标识：cu$CUDA_SHORT"
    else
        log_warn "nvidia-smi存在，但未读取到CUDA版本，无可用GPU"
    fi
else
    log_warn "未找到 nvidia-smi，无NVIDIA GPU环境"
fi

# ====================== 2. 无GPU交互确认CPU模式 ======================
if [[ $HAS_GPU -eq 0 ]]; then
    read -p "未检测到GPU，是否继续使用CPU版本运行Ollama？(y/n) " CHOICE
    case "$CHOICE" in
        y|Y) log_info "确认使用CPU模式，继续执行脚本" ;;
        n|N) log_info "用户选择退出，脚本终止"; exit 0 ;;
        *) log_error "输入无效，脚本退出"; exit 1 ;;
    esac
fi

# 定义项目绝对路径
if [[ $HAS_GPU -eq 1 ]]; then
    DIR_NAME="PaddleOCR-VL-1.6-gpu"
else
    DIR_NAME="PaddleOCR-VL-1.6-cpu"
fi
FULL_PROJECT_PATH=$(realpath "$DIR_NAME")
YAML_FILE="$FULL_PROJECT_PATH/PaddleOCR-VL-1.6.yaml"
VENV_ACTIVATE="$FULL_PROJECT_PATH/venv/bin/activate"

# ====================== 3. 检测/自动安装uv ======================
log_info -e "\n===== 2. 检测 uv 工具 ====="
if command -v uv &> /dev/null; then
    log_success "uv 已安装，版本：$(uv --version)"
else
    log_warn "未检测到uv，执行官方一键安装脚本"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    log_success "uv 安装完成，刷新环境变量"
    source "$HOME/.cargo/env"
    if command -v uv &> /dev/null; then
        log_success "uv 环境变量刷新成功，当前版本：$(uv --version)"
    else
        log_warn "uv 临时未生效，新开终端可正常使用uv命令"
    fi
fi

# ====================== 4. 检测/自动安装ollama ======================
log_info -e "\n===== 3. 检测 Ollama ====="
if command -v ollama &> /dev/null; then
    log_success "Ollama 已安装，版本：$(ollama --version)"
else
    log_warn "未检测到ollama，执行官方一键安装脚本"
    curl -fsSL https://ollama.com/install.sh | sh
    log_success "Ollama 安装完成，刷新环境变量"
    source /etc/profile
    if command -v ollama &> /dev/null; then
        log_success "Ollama 环境刷新成功，版本：$(ollama --version)"
    else
        log_warn "Ollama 临时未生效，新开终端可正常调用ollama命令"
    fi
fi

# ====================== 5. 拉取Ollama模型 ======================
log_info -e "\n===== 4. 开始拉取模型 AuditAid/PaddleOCR-VL-1.6-0.9B ====="
ollama pull AuditAid/PaddleOCR-VL-1.6-0.9B
PULL_CODE=$?
if [[ $PULL_CODE -ne 0 ]]; then
    log_error "模型拉取失败，退出码：$PULL_CODE"
    exit $PULL_CODE
fi
log_success "模型拉取完成！"

# ====================== 6. 创建项目目录 ======================
log_info -e "\n===== 5. 创建工作目录 $DIR_NAME ====="
if [[ -d "$DIR_NAME" ]]; then
    log_error "文件夹 $DIR_NAME 已存在！请先手动删除该文件夹后再运行脚本"
    log_info "删除命令示例1：rm -rf $DIR_NAME"
    log_info "通用删除命令模板：rm -rf PaddleOCR-VL-1.6-xxx"
    exit 1
else
    mkdir -p "$DIR_NAME"
    log_success "成功创建目录：$FULL_PROJECT_PATH"
fi

# ====================== 7. 创建 Python3.12 venv 虚拟环境 ======================
log_info -e "\n===== 6. 在 $DIR_NAME 内创建 Python3.12 虚拟环境 venv ====="
cd "$DIR_NAME"
uv venv --python 3.12 venv
log_success "Python3.12虚拟环境创建完成，路径：$FULL_PROJECT_PATH/venv"

# ====================== 8. 子shell串行执行全套流程 ======================
log_info -e "\n===== 7. 子shell激活虚拟环境，按顺序执行全套流程 ====="
(
    source venv/bin/activate

    # 步骤1：安装对应Paddle
    if [[ $HAS_GPU -eq 1 ]]; then
        PADDLE_INDEX="https://www.paddlepaddle.org.cn/packages/stable/cu$CUDA_SHORT/"
        INSTALL_PADDLE="uv pip install paddlepaddle-gpu==3.3.1 -i $PADDLE_INDEX"
        log_info "【子shell】步骤1：执行GPU版Paddle安装命令：$INSTALL_PADDLE"
        $INSTALL_PADDLE
    else
        PADDLE_INDEX="https://www.paddlepaddle.org.cn/packages/stable/cpu/"
        INSTALL_PADDLE="uv pip install paddlepaddle==3.3.0 -i $PADDLE_INDEX"
        log_info "【子shell】步骤1：执行CPU版Paddle安装命令：$INSTALL_PADDLE"
        $INSTALL_PADDLE
    fi

    # 步骤2：安装paddleocr[all]
    INSTALL_OCR="uv pip install paddleocr[all]"
    log_info "【子shell】步骤2：Paddle安装完成，执行：$INSTALL_OCR"
    $INSTALL_OCR

    # 步骤3：更新pip
    INSTALL_PIP="uv pip install pip"
    log_info "【子shell】步骤3：更新pip工具，执行：$INSTALL_PIP"
    $INSTALL_PIP

    # 步骤4：安装PaddleX serving服务依赖
    SERVING_INSTALL_CMD="paddlex --install serving"
    log_info "【子shell】步骤4：安装PaddleX Serving依赖，执行：$SERVING_INSTALL_CMD"
    $SERVING_INSTALL_CMD

    # 步骤5：导出配置文件
    GET_CFG_CMD="paddlex --get_pipeline_config PaddleOCR-VL-1.6 --save_path ./"
    log_info "【子shell】步骤5：导出PaddleOCR-VL-1.6配置文件至当前目录，执行：$GET_CFG_CMD"
    $GET_CFG_CMD

    # 步骤6：sed替换yaml内genai_config配置
    log_info "【子shell】步骤6：修改PaddleOCR-VL-1.6.yaml genai配置段落"
    sed -i '/    genai_config:/,/      backend: native/c\    genai_config:\n      backend: llama-cpp-server\n      server_url: http://localhost:11434/v1\n      client_kwargs:\n        model_name: "AuditAid/PaddleOCR-VL-1.6-0.9B"' PaddleOCR-VL-1.6.yaml
    log_success "YAML配置文件修改完成"

    # 步骤7：检测8080端口是否占用，从8081顺序顺延查找空闲端口
    TARGET_PORT=8080
    check_port() {
        local port=$1
        ss -tulpn | grep ":$port " >/dev/null 2>&1
        return $?
    }
    if check_port $TARGET_PORT; then
        log_warn "端口8080已被占用，从8081开始依次查找空闲端口"
        TARGET_PORT=8081
        while check_port $TARGET_PORT; do
            TARGET_PORT=$((TARGET_PORT + 1))
        done
    fi
    log_info "最终使用服务端口：$TARGET_PORT"

    # ===================== 关键：启动服务前打印下次启动指引 =====================
    log_info -e "\n==================== 【重要：下次手动启动操作指引】 ===================="
    log_info "1. 激活虚拟环境（复制整条执行）：source $VENV_ACTIVATE"
    log_info "2. 启动OCR推理服务（默认8080）：paddlex --serve --pipeline $YAML_FILE --port 8080"
    log_warn "提示：若8080端口被占用，可自行更换其他端口号"
    log_info "3. API调用参考官方文档：https://www.paddleocr.ai/latest/version3.x/pipeline_usage/PaddleOCR-VL.html#43"
    log_info "=======================================================================\n"

    # 步骤8：启动paddlex服务
    SERVE_CMD="paddlex --serve --pipeline ./PaddleOCR-VL-1.6.yaml --port $TARGET_PORT"
    log_info "【子shell】步骤8：启动OCR推理服务，执行命令：$SERVE_CMD"
    log_info "服务访问地址：http://127.0.0.1:$TARGET_PORT"
    $SERVE_CMD
)
SUB_RET=$?
if [[ $SUB_RET -ne 0 ]]; then
    log_error "虚拟环境内全套流程执行失败，退出码 $SUB_RET"
    exit $SUB_RET
fi

# ====================== Ctrl+C退出服务后再次打印提示（兜底） ======================
log_info -e "\n==================== 服务已停止，再次附上启动指引 ===================="
log_info "1. 激活虚拟环境：source $VENV_ACTIVATE"
log_info "2. 启动OCR服务命令：paddlex --serve --pipeline $YAML_FILE --port 8080"
log_info "API请求文档地址：https://www.paddleocr.ai/latest/version3.x/pipeline_usage/PaddleOCR-VL.html#43"
if [[ $HAS_GPU -eq 1 ]]; then
    log_info "当前环境：GPU加速 | CUDA cu$CUDA_SHORT | paddlepaddle-gpu==3.3.1"
else
    log_info "当前环境：CPU | paddlepaddle==3.3.0"
fi
