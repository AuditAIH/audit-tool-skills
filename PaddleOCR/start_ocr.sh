#!/bin/bash
################################################################################
# 使用说明：
# 0. 请先用ollama执行OCR模型拉取 
#    ollama pull AuditAid/PaddleOCR-VL-1.6-0.9B
# 1. 顶部 LLAMA_PORT / OCR_PORT 修改端口
# 2. llama-server 启动参数段可自行追加CUDA、显存、加速相关参数
#    常用加速参数参考：
#    开启调试  --verbose
# 3. 日志直接输出控制台，建议用systemd journal接管
################################################################################
# 端口配置区
LLAMA_PORT=8118
OCR_PORT=8080

# 日志前缀区分
LOG_LLAMA="[LLAMA-SERVER]"
LOG_OCR="[PADDLE-OCR]"
MAIN_PID=$$
RESTART_DELAY=3

# 判断主进程是否存活
main_alive() {
    kill -0 "$MAIN_PID" 2>/dev/null
}

# Llama 保活逻辑
run_llama() {
    local svc_pid
    # 收到停止信号时清理当前llama-server进程
    trap '
        [ -n "$svc_pid" ] && kill -TERM "$svc_pid" 2>/dev/null
        sleep 1
        [ -n "$svc_pid" ] && kill -9 "$svc_pid" 2>/dev/null
        exit 0
    ' SIGTERM SIGINT

    while main_alive; do
        echo "$LOG_LLAMA ========== 启动 llama-server port:$LLAMA_PORT =========="
        # CUDA环境变量
        export GGML_BACKEND_PATH=/usr/local/lib/ollama/cuda_v13/libggml-cuda.so
        export LD_LIBRARY_PATH=/usr/local/lib/ollama:/usr/local/lib/ollama/cuda_v13
        export CUDA_VISIBLE_DEVICES=0

        # 所有分行参数完全正常识别，shell换行\不丢失参数
        /usr/local/lib/ollama/llama-server \
            --model /usr/share/ollama/.ollama/models/blobs/sha256-e791f710e32aef14c3c0bcdebe54f46883d49e8882ad554dab11f74f584c9387 \
            --mmproj /usr/share/ollama/.ollama/models/blobs/sha256-204d757d7610d9b3faab10d506d69e5b244e32bf765e2bab2d0167e65e0a058a \
            --port "$LLAMA_PORT" \
            --host 0.0.0.0 \
            --temp 0 \
            --parallel 12 \
            --flash-attn on \
            -b 2048 2>&1 | while read -r line; do
                echo "$LOG_LLAMA $line"
            done &
        svc_pid=$!
        wait "$svc_pid"

        # 主进程死亡则停止重启
        if ! main_alive; then
            echo "$LOG_LLAMA 主进程终止，不再重启"
            break
        fi
        echo "$LOG_LLAMA 进程退出，${RESTART_DELAY}s后自动重启"
        sleep "$RESTART_DELAY"
    done
}

# OCR保活逻辑
run_ocr() {
    local svc_pid
    trap '
        [ -n "$svc_pid" ] && kill -TERM "$svc_pid" 2>/dev/null
        sleep 1
        [ -n "$svc_pid" ] && kill -9 "$svc_pid" 2>/dev/null
        exit 0
    ' SIGTERM SIGINT

    while main_alive; do
        echo "$LOG_OCR ========== 启动 PaddleOCR port:$OCR_PORT =========="
        source /root/PaddleOCR-VL-1.6-gpu/venv/bin/activate
        paddlex --serve \
            --pipeline /root/PaddleOCR-VL-1.6-gpu/PaddleOCR-VL-1.6.yaml \
            --port "$OCR_PORT" 2>&1 | while read -r line; do
                echo "$LOG_OCR $line"
            done &
        svc_pid=$!
        wait "$svc_pid"

        if ! main_alive; then
            echo "$LOG_OCR 主进程终止，不再重启"
            break
        fi
        echo "$LOG_OCR 进程退出，${RESTART_DELAY}s后自动重启"
        sleep "$RESTART_DELAY"
    done
}

# 主进程停止信号处理
clean_main() {
    echo -e "\n[MAIN] 收到停止信号，关闭全部服务"
    [ -n "$LOOP_LLAMA_PID" ] && kill -TERM "$LOOP_LLAMA_PID" 2>/dev/null
    [ -n "$LOOP_OCR_PID" ] && kill -TERM "$LOOP_OCR_PID" 2>/dev/null
    wait "$LOOP_LLAMA_PID" "$LOOP_OCR_PID"
    echo "[MAIN] 所有服务已正常停止"
    exit 0
}
trap clean_main SIGINT SIGTERM SIGHUP

# 后台启动两个保活循环
run_llama &
LOOP_LLAMA_PID=$!
run_ocr &
LOOP_OCR_PID=$!

echo "==================== AI服务启动完成 ===================="
echo "Llama端口: $LLAMA_PORT | OCR端口: $OCR_PORT"
echo "systemctl stop 可完整关闭，无无限重启残留"
echo "========================================================"

# 阻塞等待子循环，交由systemd托管主进程
wait
