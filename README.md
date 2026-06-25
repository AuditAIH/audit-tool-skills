# audit-tool-skills

Claude Code 技能合集插件，包含两个技能：

- **audit** — 代码内审：检查 bug、安全、性能与质量问题
- **tools** — 常用工具技能

## 安装

在 Claude Code 会话中执行：

```shell
/plugin marketplace add <你的GitHub用户名>/audit-tool-skills
/plugin install audit-tool-skills@audit-tool-skills
/reload-plugins
```

## 使用

```shell
/audit-tool-skills:audit
/audit-tool-skills:tools
```

## 更新

```shell
/plugin marketplace update audit-tool-skills
/reload-plugins
```

## 目录结构

```
audit-tool-skills/
├── .claude-plugin/
│   └── marketplace.json
└── plugins/
    └── audit-tool-skills/
        ├── .claude-plugin/
        │   └── plugin.json
        └── skills/
            ├── audit/
            │   └── SKILL.md
            └── tools/
                └── SKILL.md
```

## License

MIT
