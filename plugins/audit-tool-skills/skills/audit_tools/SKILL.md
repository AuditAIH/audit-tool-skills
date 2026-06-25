---
name: audit_tools
description: 审计工具技能总入口。当用户需要文档解析、数据脱敏等审计辅助工具能力时使用；本技能根据具体需求调度对应工具子目录下的 SKILL.md 与脚本执行。
---

# 审计工具技能（Audit Tools）

## 技能定位

本技能是审计辅助工具能力的**总入口与调度中枢**，与 [[internal-audit]]（内审主技能）平行。它本身不直接执行具体处理，而是：

1. 理解用户的工具需求；
2. 将需求匹配到对应的工具子目录；
3. 调用对应工具的 `SKILL.md`（使用说明）与 `scripts/`（脚本）执行具体工作。

## 工具目录结构

本技能采用「总说明 + 独立工具子目录」组织，每个工具都是一个**独立文件夹**，自带使用说明（`SKILL.md`）与脚本（`scripts/`），可单独使用、单独复制：

```
audit_tools/
├── SKILL.md                    # 本文件（总说明与调度）
├── data-masking/               # 工具：数据脱敏
│   ├── SKILL.md                # 使用说明
│   └── scripts/
│       ├── mask.py             # 脱敏主脚本
│       └── requirements.txt    # 依赖
└── document-parsing/           # 工具：文档解析
    ├── SKILL.md                # 使用说明
    └── scripts/
        ├── parse.py            # 解析主脚本（PDF/Word/Excel/OCR）
        └── requirements.txt    # 依赖
```

## 已有工具清单

| 工具 | 目录 | 用途 | 触发关键词 |
| --- | --- | --- | --- |
| 数据脱敏 | [`data-masking/`](data-masking/SKILL.md) | 对 PII（身份证、手机号、银行卡等）做不可逆脱敏 | 脱敏、掩码、去隐私、PII、敏感信息 |
| 文档解析 | [`document-parsing/`](document-parsing/SKILL.md) | 从 PDF/Word/Excel/图片提取文本与结构化内容 | 解析、提取、PDF、Excel、Word、OCR、发票、台账 |

> 后续新增工具时，在 `audit_tools/` 下新建独立子目录（含 `SKILL.md` + `scripts/`），并在本表登记。

## 调度说明（如何使用本技能）

当用户描述一个工具需求时：

1. 提取需求中的**关键词**（如"脱敏""解析 PDF""提取发票字段"等）；
2. 对照上方工具清单定位所属工具，打开其 `SKILL.md` 了解使用方式与规则；
3. 按需调用 `scripts/` 下的脚本执行，或按 `SKILL.md` 的方法论手工处理；
4. 若无匹配工具，告知用户暂未覆盖，可按通用方法论提供框架性协助。

### 关键词映射示例

- "脱敏 / 掩码 / 隐去身份证 / 手机号打码 / 隐私保护" → `data-masking`
- "解析 PDF / 提取 Excel 台账 / 读取 Word / OCR 发票 / 抽取表格" → `document-parsing`

## 与内审主技能的协作

[[internal-audit]] 在执行审计程序时，常需先解析用户上传的材料（报销台账、发票、行程单等）。典型协作链路：

1. 用 `document-parsing` 将原始文档解析为结构化字段；
2. 用 `data-masking` 对含 PII 的材料做脱敏后再共享 / 归档；
3. 将解析后的结构化数据交给 [[internal-audit]] 的审计程序稽核。

## 脚本使用约定

- 每个工具的脚本放在该工具的 `scripts/` 子目录下，**自包含**、不跨工具引用；
- 运行前先安装依赖：`pip install -r scripts/requirements.txt`；
- 脚本默认支持 `--help` 查看用法，优先在**本地**运行以保护敏感数据。
