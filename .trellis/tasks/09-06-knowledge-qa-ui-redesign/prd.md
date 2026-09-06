# 知识问答界面重构

## Goal

基于 Tailwind CSS 重构知识库问答的页面与核心交互

## Requirements

- 以现有 Tailwind CSS 组件为基础重构视觉和信息层级，不改变既有业务功能与 API 契约。
- 提供清晰的导航入口访问模型配置；配置管理适配桌面与窄屏。
- 改善对话空状态、流式状态、错误重试、文档上传/处理状态、引用面板和配额提示。
- 保持键盘可操作性、可读对比度和基础 ARIA 标签。

## Acceptance Criteria

- [ ] 登录页与问答工作区视觉统一、响应式可用。
- [ ] 会话、文档、模型设置、引用和用户操作有可理解的加载、空和错误状态。
- [ ] 原有登录、上传、提问、停止、重试、引用和工具确认仍正常工作。
- [ ] 前端 TypeScript 构建通过。

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
