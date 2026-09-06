# Docker 与 Jenkins 本地自动部署

## Goal

验证完整功能并提供 Docker Desktop 与 Jenkins 本地镜像构建、部署、健康检查和回滚流程

## Requirements

- 在 Docker Desktop 本机运行整个应用栈并记录环境前置条件和验证证据。
- Docker 构建应可重复，启动顺序、迁移、健康检查与持久卷明确。
- 提供 Jenkins Pipeline：校验、构建前后端镜像、以构建标识标记、Compose 部署、健康检查和回滚。
- Jenkins 凭据管理部署密钥与初始化变量，Pipeline 日志不得打印敏感信息。

## Acceptance Criteria

- [ ] `docker compose up --build` 后依赖服务、后端、Worker 与前端均正常运行。
- [ ] 健康检查可验证后端和前端；可执行登录、上传和问答冒烟测试。
- [ ] Jenkins 在具备 Docker Desktop 访问权限的节点上可一键部署。
- [ ] 部署失败时恢复上一个成功镜像标签，并保留诊断日志。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
