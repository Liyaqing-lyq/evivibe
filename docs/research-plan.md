# EviVibe 研究计划：研究问题、假设与实验协议

> 本文档把研究思路映射到仓库中可直接执行的实验命令，供论文写作与审稿回复使用。
> 对应论文主线：**构建包含最终作品和运行时证据的 Vibe Coding 评测基准，验证运行时证据与证据约束的多评审器方法能否显著提高自动评价与专家评价的一致性。**

## 1. 研究对象的形式化

一个 Vibe Coding 作品 A = {R, P, T, C, E, U}：

| 符号 | 含义 | 仓库对应 |
|---|---|---|
| R | 任务需求 | `work.json::requirement` |
| P | Prompt 与对话轨迹 | `prompts.jsonl` |
| T | 人机交互与版本演化 | `versions.json` |
| C | 源代码与项目文件 | 作品目录源文件 |
| E | 可执行环境与运行证据 | `runtime_trace.json`（录制）/ Playwright 实录 |
| U | 标准用户任务与人工标签 | `data/tasks/`、`work.json::expert_labels` |

总体评价 `Q = f(F, U, R, S, M, I, H)`，八维加权：功能 F、体验 U、视觉、可靠性 R、安全 S、可维护 M、创新 I、人机协作 H。

## 2. 研究问题（RQ）与可执行实验

### RQ1：传统代码与视觉指标能否预测真实质量？

- **基线A（纯代码指标）**：关闭其他模态。
  ```bash
  evivibe ablate --work <w> --tasks data/tasks --modality task_log
  evivibe ablate --work <w> --tasks data/tasks --modality screenshot
  ```
- **基线B（视觉相似度/VLM 直接打分）**：实现于 `reviewers/llm.py` 的单评审器配置（`reviewers=["ui"]`）。
- **指标**：与 `expert_labels.overall` 的 Spearman ρ、Kendall τ、MAE（`evivibe.metrics`）。

### RQ2：运行时任务证据是否提高自动评价的准确性与稳定性？

- **输入阶梯**：依次叠加 code → +metrics → +security_scan → +task_log → +screenshot → +prompt，每级重跑 `batch`，绘制一致性曲线。
- **消融**：`evivibe ablate --modality <m>` 逐项关闭并记录 ΔSpearman / ΔMAE。

### RQ3：过程特征能否解释质量差异？

- 用 `analyzers/process_features.py` 的 7 个特征（澄清率、报错率、验证率、人工修改率等）对专家分做回归/排序分析（H4）。
- 特征证据已进报告：`Evidence(kind="prompt_trace")`。

## 3. 假设与验证设计

| 假设 | 陈述 | 验证方法 |
|---|---|---|
| H1 | 传统代码指标与专家评价的相关性低于运行时证据 | RQ1 基线 vs 完整配置的相关系数对比 |
| H2 | 运行时证据提升自动-专家一致性 | RQ2 输入阶梯单调性检验 |
| H3 | 多评审器聚合的评分方差低于单一大模型 | 同一作品重复评测 N 次（LLM temperature>0），比较 `metrics.run_variance`；`--strict` 证据绑定进一步压缩方差 |
| H4 | 澄清、验证、迭代行为预测最终质量 | 过程特征回归（RQ3） |
| H5 | 视觉质量与功能质量不一致 | `expert_labels.dimensions` 中 visual 与 functionality 分差分布 + 视觉单评审器排序 vs 专家功能排序 |

## 4. 评审架构

| 评审器 | 输入（模态开关） | 输出 |
|---|---|---|
| functional | task_log | 任务完成度、失败步骤、缺陷严重度 |
| ui | screenshot | 布局、一致性、可访问性 |
| code | code, metrics | 模块性、复杂度、重复、文档 |
| security | security_scan | 漏洞类型、风险等级 |
| process | prompt | 需求表达、验证行为、AI 依赖度 |

所有评审器输出必须引用证据 ID；聚合器（`aggregate.apply_evidence_policy`）负责解析绑定并执行 soft/strict 策略。

## 5. 报告指标

每个实验至少报告：Spearman ρ、Kendall τ、ICC(2,1)、MAE、严重缺陷召回率（`defect_recall`，真值 = `expert_labels.severe_defects`）、误报率（`false_discovery_rate`）、重复运行方差（`run_variance`）、单作品评价耗时与 token 成本。

## 6. 数据规模路线

| 阶段 | 规模 | 目标 |
|---|---|---|
| 试点 | 10–20 作品 | 验证任务、量表、运行环境 |
| 第一轮 | 30–50 作品 | 初版人工标签 + 自动测试结果 |
| 论文级 | 80–150 作品 | 模型比较、消融、跨任务泛化 |
| 扩展 | 多课程/多校 | 外部有效性 |

## 7. 风险与控制（已内建到工具）

| 风险 | 控制措施（实现位置） |
|---|---|
| 参赛者针对公开样例优化 | 隐藏任务类别 `hidden` + 异常输入任务（task spec category） |
| 模型偏好视觉精美作品 | 证据绑定 + 硬门槛 + 模态消融可量化视觉偏置 |
| 无依据解释 | `--strict` 丢弃无证据结论；报告逐条展示证据链 |
| 平台复杂度挤压研究 | 零依赖核心 + 录制回放，先数据采集后评审模块 |
