# EviVibe（中文说明）

**面向 Vibe Coding 软件作品的证据约束多维评测框架。**

> Vibe Coding = 人与生成式 AI 通过自然语言、示例、截图和多轮对话**共同创作完整软件作品**——而不是只生成一个能通过单元测试的函数。

EviVibe 评价的是完整作品：需求、Prompt 轨迹、版本历史、源代码、运行系统与标准用户任务，并输出**可追溯的质量结论**——每一分扣分对应一个缺陷，每个缺陷对应机器采集的证据。

## 与前人工作的关系

> ViBench（CAIS '26，Replit 等）与 Replit 的 VibeBench 评测的是**AI agent** 从 Prompt 造应用的能力（Pass@1、agent 可靠性）；EviVibe 评测的是**人机共创的完整作品**——学生与开发者真实提交的产物——采用证据约束的多评审器方法，并把人机协作过程纳入质量模型。研究对象、方法与问题均不同，互为补充。

## 核心创新（面向论文贡献）

1. **证据绑定评审（Evidence-Bound Review）**：LLM 评审器的每个结论必须引用确定性探针采集的证据 ID；引用不存在证据的结论被降权（soft）或直接丢弃（strict），从机制上抑制评分漂移与无依据解释。
2. **两段式评价协议**：硬门槛（启动、核心任务、高危安全、数据持久化）不通过即拒评，杜绝"高分平均掉致命缺陷"；通过后进入八维加权软评分。
3. **过程感知维度**：从 Prompt 轨迹与版本历史提取澄清率、报错率、人工验证率、手工修改率等可解释特征，将人机协作过程纳入质量模型。
4. **置信度加权多评审器聚合**：功能 / UI / 代码 / 安全 / 过程五类评审器 + 方差度量，支持 H3（多评审器方差低于单一 LLM）的实验验证。
5. **模态消融开关**：code / screenshot / task_log / prompt / metrics / security_scan 六种输入可独立关闭，一条命令完成 RQ2 的输入阶梯实验。
6. **录制-回放证据机制**：运行时证据可录制后离线确定性回放，使评测可复现、可入库、可在 CI 中运行。

## 快速开始

```bash
pip install -e ".[dev]"        # 核心零依赖（纯标准库）
evivibe selftest             # 离线演示评测，无需网络与 LLM
pytest -v                      # 全量测试
```

评测示例作品：

```bash
evivibe evaluate --work data/works/demo-todo --tasks data/tasks --out report/
```

批量评测并与专家标签对齐（输出 Spearman / Kendall / MAE）：

```bash
evivibe batch --works data/works --tasks data/tasks --out report/
```

消融实验（关闭任务日志输入，观察分数变化）：

```bash
evivibe ablate --work data/works/demo-todo --tasks data/tasks --modality task_log
```

接入 LLM 评审器（OpenAI 兼容接口）：

```bash
export OPENAI_API_KEY=sk-...
evivibe evaluate --work data/works/demo-todo --tasks data/tasks \
                    --reviewer llm --strict
```

## 质量模型

| 维度 | 证据来源 |
|---|---|
| 功能正确性 | 标准用户任务执行日志、步骤成功率 |
| 用户体验 | 任务耗时、步骤摩擦、异常提示 |
| 视觉与交互 | 截图（多视口）、DOM 溢出/可访问性检查 |
| 可靠性 | 异常输入任务（空数据、重复提交、非法字符） |
| 安全性 | 静态扫描（eval、硬编码密钥、XSS sink 等） |
| 可维护性 | 复杂度、重复率、注释率、依赖清单、测试 |
| 创新性 | 需求差异 + 专家盲评标签 |
| 人机协作 | Prompt 轨迹与版本历史的过程特征 |

评分机制：`Q = Σ w_d · score_d`，维度分 = 100 − Σ(严重度惩罚 × 置信度)，可选与评审器先验分按小权重融合。权重、门槛、惩罚均由 JSON 配置，全流程可复现。

详细研究问题、假设与实验协议见 [docs/research-plan.md](docs/research-plan.md)，
手把手操作教程见 [docs/usage.zh-CN.md](docs/usage.zh-CN.md)。

## 系统架构图

用浏览器打开 [docs/architecture.html](docs/architecture.html) 即可查看完整的评测流水线架构图：
作品输入 → 确定性探针 → 证据池 → 多评审器 → 硬门槛 → 置信度聚合 → 报告输出。
单文件、离线可用，无需起服务；机器可读的图定义见 `docs/architecture.spec.json`。

## 许可

MIT。
