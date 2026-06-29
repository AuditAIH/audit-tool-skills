## 脚本用来在dify工作流界面，批量请求dify工作流导出，并打包成一个压缩包格式，后续使用解压zip文件，并导入dify工作流即可。

### 完全在本地运行，无隐私风险，运行代码前请进行检查，并使用可信ZIP源。

# 如何使用
直接在浏览器控制台运行
# 脚本说明 / Script Overview

简体中文：
该脚本用于在 Dify 工作流界面批量请求工作流导出并打包为 ZIP，之后可解压并导入到 Dify 中。原始脚本已从旧仓库迁移到当前仓库中，代码文件位于 `tools/dify-workflow-batch-export/` 下。

使用前注意：请先审查脚本以确认没有安全或隐私风险，建议在隔离环境中运行。

English:
This script batch-requests Dify workflow exports in the Dify UI and packages them into a ZIP file for later import. The original script has been migrated to this repository; the code files live under `tools/dify-workflow-batch-export/`.

如何使用 / Usage

- 直接在本地仓库中使用（推荐）：打开浏览器控制台，复制并粘贴 `tools/dify-workflow-batch-export/export.js` 的内容并执行。

- 从 GitHub raw 链接获取（指向已迁移的新仓库）：

```
fetch('https://raw.githubusercontent.com/AuditAIH/dify_tools/refs/heads/main/tools/dify-workflow-batch-export/export.js')
  .then(res => res.text())
  .then(script => eval(script));
```

- 或者直接访问源码（新仓库路径）：

https://raw.githubusercontent.com/AuditAIH/dify_tools/refs/heads/main/tools/dify-workflow-batch-export/export.js

示例文件 / Files in this folder

- `export.js` - 批量导出脚本。
- `nozipexport.js` - 不打包为 ZIP 的导出脚本（根据需求可直接修改和运行）。

本地运行建议 / Local-run recommendation

- 推荐将脚本内容审查并直接从本地文件执行，减少网络风险。可以在浏览器开发者工具中打开并执行：复制 `tools/dify-workflow-batch-export/export.js` 的内容到控制台并运行。

贡献 / Contributions

- 若要调整脚本或添加功能，请在本仓库相应目录下提交 PR 或 issue，保留对使用说明的更新。

# 或者复制源码

https://raw.githubusercontent.com/AuditAIH/dify-workflow-batch-export/refs/heads/main/export.js

直接粘贴在控制台运行
<img width="2838" height="1546" alt="image" src="https://github.com/user-attachments/assets/b4e7b6d4-fa37-4c37-9907-febce199d5e9" />
