import sys
import os
import tempfile
import subprocess
import json
import re  # 导入正则表达式模块
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import PlainTextResponse, HTMLResponse

# 定义支持的文件类型
SUPPORTED_TYPES = {
    'ocr': {'.png', '.jpg', '.jpeg', '.pdf'},
    'audio': {'.mp3', '.wav', '.flac', '.m4a', '.ogg'},
    'office': {'.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp'},
}

# 定义第五个code - hashcat密码破解功能
HASHCAT_CODE = '''
import subprocess
import sys
import os
import uuid
import io
from contextlib import redirect_stdout
import re

def run_command(cmd):
    """执行命令，返回 (returncode, stdout)"""
    try:
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        return result.returncode, result.stdout
    except Exception as e:
        return -1, f"Command execution error: {e}"

def extract_hash_via_office2john(filepath):
    """使用 office2john.py 提取哈希"""
    office2john_path = "/root/paddleocr_gpu/hashcat-7.1.2/office2john.py"
    cmd = f'python "{office2john_path}" "{filepath}"'
    ret_code, output = run_command(cmd)
    if ret_code == 0:
        return output
    else:
        print(f"Error calling office2john: {output}")
        return None

def identify_hash_type(hash_file_path, hashcat_bin):
    """使用 hashcat --identify 检测哈希类型"""
    identify_cmd = f'"{hashcat_bin}" --identify "{hash_file_path}"'
    ret_code, identify_output = run_command(identify_cmd)
    if ret_code == 0 and identify_output:
        lines = identify_output.strip().split("\\n")
        for line in lines:
            # 查找形如 " 9400 | ..." 的行
            match = re.match(r"^\\s*(\\d+)\\s*\\|", line)
            if match:
                identified_mode = match.group(1)
                print(f"DEBUG: Identified hash type as: {identified_mode}")
                return identified_mode
    print(f"WARNING: Could not identify hash type using --identify. Output: {identify_output}")
    return None

def main_logic(excel_file, usrid=""):
    """
    核心处理逻辑：使用 List.txt 作为密码字典进行破解
    返回精简的结果文本
    """
    if not os.path.isfile(excel_file):
        result = f"错误: 文件 '{excel_file}' 不存在!"
        return result

    # 使用绝对路径
    wordlist = "/root/paddleocr_gpu/hashcat-7.1.2/List.txt"
    hashcat_bin = "/root/paddleocr_gpu/hashcat-7.1.2/hashcat.bin"
    password_dir = "/root/paddleocr_gpu/hashcat-7.1.2/password"
    
    os.makedirs(password_dir, exist_ok=True)

    # 使用临时文件的原始文件名（不含路径和扩展名）作为基础
    original_filename = os.path.basename(excel_file)
    name_part = os.path.splitext(original_filename)[0]
    filename_part = f"{usrid}_{name_part}" if usrid else f"{name_part}"
    hash_filename = f"{filename_part}.hashcat"
    hash_file_path = os.path.join(password_dir, hash_filename)

    # --- 开始构建精简结果 ---
    result = f"文件: {excel_file}\\n"
    result += f"字典: {wordlist}\\n"

    raw_output = extract_hash_via_office2john(excel_file)
    if not raw_output:
        result += "错误: 使用office2john提取哈希失败。\\n"
        return result

    # 解析哈希（取第一个含冒号行的冒号后部分）
    hash_content = ""
    for line in raw_output.strip().split("\\n"):
        if ":" in line:
            hash_content = ":".join(line.split(":")[1:])
            break

    if not hash_content:
        result += "错误: 无法从office2john输出中解析哈希。\\n"
        result += f"原始输出: {raw_output}\\n"
        return result

    # 保存哈希
    with open(hash_file_path, "w") as f:
        f.write(hash_content + "\\n")

    if not os.path.isfile(hashcat_bin):
        result += f"错误: hashcat.bin 不存在于 {hashcat_bin}\\n"
        return result

    # --- 新增：使用 --identify 检测哈希类型 ---
    identified_mode = identify_hash_type(hash_file_path, hashcat_bin)
    if not identified_mode:
        result += "错误: 无法检测哈希类型，退出。\\n"
        return result

    # 使用字典攻击：-a 0 + List.txt
    mode = identified_mode
    crack_cmd = f'"{hashcat_bin}" -m {mode} -a 0 "{hash_file_path}" "{wordlist}"'
    
    ret_code, log_output = run_command(crack_cmd)

    # --- 解析日志，提取关键信息 ---
    password_found = None
    speed_info = "N/A"
    progress_info = "N/A"
    is_existing_password = False
    status_line = "Unknown"
    
    # 检查 hashcat 运行状态
    if "INFO: All hashes found as potfile and/or empty entries!" in log_output:
        is_existing_password = True
        status_line = "Potfile Hit"
    elif "Status...........: Cracked" in log_output:
        status_line = "Cracked"
    elif "Status...........: Exhausted" in log_output:
        status_line = "Exhausted"

    # 统一使用 --show 查询最终结果
    if status_line in ["Potfile Hit", "Cracked"]:
        show_cmd = f'"{hashcat_bin}" -m {mode} --show "{hash_file_path}"'
        _, show_output = run_command(show_cmd)
        if show_output and ":" in show_output:
            parts = show_output.split(":", 1)
            if len(parts) > 1:
                password_found = parts[1].strip()
            else:
                password_found = f"Potfile Read Error: {show_output.strip()}"
        else:
            password_found = f"Potfile Missing Result (Status: {status_line})"

    # 提取速度和进度
    if status_line in ["Cracked", "Exhausted"]:
        speed_match = re.search(r"Speed\\.#[^:]+:\\s*([0-9.,]+\\s*[KMGT]?H/s)", log_output)
        if speed_match:
            speed_info = speed_match.group(1)
        
        progress_match = re.search(r"Progress\\.+:\\s*([0-9,]+/[0-9,]+\\s+\\([0-9.]+\\%\\))", log_output)
        if progress_match:
            progress_info = progress_match.group(1)

    # --- 构建最终结果 ---
    if password_found:
        if is_existing_password:
            result += f"状态: 已存在密码\\n"
            result += f"密码: {password_found}\\n"
        else:
            result += f"状态: 新查找密码\\n"
            result += f"密码: {password_found}\\n"
    else:
        result += f"状态: 未找到密码\\n"
        result += f"原因: 字典已穷尽\\n"
        result += f"可考虑将以下代码（文件哈希）复制给闲鱼请求帮助: `{hash_content}`\\n"

    result += f"速度: {speed_info}\\n"
    result += f"执行: {progress_info}\\n"

    # 保存日志
    log_path = os.path.join(password_dir, f"log_{filename_part}.txt")
    with open(log_path, "w", encoding='utf-8') as f:
        f.write(log_output)

    return result

def main():
    if len(sys.argv) == 1:
        excel_file = "./test01.xlsx"
        usrid = "dlh"
        print(f"提示: 未提供参数，使用默认文件: {excel_file}, usrid: {usrid}")
    elif len(sys.argv) == 2:
        excel_file = sys.argv[1]
        usrid = ""
    elif len(sys.argv) == 3:
        excel_file = sys.argv[1]
        usrid = sys.argv[2]
    else:
        print("用法: python hashcat_script.py [file.xlsx [usrid]]")
        print("示例: python hashcat_script.py report.xlsx user123")
        sys.exit(1)

    result = main_logic(excel_file, usrid)
    import json
    print(json.dumps({"status": "success", "type": "hashcat", "result": result}))

if __name__ == "__main__":
    main()
'''

