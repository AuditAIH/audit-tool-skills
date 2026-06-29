import sys
import json
import uuid
from pathlib import Path
from docx import Document
from docxcompose.composer import Composer
from paddleocr import PaddleOCRVL

# ===================== 固定配置（8118已提前启动，无需改动服务相关） =====================
SERVER_URL = "http://localhost:11434/v1"
VL_MODEL_NAME = "AuditAid/PaddleOCR-VL-1.6-0.9B"
OUT_ROOT = Path("./out")
# ====================================================================================

def merge_official_docx(official_dir: Path, output_docx: str):
    """合并目录下所有docx，保留样式，无分页追加"""
    docx_files = list(official_dir.glob("*.docx"))
    if not docx_files:
        print("提示：没有找到任何DOCX文件，跳过合并", file=sys.stderr)
        return

    # 按文件名末尾数字排序
    def safe_sort_key(p: Path):
        try:
            return int(p.stem.split('_')[-1])
        except:
            return p.name

    docx_files.sort(key=safe_sort_key)
    total = len(docx_files)
    print(f"找到 {total} 个DOCX文件，开始合并...", file=sys.stderr)

    master = Document(str(docx_files[0]))
    composer = Composer(master)
    success = 1

    for file in docx_files[1:]:
        try:
            composer.append(Document(str(file)))
            success += 1
            print(f"已合并: {file.name} ({success}/{total})", file=sys.stderr)
        except Exception as e:
            print(f"合并失败 {file.name}: {e}", file=sys.stderr)

    master.save(output_docx)
    print(f"✅ 合并完成，成功 {success}/{total} 个文件", file=sys.stderr)

def official_way_generate(file_path: str, save_root: Path) -> tuple[str, str]:
    """OCR识别 + 生成合并docx + 生成md"""
    pipeline = PaddleOCRVL(
        vl_rec_backend="llama-cpp-server",
        vl_rec_server_url=SERVER_URL,
        vl_rec_api_model_name=VL_MODEL_NAME
    )
    output = pipeline.predict(file_path)
    file_stem = Path(file_path).stem

    # 分批导出单页docx并合并
    official_dir = save_root / "official_output"
    official_dir.mkdir(parents=True, exist_ok=True)
    for res in output:
        res.save_to_word(str(official_dir))
    final_docx = save_root / f"{file_stem}.docx"
    merge_official_docx(official_dir, str(final_docx))

    # 拼接Markdown内容
    md_blocks = []
    for idx, res in enumerate(output, 1):
        text = res.markdown.get("markdown_texts", "")
        md_blocks.append(f"--- 第{idx}页 ---\n{text}")
    md_content = "\n\n".join(md_blocks) or "未识别到内容"
    md_file = save_root / f"{file_stem}.md"
    md_file.write_text(md_content, encoding="utf-8")

    return str(final_docx.resolve()), str(md_file.resolve())

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(json.dumps({"error": "Usage: python ocrtabledocx.py <file_path>"}), file=sys.stderr)
        sys.exit(1)

    input_file = sys.argv[1]
    try:
        # 创建唯一输出目录
        uuid_dir = OUT_ROOT / str(uuid.uuid4())
        uuid_dir.mkdir(parents=True, exist_ok=True)
        docx_path, md_path = official_way_generate(input_file, uuid_dir)

        # 输出标准JSON结果
        print(json.dumps({
            "status": "success",
            "type": "ocrtable",
            "docx_path": docx_path,
            "md_path": md_path
        }, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False))
