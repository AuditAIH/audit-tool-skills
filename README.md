# audit-tool-skills

审计技能合集，面向 Claude Code / OpenClaw 等 Agent 的技能（Skill）仓库。包含两大技能：

- **audit_tools** — 审计工具技能（总入口）：数据脱敏 `data-masking`、文档解析 `document-parsing`，每个工具都是独立文件夹，自带使用说明 `SKILL.md` 与脚本 `scripts/`。
- **internal-audit** — 内审技能（总入口）：内审方法论 + 审计程序调度（含财务报销管理等已开发程序）。

仓库同时提供两种使用方式：**Claude Code 插件市场**安装，或 **OpenClaw 直接复制技能目录**。

---

## 目录结构

```
audit-tool-skills/
├── .claude-plugin/
│   └── marketplace.json              # Claude Code 插件市场清单
├── plugins/
│   └── audit-tool-skills/
│       ├── .claude-plugin/
│       │   └── plugin.json           # 插件清单
│       └── skills/
│           ├── audit_tools/          # ── 技能一：审计工具（总说明）
│           │   ├── SKILL.md          #   总入口与调度说明
│           │   ├── data-masking/     #   工具：数据脱敏（独立文件夹）
│           │   │   ├── SKILL.md
│           │   │   └── scripts/
│           │   │       ├── mask.py
│           │   │       └── requirements.txt
│           │   └── document-parsing/ #   工具：文档解析（独立文件夹）
│           │       ├── SKILL.md
│           │       └── scripts/
│           │           ├── parse.py
│           │           └── requirements.txt
│           └── internal-audit/       # ── 技能二：内审（总入口）
│               ├── SKILL.md
│               └── 审计程序/
│                   ├── 101-财务模块.md
│                   └── 10101-财务报销管理.md
├── README.md
├── LICENSE
└── .gitignore
```

> 每个工具 / 技能都是**独立文件夹**，内含 `SKILL.md`（怎么用）与必要的 `scripts/`（有哪些脚本）。可整体使用，也可单独取用其中几个。

---

## 方式一：Claude Code 使用（插件市场安装）

适合 Claude Code 用户，通过插件市场一键安装并随版本更新。

### 安装

在 Claude Code 会话中执行：

```shell
/plugin marketplace add AuditAIH/audit-tool-skills
/plugin install audit-tool-skills@audit-tool-skills
/reload-plugins
```

### 调用

安装后技能带插件命名空间前缀：

```shell
/audit-tool-skills:audit_tools        # 审计工具总入口
/audit-tool-skills:internal-audit     # 内审总入口
```

Claude 也会根据你的描述**自动触发**对应技能（如"帮我脱敏这份文件""解析这个 Excel 台账""审一下报销单"）。

### 更新

```shell
/plugin marketplace update audit-tool-skills
/reload-plugins
```

---

## 方式二：OpenClaw 使用（克隆 + 复制技能目录）

适合 OpenClaw 或任何"按目录加载 `~/.openclaw/skills/<技能名>/SKILL.md`"的 Agent。流程：克隆仓库到暂存目录 → 把需要的技能文件夹复制（覆盖）到 `~/.openclaw/skills/`。

### 1. 克隆仓库（先暂存）

```bash
git clone https://github.com/AuditAIH/audit-tool-skills.git
cd audit-tool-skills
```

仓库内技能源目录位于：

```
plugins/audit-tool-skills/skills/audit_tools/       # 审计工具技能
plugins/audit-tool-skills/skills/internal-audit/    # 内审技能
```

### 2. 复制技能到 OpenClaw（可全复制，也可只复制其中几个）

OpenClaw 从 `~/.openclaw/skills/<技能名>/SKILL.md` 加载技能。把对应技能文件夹复制过去，**已存在则覆盖**：

```bash
# 准备目标目录
mkdir -p ~/.openclaw/skills

# —— 复制两个技能（全部）——
cp -rf plugins/audit-tool-skills/skills/audit_tools      ~/.openclaw/skills/
cp -rf plugins/audit-tool-skills/skills/internal-audit   ~/.openclaw/skills/
```

或**只复制其中一个 / 其中几个**：

```bash
# 只要内审技能
cp -rf plugins/audit-tool-skills/skills/internal-audit ~/.openclaw/skills/

# 只要审计工具里的某个工具（data-masking）作为独立技能
cp -rf plugins/audit-tool-skills/skills/audit_tools/data-masking ~/.openclaw/skills/
```

> 复制时目标名就是技能名（`audit_tools`、`internal-audit`、`data-masking`、`document-parsing`）。OpenClaw 扫描 `~/.openclaw/skills/*/SKILL.md` 加载，因此带 `SKILL.md` 的文件夹即可被识别为技能。

### 3. OpenClaw 怎么用

- **自动触发**：在 OpenClaw 对话中描述任务，它会根据各 `SKILL.md` 的 `description` 自动匹配并调用对应技能。例如：
  - "把这份名单里的身份证和手机号脱敏" → 触发 `data-masking`
  - "解析这个 PDF 发票和 Excel 台账" → 触发 `document-parsing`
  - "审一下这批报销单，看看有没有违规" → 触发 `internal-audit`
- **手动调用**：按你的 OpenClaw 版本支持的斜杠命令方式调用对应技能名。
- **运行脚本**：工具类技能（data-masking / document-parsing）的 `scripts/` 下有可直接执行的 Python 脚本，详见各自 `SKILL.md` 的"脚本说明"。

### 4. 后续更新

```bash
cd audit-tool-skills
git pull
# 再次覆盖复制需要的技能
cp -rf plugins/audit-tool-skills/skills/audit_tools    ~/.openclaw/skills/
cp -rf plugins/audit-tool-skills/skills/internal-audit ~/.openclaw/skills/
```

---

## 各技能 / 工具速览

### audit_tools（审计工具总入口）
`skills/audit_tools/SKILL.md` — 总说明与调度，按关键词把需求分发到下面两个工具。

| 工具 | 目录 | 能力 | 脚本 |
| --- | --- | --- | --- |
| 数据脱敏 | `audit_tools/data-masking/` | 对身份证/手机号/银行卡/邮箱/IP 等做不可逆脱敏（掩码/哈希/删除） | `scripts/mask.py` |
| 文档解析 | `audit_tools/document-parsing/` | 从 PDF/Word/Excel/图片(OCR) 提取文本与结构化 JSON | `scripts/parse.py` |

### internal-audit（内审总入口）
`skills/internal-audit/SKILL.md` — 内审方法论 + 审计程序调度。

| 程序 | 路径 | 状态 |
| --- | --- | --- |
| 财务模块（一级索引） | `审计程序/101-财务模块.md` | ✅ |
| 财务报销管理（二级） | `审计程序/10101-财务报销管理.md` | ✅ |
| 人事 / 采购 / 合同 / 资产模块 | — | 规划中 |

---

## License

MIT