# 四个脚本的代码字符串
OCR_CODE = '''
import sys
import json
from paddleocr import PaddleOCR

def main():
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: python ocr.py <image_file_path>"}), file=sys.stderr)
        sys.exit(1)

    image_path = sys.argv[1]

    try:
        ocr = PaddleOCR(use_doc_orientation_classify=True, use_doc_unwarping=True)
        result = ocr.predict(image_path)
        texts = [res['rec_texts'] for res in result if 'rec_texts' in res]
        ocr_result = "\\n".join(sum(texts, [])) or "未找到文本识别结果"
        
        print(json.dumps({"status": "success", "type": "ocr", "result": ocr_result}))
    except Exception as e:
        print(json.dumps({"status": "error", "type": "ocr", "error": str(e)}))

if __name__ == "__main__":
    main()
'''

OCR_TABLE_CODE = '''
import sys
import json
from paddleocr import PaddleOCRVL

def main():
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: python ocrtable.py <image_file_path>"}), file=sys.stderr)
        sys.exit(1)

    image_path = sys.argv[1]

    try:
        pipeline = PaddleOCRVL()
        output = pipeline.predict(image_path)
        markdown_contents = []
        for i, res in enumerate(output):
            markdown_dict = res.markdown
            markdown_content = markdown_dict.get('markdown_texts', '')
            markdown_contents.append(f"--- Markdown Content for Result {i+1} ---\\n{markdown_content}")
        markdown_result = "\\n\\n".join(markdown_contents) or "高级解析未获取到内容"
        
        print(json.dumps({"status": "success", "type": "ocrtable", "result": markdown_result}))
    except Exception as e:
        print(json.dumps({"status": "error", "type": "ocrtable", "error": str(e)}))

if __name__ == "__main__":
    main()
'''

