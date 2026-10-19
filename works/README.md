# works/ — 放置待评测作品

每个子目录 = 一个待评测作品。目录名即 `work_id`。

## 快速开始

```powershell
# 复制模板
Copy-Item works\_template works\my-app -Recurse

# 编辑 my-app 下的文件，然后评测
cd ..
evivibe evaluate --work works\my-app --tasks data\tasks --out report
```

## 目录内文件清单

| 文件 | 必需 | 作用 |
|---|---|---|
| `work.json` | ✅ | 作品元信息、需求描述、专家标签 |
| `prompts.jsonl` | ⭕ | 人机对话轨迹（换行分隔 JSON，每行一轮） |
| `versions.json` | ⭕ | 版本演化记录（用于过程维度） |
| `runtime_trace.json` | ⭕ | 运行时证据；缺失则自动回退到"启动失败"证据 |
| 源代码文件 | ✅ | 直接平铺在目录下（.py/.js/.html 等） |

⭕ = 推荐提供，缺失会使对应维度证据不足而被扣分；这是设计使然——证据缺失即失分。

## runtime_trace.json 的三种获取方式

1. **手写**（最快）：照 `_template/` 里的样例改 task_id、步骤与 success 字段。
2. **录制回放**：用 EviVibe 的录制格式手工整理浏览器 DevTools 的操作序列。
3. **真实执行**：作品能跑起来时，用 `--base-url http://localhost:PORT` 让 EviVibe 用 Playwright 真跑（需
   `pip install -e ".[browser]"` 与 `playwright install chromium`），此时无需手写 trace。

## 任务规格文件

`data/tasks/todo.json` 定义了标准用户任务集。若要评其他类型作品，复制一份改成你的任务：

```json
{
  "task_set_id": "my-tasks",
  "tasks": [
    {"task_id": "T1", "name": "xxx", "category": "core", "critical": true}
  ]
}
```

`category` 取 `core`（核心任务，失败即触发硬门槛 G2）或 `aux`；`critical: true` 的任务失败同样拦截。
