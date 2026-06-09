---
name: periodic-review
description: 每7天审查 .claude 文件——检查过时、冗余、冲突的指令
---

# .claude 文件定期审查

## 规则

**每 7 天自动审查一次 `.claude/` 目录下的所有配置文件，检查是否有过时、冗余或相互冲突的指令。**

审查流程详见 skill [review-claude](../skills/review-claude.md)，核心维度：过时、冗余、冲突、效率。

## 清理原则

- 每条信息只有一个权威来源
- CLAUDE.md 是入口索引，不存细节
- rules/ 是详细行为规范
- skills/ 是执行流程
- memory/ 是临时教训，长期有效的应升级为 rule

## 注意

- 只提建议不动手，等用户确认
- 报告要标出具体文件名和行号
