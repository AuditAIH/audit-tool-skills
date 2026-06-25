#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文档解析主脚本。
支持 PDF / Word(.docx) / Excel(.xlsx) / 图片(OCR)，统一输出 JSON 结构化结果。

用法:
    python parse.py --input 发票.pdf
    python parse.py --input 台账.xlsx --type excel
    python parse.py --input 扫描件.png --type ocr
    python parse.py --input 合同.docx --output result.json

依赖（按需安装，缺哪类装哪类）:
    pip install -r requirements.txt

输出 JSON 结构:
    {
      "metadata": {"file": "...", "type": "...", "tool": "...", "pages": N},
      "paragraphs": [...],
      "tables": [[...], ...],
      "key_values": {"k": "v"}
    }
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _check(cmd):
    return shutil.which(cmd) is not None


def _try_import(name):
    try:
        return __import__(name)
    except ImportError:
        return None


def detect_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext == ".docx":
        return "docx"
    if ext in (".xlsx", ".xls"):
        return "excel"
    if ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"):
        return "ocr"
    raise ValueError(f"不支持的扩展名: {ext}")


def parse_pdf(path):
    out = {"metadata": {"file": path, "type": "pdf"}, "paragraphs": [], "tables": [], "key_values": {}}
    fitz = _try_import("fitz")
    if fitz:
        out["metadata"]["tool"] = "PyMuPDF"
        doc = fitz.open(path)
        out["metadata"]["pages"] = doc.page_count
        for page in doc:
            out["paragraphs"].append(page.get_text("text"))
        return out
    if _check("pdftotext"):
        out["metadata"]["tool"] = "pdftotext"
        res = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True)
        out["paragraphs"] = [p for p in res.stdout.split("\n\n") if p.strip()]
        return out
    raise RuntimeError("PDF 解析需安装 PyMuPDF (pip install pymupdf) 或 poppler 的 pdftotext")


def parse_docx(path):
    docx = _try_import("docx")
    if not docx:
        raise RuntimeError("Word 解析需安装 python-docx (pip install python-docx)")
    d = docx.Document(path)
    paragraphs = [p.text for p in d.paragraphs if p.text.strip()]
    tables = [[cell.text for cell in row.cells] for tbl in d.tables for row in tbl.rows]
    return {
        "metadata": {"file": path, "type": "docx", "tool": "python-docx"},
        "paragraphs": paragraphs,
        "tables": tables,
        "key_values": {},
    }


def parse_excel(path):
    openpyxl = _try_import("openpyxl")
    if not openpyxl:
        raise RuntimeError("Excel 解析需安装 openpyxl (pip install openpyxl)")
    wb = openpyxl.load_workbook(path, data_only=True)
    tables = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            if any(c is not None and str(c).strip() for c in row):
                tables.append([("" if c is None else str(c)) for c in row])
    return {
        "metadata": {"file": path, "type": "excel", "tool": "openpyxl",
                     "sheets": [ws.title for ws in wb.worksheets]},
        "paragraphs": [],
        "tables": tables,
        "key_values": {},
    }


def parse_ocr(path):
    pytesseract = _try_import("pytesseract")
    Image = _try_import("PIL.Image")
    if not (pytesseract and Image):
        raise RuntimeError("OCR 需安装 pytesseract + Pillow，并安装 Tesseract 引擎（中文需 chi_sim 语言包）")
    img = Image.open(path)
    lang = "chi_sim+eng" if _check_tesseract_lang("chi_sim") else "eng"
    text = pytesseract.image_to_string(img, lang=lang)
    return {
        "metadata": {"file": path, "type": "ocr", "tool": "tesseract", "lang": lang},
        "paragraphs": [p for p in text.split("\n") if p.strip()],
        "tables": [],
        "key_values": {},
    }


def _check_tesseract_lang(lang):
    if not _check("tesseract"):
        return False
    try:
        res = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True)
        return lang in res.stdout
    except Exception:
        return False


PARSERS = {"pdf": parse_pdf, "docx": parse_docx, "excel": parse_excel, "ocr": parse_ocr}


def main():
    ap = argparse.ArgumentParser(description="文档解析工具（PDF/Word/Excel/OCR → JSON）")
    ap.add_argument("--input", "-i", required=True, help="输入文件路径")
    ap.add_argument("--type", "-t", choices=["pdf", "docx", "excel", "ocr"],
                    help="指定类型；缺省按扩展名自动识别")
    ap.add_argument("--output", "-o", help="输出 JSON 路径；缺省写 stdout")
    args = ap.parse_args()

    if not os.path.exists(args.input):
        sys.exit(f"文件不存在: {args.input}")

    ftype = args.type or detect_type(args.input)
    try:
        result = PARSERS[ftype](args.input)
    except RuntimeError as e:
        sys.exit(f"解析失败: {e}")

    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"[parse] 已写入 {args.output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
