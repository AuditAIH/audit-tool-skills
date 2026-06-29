# dify_tools

[简体中文](#简体中文-中文文档) | [English](#english-version)

## 简体中文（中文文档）

这是一个用于存放与 Dify 相关工具与代码的仓库。该仓库包含三个主要目录：DSL、tools 与 code。

This repository contains tools and code related to Dify. It includes three primary directories: DSL, tools, and code.

**项目结构 / Structure**

- **`dsl`**: 存放 Dify 导出的工作流模板（DSL 文件）。这些文件通常是 Dify 平台导出的工作流定义或模板，可用于在 Dify 中导入、复现或分享流程。
- **`tools`**: 存放封装好的可执行工具或模块。这里的内容通常是已经打包、可以直接运行或被工作流调用的二进制、脚本或可复用工具库。
- **`code`**: 存放工具或工作流节点的源码。包含实现逻辑、依赖说明和测试等，方便开发、调试和扩展。

**说明 / Notes**

- DSL: Dify 导出的工作流模板，代表流程定义、节点参数与连线关系，适合导入到 Dify 平台进行执行或编辑。
- Tool: 封装好的可执行代码或服务，能被工作流节点调用以完成具体任务（如调用模型、处理数据、外部 API 集成等）。
- Code: 针对工具或节点的源码级实现，便于本地开发、单元测试与复用。

如果你需要开始使用或开发：

1. 查看 [dsl](dsl) 中的模板以了解已有工作流。
2. 在 [tools](tools) 中寻找可直接运行或被引用的工具。
3. 在 [code](code) 中查看或修改源码，然后按需打包到 `tools` 中。

---

## English Version

**dify_tools** is a repository designed to store tools and code related to Dify. The repository is organized into three main directories: DSL, tools, and code, each serving a specific purpose in the Dify workflow ecosystem.

**Project Structure / 项目结构**

- **`dsl`**: Contains Dify-exported workflow templates (DSL files). These files represent workflow definitions, node parameters, and connection relationships exported from the Dify platform. They can be imported back into Dify for execution, editing, or sharing across teams.
- **`tools`**: Houses packaged, runnable tools and modules. This directory contains pre-built binaries, scripts, or reusable libraries that can be directly executed or invoked by workflow nodes to perform specific tasks.
- **`code`**: Holds source code for tools and workflow nodes. This includes implementation logic, dependency specifications, unit tests, and documentation for easy local development, debugging, and extension.

**About Each Directory / 关于每个目录**

- **DSL (Domain Specific Language)**: Dify-exported workflow templates that define the complete flow structure, including node configurations, parameters, and connections. These are ideal for importing into Dify to reproduce or execute pre-defined workflows.
- **Tool (Executable Packages)**: Self-contained, executable code or services that workflow nodes can invoke to accomplish specific tasks such as model calls, data processing, external API integrations, and more.
- **Code (Source Implementation)**: The underlying source code for tools and workflow nodes, designed for local development, unit testing, version control, and component reuse across projects.

**Getting Started / 快速开始**

1. **Review Workflow Templates**: Explore the [dsl](dsl) folder to understand the available workflow templates and use cases already in the repository.
2. **Discover Available Tools**: Browse the [tools](tools) directory to find ready-to-use tools, integrations, or utilities that can be directly invoked or referenced.
3. **Develop & Extend**: Check the [code](code) directory to view, modify, or extend the source implementations. Once ready, package your extensions into `tools` for production use.

**Workflow / 工作流**

Typically, the workflow in this repository follows this pattern:

1. **Development**: Write and test source code in the [code](code) directory.
2. **Packaging**: Once verified, package the code into executable tools and place them in the [tools](tools) directory.
3. **Integration**: Use the tools within Dify workflows or export workflow templates as DSL files to the [dsl](dsl) directory.
4. **Sharing**: Share workflows and tools with your team or community by pushing updates to this repository.

**Safety & Best Practices / 安全与最佳实践**

- Always review script and tool code before execution to ensure security and privacy.
- Run scripts in isolated or controlled testing environments if unsure about their behavior.
- Keep dependencies and tools up-to-date to mitigate security vulnerabilities.
- Use version control to track changes and maintain a clear history of modifications.

**Contributing / 贡献指南**

We welcome contributions! To add new tools, workflow templates, or source code:

1. Organize your content in the appropriate directory (`dsl`, `tools`, or `code`).
2. Include a clear README or documentation describing the purpose, usage, and any dependencies.
3. Test thoroughly before submitting a pull request.
4. Follow the repository's naming conventions and directory structure.
5. Update the main README if your contribution introduces new categories or workflows.

**License & Attribution / 许可和归属**

Please ensure all contributed code and workflows respect original licenses and provide appropriate attribution to authors and sources.

**Support & Questions / 支持与问题**

For questions, issues, or suggestions, please open an issue in the repository or contact the maintainers. We aim to provide timely support and guidance.

欢迎贡献：如需添加新的工具、模板或源码，请按照各目录的用途提交对应内容并附带简单说明。

For contributions in Chinese: 如果您使用中文贡献，请提供相应的中英双语说明。
