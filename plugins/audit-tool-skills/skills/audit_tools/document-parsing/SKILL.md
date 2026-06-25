---
name: document-parsing
description: 文档解析技能。当用户需要从 PDF、Word、Excel、图片（OCR）等文档中提取文本与结构化内容时使用。
---

# 文档解析技能（Document Parsing）

## 适用场景

将各类文档转换为可处理的文本与结构化数据，典型用途包括：单据/凭证提取、报表解析、合同条款抽取、扫描件数字化等。

## 支持文档类型

| 类型 | 扩展名 | 说明 |
| --- | --- | --- |
| PDF | `.pdf` | 文本型 / 扫描型均支持 |
| Word | `.docx` | 段落、表格、样式 |
| Excel | `.xlsx` / `.xls` | 工作表、单元格、表格 |
| 图片 | `.png` / `.jpg` / `.tif` 等 | 通过 OCR 识别 |

## 解析流程

1. **识别类型**：依据扩展名 / 文件头判断文档类型
2. **选择工具**：按类型映射到对应解析工具
3. **提取内容**：抽取文本、表格、图像、元数据
4. **结构化输出**：整理为段落 / 表格 / 键值对的结构化结果

## 工具建议（按可用性选择）

- **PDF**
  - `pdftotext`（poppler）：快速提取文本型 PDF
  - `pdfplumber`：精细表格与版面提取
  - `PyMuPDF` (fitz)：高性能文本 / 图片 / 元数据
- **Word**
  - `python-docx`：段落、表格、样式
- **Excel**
  - `openpyxl`：单元格级读写
  - `pandas`：表格批量转 DataFrame
- **图片 OCR**
  - `Tesseract`（pytesseract）：通用 OCR
  - `PaddleOCR`：中文与复杂版面效果更佳

> 使用前先检测工具是否已安装（`which` / `python -c "import …"`），缺失时提示安装或回退方案。

## 结构化输出

输出建议采用 JSON 或 Markdown，按以下结构组织：

- `paragraphs`：段落文本列表
- `tables`：表格（二维数组 / Markdown 表格）
- `key_values`：键值对（适用于表单、凭证）
- `metadata`：文件名、页数、解析工具、时间

## 表格与版面理解要点

- 优先保留表格的行列结构，避免拍平为纯文本
- 注意合并单元格、跨页表格的还原
- 多栏版面需按阅读顺序重组，避免串列
- 表头识别：首行 / 合并单元格常为表头

## 注意事项

- **扫描件 PDF**：文本层为空，需走 OCR 流程（先转图片再识别）
- **加密 / 受保护文件**：需先解密或取得口令，否则无法解析
- **多语言**：中文优先 PaddleOCR；Tesseract 需安装对应语言包（如 `chi_sim`）
- **乱码**：检查文件编码与字体嵌入，必要时用 OCR 兜底
- **大文件**：分页 / 分块处理，避免一次性载入内存溢出

## 输出校验

- 核对页数、段落数、表格数是否与原文一致
- 抽样比对关键文本，确认无错行 / 漏行
- 对 OCR 结果保留置信度，低置信片段标记复核

## 脚本说明

本工具自带脚本，位于 `scripts/` 下，按需安装依赖后即可运行：

| 文件 | 作用 |
| --- | --- |
| `scripts/parse.py` | 解析主脚本：自动识别 PDF/Word/Excel/图片，统一输出 JSON（paragraphs/tables/key_values/metadata） |
| `scripts/requirements.txt` | 依赖清单（按实际用到的文档类型按需安装） |

### 安装与用法

```bash
# 按需安装依赖（解析哪类装哪类）
pip install -r scripts/requirements.txt
# OCR 还需系统安装 Tesseract 引擎，中文需 chi_sim 语言包

# 自动识别类型并解析，结果输出到 stdout（JSON）
python scripts/parse.py --input 报销台账.xlsx

# 指定类型 + 输出到文件
python scripts/parse.py --input 发票.pdf --type pdf --output result.json

# OCR 解析扫描件 / 图片
python scripts/parse.py --input 扫描发票.png --type ocr
```

输出 JSON 结构：

```json
{
  "metadata": {"file": "...", "type": "...", "tool": "...", "pages": 3},
  "paragraphs": ["..."],
  "tables": [[...]],
  "key_values": {"k": "v"}
}
```

缺哪种依赖会明确提示安装命令；脚本优先用已安装的库（如 PDF 优先 PyMuPDF，回退 pdftotext）。
