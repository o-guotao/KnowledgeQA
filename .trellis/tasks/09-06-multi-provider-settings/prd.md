# 模型多供应商配置

## Goal

实现面向登录用户的多 OpenAI 兼容供应商模型配置、密钥保护与连通性验证

## Requirements

- 每个登录用户可创建多个 OpenAI Chat Completions 兼容配置：名称、Base URL、模型名、API Key、超时和可选单价。
- 用户可设置一个当前激活配置；问答只能使用本人激活配置。首次使用没有配置时须给出可行动提示。
- API Key 只在提交时传输，查询接口仅返回掩码、最后更新时间和非敏感字段。
- 供应商 URL 必须为 HTTPS 公网地址；拒绝 localhost、私有/保留地址及含凭据 URL，以降低 SSRF 风险。
- 配置写入需以部署密钥加密；部署密钥仍只来自环境/Jenkins 凭据。现有 DEEPSEEK 环境变量保留为迁移期系统兜底。
- 提供连通性测试，不记录密钥或上游响应正文。

## Acceptance Criteria

- [ ] 完成数据库迁移、后端模型/服务/API 和前端运行时 schema。
- [ ] 任意用户不能读取、修改、删除或使用其他用户配置。
- [ ] API Key 不会通过 REST 响应、异常、日志或浏览器存储泄露。
- [ ] 对话流使用当前激活配置；未配置、无效配置及上游失败可被前端清楚呈现。
- [ ] 支持至少 DeepSeek 和任意符合 OpenAI Chat Completions 协议的供应商。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
