# RAG 评估集 v2 说明

## 构成

- `corpus/`：11 篇语料 = 8 篇领域文档（采购/绩效/薪酬/研发/客服/行政/数据平台/财务共享）+ 3 篇强干扰文档（健康饮食/骑行/英语笔记）
- `questions_seed.jsonl`：50 条种子问句（人工编写，含参考答案）
- `questions_v2.jsonl`：由 `python -m eval.gen_dataset` 校验后生成的正式评估集

## 字段

每行：`{"id","q","gold_docs","gold_keywords","reference_answer","type","difficulty"}`

- `gold_docs`：答案所在的文档（列表，多文档题用于 comparison/summary）
- `gold_keywords`：gold chunk 运行时解析依据——**chunk 属于 gold_docs 且内容含任一关键词即判为 gold chunk**（与 chunk_size 无关，跨切分参数稳健）
- `reference_answer`：参考答案，供"上下文召回"指标拆论断比对
- `type`：factual / list / comparison / summary
- `difficulty`：easy / hard（hard = 同义改写、数值映射、否定判断、单文档聚合、多文档对比，占比 ≥40%）

## 干扰设计

- 财务簇：采购付款（15 个工作日）vs 报销审核（3 个工作日）vs 备用金（2 万/30 天）——时限/额度易混
- SLA 簇：研发告警（5 分钟）vs 客服工单（2 小时）vs 投诉（4 小时）vs 重大客诉报告（24 小时）
- 来访簇：行政访客登记 vs 客服客户来访预约
- 密级簇：数据平台 L2 看板分享限制

## 构建与校验

```powershell
# 校验 + 生成 questions_v2.jsonl（无需 LLM）
python -m eval.gen_dataset

# 用 DeepSeek 重新生成参考答案后再校验（需 DEEPSEEK_API_KEY）
python -m eval.gen_dataset --llm
```

校验规则：gold 文档必须存在于语料库；每个 gold_keyword 必须出现在至少一篇 gold_doc 中（忽略空白差异）；参考答案长度 [10,600] 且关键词覆盖率 ≥50%（告警）；难例占比 ≥40%（强制）。

## 人工校验记录

- 2026-10-12：50 条种子问句由人工依据语料逐条编写，参考答案人工撰写；关键词与语料原文逐条核对（脚本校验通过）。
