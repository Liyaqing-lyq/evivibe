# EviVibe 使用教程（手把手版）

> 环境要求：Python 3.9+。核心零依赖（纯标准库），离线即可完成评测。

## 0. 安装

```powershell
cd <你的仓库路径>\evivibe
python -m venv .venv
.\.venv\Scripts\Activate.psite       # 若报执行策略错误见下方提示
pip install -e ".[dev]"
```

> PowerShell 激活 venv 报错"禁止运行脚本"时，先执行一次：
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

验证安装：

```powershell
evivibe --version
evivibe selftest      # 离线跑一遍演示评测，应输出 status=accepted score=87.4
```

## 1. 五分钟跑通：评测示例作品

```powershell
evivibe evaluate --work data\works\demo-todo --tasks data\tasks --out report
```

输出两个文件：

| 文件 | 内容 |
|---|---|
| `report\demo-todo.json` | 机器可读完整结果（门槛、评分、缺陷、证据、配置） |
| `report\demo-todo.md` | 人读报告：结论 → 门槛 → 任务表 → 维度分 → 证据链 |

再试一个会被硬门槛拦截的坏作品（观察 exit code = 2）：

```powershell
evivibe evaluate --work data\works\demo-clipboard --tasks data\tasks --out report
```

## 2. 评测你自己的作品

### 2.0 最快路径：复制内置模板

仓库自带 `works\_template\`，四个文件都写好了字段说明，直接复制改名即可：

```powershell
cd "C:\Users\85984\WorkBuddy\2026-10-19-17-15-08\evivibe"
Copy-Item works\_template works\my-app -Recurse
# 编辑 works\my-app\ 下的文件，然后：
evivibe evaluate --work works\my-app --tasks data\tasks --out report
```

> 注意：以 `_` 或 `.` 开头的目录在 `evivibe batch` 中会被自动跳过，所以模板本身不会被误当成作品评测。

模板各文件的作用与填写要点见 [works/README.md](../works/README.md)。

### 2.1 准备作品目录

在任意位置新建 `works\my-app\`，包含：

```
my-app\
├── work.json           # 必需：元数据 + 需求 +（可选）专家标签
├── prompts.jsonl       # 推荐：人机对话轨迹，每行一条 JSON
├── versions.json       # 推荐：版本历史，human_edited 标记人工修改
├── runtime_trace.json  # 回放模式必需：录制的运行证据（见 2.3）
└── <你的源代码文件>
```

**work.json 最小示例**：

```json
{
  "work_id": "my-app",
  "title": "我的作品",
  "requirement": "一个校园二手书交易网站……",
  "expert_labels": { "overall": 75 }
}
```

**prompts.jsonl 示例**（每行一条）：

```json
{"turn": 1, "role": "user", "text": "帮我做一个二手书交易网站"}
{"turn": 2, "role": "user", "text": "报错了：500，帮我修复"}
{"turn": 3, "role": "user", "text": "我测试了一下，可以了"}
```

**versions.json 示例**：

```json
{ "versions": [
  {"version": 1, "label": "initial", "human_edited": false},
  {"version": 2, "label": "css fix", "human_edited": true}
] }
```

### 2.2 任务集

任务集定义"标准用户任务"，模板见 `data\tasks\todo.json`。四个类别：

| category | 用途 |
|---|---|
| `core` | 核心用户任务，失败直接触发硬门槛 |
| `extension` | 扩展任务，失败只扣软分 |
| `robustness` | 异常输入（空数据/重复提交/非法字符），喂给可靠性维度 |
| `persistence` | 刷新后数据还在，可配置为硬门槛 |

步骤（steps）动作支持：`goto / click / fill / expect / expect_absent / reload / screenshot`。

### 2.3 运行证据：两种模式

**模式 A：录制回放（推荐，离线可复现）**

写 `runtime_trace.json`，格式照抄 `data\works\demo-todo\runtime_trace.json`：boot 结果 + 每个任务的步骤成败 + 截图/DOM/日志。可以手工填，也可以先用模式 B 跑一遍自动生成。

**模式 B：Playwright 实跑（需要真实运行的应用）**

```powershell
pip install -e ".[browser]"
playwright install chromium
# 先把你的应用跑起来，例如 http://localhost:5000
evivibe evaluate --work works\my-app --tasks data\tasks --out report --base-url http://localhost:5000
```

### 2.4 评测

```powershell
evivibe evaluate --work works\my-app --tasks data\tasks --out report
```

## 3. 批量评测 + 与专家标签对齐

把多个作品放进 `works\`，每个作品目录带 `expert_labels.overall`：

```powershell
evivibe batch --works works --tasks data\tasks --out report
```

自动输出：每个作品的报告 + `batch_summary.json`（含 Spearman / Kendall / MAE 一致性、对比表）。这是论文 RQ1/RQ2 实验的主入口。

## 4. 消融实验（RQ2 输入阶梯）

逐个关闭输入模态，观察分数与一致性变化：

```powershell
evivibe ablate --work works\my-app --tasks data\tasks --modality task_log
evivibe ablate --work works\my-app --tasks data\tasks --modality screenshot
evivibe ablate --work works\my-app --tasks data\tasks --modality prompt
```

可关闭的模态：`code / screenshot / task_log / prompt / metrics / security_scan`。

## 5. 接入 LLM 评审器

```powershell
$env:OPENAI_API_KEY = "sk-..."
# 可选：自定义端点与模型（任何 OpenAI 兼容接口）
$env:EVIVIBE_LLM_BASE_URL = "https://api.openai.com/v1"
$env:EVIVIBE_LLM_MODEL = "gpt-4o-mini"

evivibe evaluate --work data\works\demo-todo --tasks data\tasks --out report --reviewer llm --strict
```

`--strict`：LLM 结论引用了不存在的证据 ID → 直接丢弃；默认 soft 模式降权 4 倍。

## 6. 自定义配置

```powershell
evivibe evaluate --work works\my-app --tasks data\tasks --config my.json
```

`my.json` 只写要覆盖的字段（深合并），例如把安全门槛关掉、调整权重：

```json
{
  "weights": { "functionality": 0.30, "security": 0.10 },
  "gates": { "block_critical_security": false }
}
```

## 7. 理解报告

- **Verdict**：`ACCEPTED`（有加权分）或 `GATED`（硬门槛失败，分数为 0）
- **Dimension scores**：每维 100 起步，扣 `严重度惩罚 × 置信度`；无发现维度记中性 85 分、置信度 0（提示"证据不足"而非"没有问题"）
- **Findings**：每条缺陷列出严重度、维度、评审器、置信度，以及它引用的证据 ID + 内容摘要 + digest
- **证据附录**：全部证据（任务日志/截图/DOM/静态扫描/指标/Prompt特征），可逐条核对

## 8. 常见问题

| 问题 | 处理 |
|---|---|
| PowerShell 无法激活 venv | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| evaluate 返回码 2 | 作品被硬门槛拦截（预期行为），看报告中 FAIL 的门槛 |
| 想让持久化成为硬门槛 | 配置 `{"gates": {"require_persistence": true}}` |
| LLM 报 no API key | 设置 `OPENAI_API_KEY` 或改用 `--reviewer mock` |
| 想看某维度为何是这个分 | 报告 §4 找该维度 finding，按证据 ID 到附录核对 payload |