ASR_PEOPLE_CODE = '''
import sys
import json
from funasr import AutoModel

def ms_to_hhmmss(ms):
    total_seconds = int(ms // 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def main():
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: python asrpeople.py <audio_file_path>"}), file=sys.stderr)
        sys.exit(1)

    audio_path = sys.argv[1]

    try:
        model = AutoModel(
            model="paraformer-zh",
            disable_update=True, # 禁用更新检查
            vad_model="fsmn-vad",
            punc_model="ct-punc-c",
            spk_model="cam++",
        )
        res = model.generate(input=audio_path, batch_size_s=300, hotword='魔搭')

        if not res:
            result_text = "未识别到语音内容"
        else:
            sentences = [s for item in res for s in item["sentence_info"]]
            colors = ["red", "blue", "green", "purple", "orange", "cyan", "magenta", "darkgreen"]
            result_lines = []
            current = sentences[0] if sentences else None

            for sent in sentences[1:]:
                if sent["spk"] == current["spk"]:
                    current["text"] += sent["text"]
                else:
                    color = colors[current["spk"] % len(colors)]
                    result_lines.append(
                        f'<span style="color:{color};font-weight:bold;">'
                        f'spk{current["spk"]} [{ms_to_hhmmss(current["start"])}]：</span>'
                        f'{current["text"]}'
                    )
                    current = sent

            if current:
                color = colors[current["spk"] % len(colors)]
                result_lines.append(
                    f'<span style="color:{color};font-weight:bold;">'
                    f'spk{current["spk"]} [{ms_to_hhmmss(current["start"])}]：</span>'
                    f'{current["text"]}'
                )
            result_text = "<br><br>".join(result_lines)

        print(json.dumps({"status": "success", "type": "asrpeople", "result": result_text}))
    except Exception as e:
        print(json.dumps({"status": "error", "type": "asrpeople", "error": str(e)}))

if __name__ == "__main__":
    main()
'''

# 假设ASR_CODE是基本语音转文字功能（不识别说话人）
ASR_CODE = '''
import sys
import json
from funasr import AutoModel

def clean_sense_voice_output(text):
    import re
    return re.sub(r'<\|[^|]+\|>', '', text).strip()

def main():
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: python asr.py <audio_file_path>"}), file=sys.stderr)
        sys.exit(1)

    audio_path = sys.argv[1]

    try:
        model = AutoModel(
            model="/root/.cache/modelscope/hub/models/iic/SenseVoiceSmall",
            disable_update=True, # 禁用更新检查
            trust_remote_code=True,
            remote_code="/root/paddleocr_gpu/SenseVoice/model.py",
            vad_model="fsmn-vad",
            vad_kwargs={"max_single_segment_time": 30000},
            device="cuda:0",
        )
        result = model.generate(input=audio_path, use_itn=True, cache_dir="./checkpoint")
        asr_result = clean_sense_voice_output(result[0]["text"])
        
        print(json.dumps({"status": "success", "type": "asr", "result": asr_result}))
    except Exception as e:
        print(json.dumps({"status": "error", "type": "asr", "error": str(e)}))

if __name__ == "__main__":
    main()
'''

