# 本地部署、模型配置与界面重构

## Goal

统筹多供应商模型配置、知识问答界面重构、Docker Desktop 部署和 Jenkins 自动化的集成验收。

## Requirements

- 已登录用户可维护自己的多个 OpenAI 兼容 LLM 配置，并选择当前用于问答的配置。
- API Key 不可由页面或接口明文回显，且不得写入浏览器持久化存储、镜像或日志。
- 保持现有 RAG、SSE、引用、配额、文档异步入库和工具确认能力可用。
- 使用现有 Tailwind CSS 体系重设计用户界面。
- 以 Docker Desktop 为本地目标，Jenkins 完成镜像构建、部署、健康检查和失败回滚。

## Acceptance Criteria

- [ ] 用户可在页面新增、编辑、删除、测试和切换多个模型配置；问答请求使用该用户当前激活的配置。
- [ ] 配置 API 遵循用户隔离，响应只返回掩码 API Key；密钥在数据库中加密存放。
- [ ] 核心问答全链路通过本地 Docker Compose 冒烟验证。
- [ ] 新 UI 在桌面及窄屏下可用，覆盖登录、问答、会话、文档、引用、配额和模型配置。
- [ ] Jenkins Pipeline 能在本机 Docker Desktop 构建、部署并检查服务健康，失败时恢复上一个版本。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