def extract_json_from_output(output_str):
    """
    从子进程的输出字符串中提取JSON对象。
    使用更简单的策略，查找第一个以 {"status": 开头的JSON对象。
    """
    # 查找 {"status": 开头的位置
    start_marker = '{"status":'
    start_pos = output_str.find(start_marker)
    
    if start_pos == -1:
        # 没有找到开始标记
        return None

    # 从找到的开始位置，尝试提取一个完整的JSON对象
    # 使用括号计数来找到匹配的结束括号
    brace_count = 0
    start_brace_pos = -1
    for i, char in enumerate(output_str[start_pos:], start_pos):
        if char == '{':
            if brace_count == 0:
                # 记录最外层 { 的位置
                start_brace_pos = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and start_brace_pos != -1:
                # 找到匹配的结束括号
                potential_json_str = output_str[start_brace_pos:i+1]
                try:
                    parsed_json = json.loads(potential_json_str)
                    # 验证是否是我们期望的格式
                    if isinstance(parsed_json, dict) and 'status' in parsed_json and 'type' in parsed_json:
                        return parsed_json
                except json.JSONDecodeError:
                    # 如果解析失败，继续寻找下一个可能的JSON
                    continue
    # 如果循环结束都没找到，返回 None
    return None

def execute_subprocess_with_code(code_string, file_path):
    """执行子进程，使用-c参数执行代码字符串"""
    cmd = ["python", "-c", code_string, file_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        
        if result.returncode == 0:
            # 尝试从混合输出中提取JSON
            json_result = extract_json_from_output(result.stdout)
            
            if json_result:
                if json_result.get("status") == "success":
                    return json_result.get("result", "")
                else:
                    error_msg = json_result.get("error", "未知错误")
                    print(f"子进程执行失败: {error_msg}")
                    return f"执行失败: {error_msg}"
            else:
                # 如果找不到有效的JSON，说明子进程可能出错或输出格式异常
                print(f"子进程输出中未找到有效的JSON结果: {result.stdout}")
                return f"输出格式错误或未找到结果: {result.stdout[:200]}..." # 只显示前200个字符

        else:
            print(f"子进程执行失败，返回码: {result.returncode}, 错误: {result.stderr}")
            return f"执行失败，返回码: {result.returncode}"
    except subprocess.TimeoutExpired:
        print(f"子进程执行超时")
        return "执行超时"
    except Exception as e:
        print(f"执行子进程时异常: {str(e)}")
        return f"执行异常: {str(e)}"

def is_office_file(filename):
    """检查是否为Office文件"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in SUPPORTED_TYPES['office']

def decrypt_office_file(file_path, user_id='test'):
    """
    解密Office文件
    使用hashcat进行密码破解
    """
    try:
        result = execute_subprocess_with_code(HASHCAT_CODE, file_path)
        return result
    except Exception as e:
        print(f"解密失败: {str(e)}")
        return None

app = FastAPI(title="OCR与语音识别API")

@app.post("/", response_class=PlainTextResponse)
async def process_request(
    text: str = Form(...),
    file: UploadFile = File(...)
):
    ext = os.path.splitext(file.filename)[1].lower()
    temp_path = None
    response = None

    try:
        # 1. 创建临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_path = temp_file.name

        # 2. 根据文件类型分类处理
        if is_office_file(file.filename):
            # Office文件处理
            print(f"检测到Office文件: {file.filename}，开始解密...")
            decryption_result = decrypt_office_file(temp_path, 'test')
            if decryption_result:
                print("Office文件解密成功")
                response = PlainTextResponse(str(decryption_result), status_code=200)
            else:
                print("Office文件解密失败或无需解密")
                response = PlainTextResponse("暂不支持该功能", status_code=200)

        elif ext in SUPPORTED_TYPES['ocr']:
            # OCR文件处理
            if text == "空白提问":
                result = execute_subprocess_with_code(OCR_CODE, temp_path)
                response = PlainTextResponse(result, status_code=200)
            else:
                result = execute_subprocess_with_code(OCR_TABLE_CODE, temp_path)
                response = PlainTextResponse(result, status_code=200)

        elif ext in SUPPORTED_TYPES['audio']:
            # 音频文件处理
            if text == "空白提问":
                result = execute_subprocess_with_code(ASR_CODE, temp_path)
                response = PlainTextResponse(result, status_code=200)
            else:
                result = execute_subprocess_with_code(ASR_PEOPLE_CODE, temp_path)
                response = HTMLResponse(result, status_code=200)
        
        else:
            response = PlainTextResponse(f"不支持的文件类型: {ext}", status_code=200)

    except Exception as e:
        error_msg = f"处理请求时出错: {str(e)}"
        print(error_msg)
        response = PlainTextResponse(error_msg, status_code=500)

    finally:
        # 3. 清理临时文件
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9006)