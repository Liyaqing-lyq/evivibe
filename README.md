# EviVibe

**An evidence-bound, multi-dimensional evaluation framework for *vibe coding* software artifacts.**

> Vibe coding = humans and generative AI co-creating **complete software works** through natural language, examples, screenshots and iterative dialogue — not just generating a function that passes unit tests.

EviVibe evaluates the whole artifact — requirement, prompt trajectory, version history, source code, running system and recorded user tasks — and produces a **traceable quality verdict**: every score point lost maps to a finding, and every finding maps to machine-collected evidence.

```
   ┌──────────────────────────── work dir ────────────────────────────┐
   │  work.json   prompts.jsonl   versions.json   runtime_trace.json  │
   │        (R)         (P)            (T)             (E)      + code (C)
   └──────────────────────────────────┬────────────────────────────────┘
                                      ▼
   ┌─ deterministic probes ──────────────────────┐   ┌─ standard tasks ─┐
   │ code metrics · security scan · process feats│   │ replay/live runs │
   └──────────────────┬──────────────────────────┘   └────────┬─────────┘
                      ▼          EVIDENCE POOL (ids + digests)  ▼
   ┌─ reviewer ensemble ──────────────────────────────────────────────┐
   │  functional · ui · code · security · process   (mock or LLM)     │
   │  every finding MUST cite evidence ids                            │
   └──────────────────┬────────────────────────────────────────────────┘
                      ▼
   hard gates (boot · core tasks · critical security · persistence)
                      ▼
   evidence binding → severity-penalty dimension scores → weighted Q
                      ▼
   report.json + report.md (findings ↔ evidence ↔ digests)
```

## Why it exists

> **Relation to prior art.** ViBench (CAIS '26, Replit et al.) and Replit's
> VibeBench evaluate **AI agents** building apps from prompts (Pass@1, agent
> reliability). EviVibe evaluates **human-AI co-created works** — the
> artifacts students and practitioners actually submit — with an
> evidence-bound, multi-reviewer method and a human-collaboration dimension.
> Different object of study, different method, complementary questions.

Existing benchmarks stop at the wrong boundary for vibe-coding works:

| Gap | EviVibe's answer |
|---|---|
| Code benchmarks (HumanEval, MBPP, SWE-bench) judge functions or patches, not whole works | Evaluates the complete artifact A = {R, P, T, C, E, U} |
| UI metrics (screenshots, DOM, VLM scores) conflate *looking good* with *working* | Runtime task evidence corrects visual-preference ranking bias |
| Direct LLM scoring drifts and hallucinates rationales | **Evidence-bound review**: findings citing non-existent evidence are down-weighted or discarded |
| Single-judge scores are unstable | **Confidence-weighted multi-reviewer aggregation** with run-variance measurement |
| No public data with prompts + versions + runtime + labels | Benchmark data schema + record/replay harness, shipped with the tool |

## Quick start

```bash
pip install -e ".[dev]"        # core has zero dependencies (stdlib only)
evivibe selftest             # offline demo evaluation, no network/LLM
pytest -v                      # full test suite
```

Evaluate the bundled demo work:

```bash
evivibe evaluate \
  --work data/works/demo-todo \
  --tasks data/tasks \
  --out report/
```

Output (`report/demo-todo.md`):

```
> Verdict: ACCEPTED — weighted score 84.4 / 100

| Gate        | Result |
|-------------|--------|
| boot        | ✅ PASS |
| core_tasks  | ✅ PASS |
| security    | ✅ PASS |

| Dimension        | Score | Confidence | Findings |
|------------------|-------|------------|----------|
| Functionality    | 85.0  | 0.00       | 0        |
| Reliability      | 81.25 | 0.75       | 1        |
| ...              |       |            |          |
| Weighted total   | 84.4  |            |          |

### 🟠 [MAJOR] Robustness tasks failed (2/3)
*Dimension: Reliability · Reviewer: functional · Confidence: 0.75*
**Evidence:** `ev-...` (task_log) [robustness] duplicate-submit — failed ...
```

Evaluate every work in a corpus and compare against expert labels:

```bash
evivibe batch --works data/works --tasks data/tasks --out report/
# → Spearman / Kendall / MAE agreement with expert_labels.overall
```

Ablate an input modality (paper experiment, RQ2):

```bash
evivibe ablate --work data/works/demo-todo --tasks data/tasks --modality task_log
```

## Using the LLM backend

The mock backend is fully deterministic and runs offline. To plug in LLM judges
(OpenAI-compatible endpoint):

```bash
export OPENAI_API_KEY=sk-...
export EVIVIBE_LLM_BASE_URL=https://api.openai.com/v1   # optional
export EVIVIBE_LLM_MODEL=gpt-4o-mini                     # optional

evivibe evaluate --work data/works/demo-todo --tasks data/tasks \
                    --reviewer llm --strict
```

`--strict` discards any LLM finding that fails to cite real evidence ids;
the default `soft` mode down-weights them by 4×.

## Repository layout

```
evivibe/
├── evivibe/
│   ├── schema.py              # data model: Evidence, Finding, TaskResult, Report
│   ├── config.py              # weights, gates, penalties, modality toggles
│   ├── gates.py               # hard-gate stage
│   ├── aggregate.py           # evidence binding + scoring (the core method)
│   ├── metrics.py             # Spearman, Kendall, ICC(2,1), MAE, variance...
│   ├── report.py              # Markdown/JSON rendering
│   ├── pipeline.py            # end-to-end orchestration
│   ├── cli.py                 # evivibe evaluate | batch | ablate | selftest
│   ├── analyzers/             # code metrics, security scan, process features
│   ├── runners/               # replay (recorded) + playwright (live)
│   └── reviewers/             # mock ensemble + LLM ensemble
├── data/
│   ├── tasks/todo.json        # standard user tasks (core/robustness/...)
│   └── works/                 # demo-todo (accepted) · demo-clipboard (gated)
├── tests/                     # unit + end-to-end, all offline
└── docs/research-plan.md      # RQs, hypotheses, experiment protocol
```

## The evaluation model

**Stage 1 — hard gates.** A work that cannot boot, fails core standard tasks,
or carries an evidence-bound critical security finding is rejected outright;
no weighted score can average the failure away.

**Stage 2 — soft scoring.** Each dimension starts at 100; every bound finding
subtracts `severity_penalty × confidence`. Reviewer holistic priors are blended
at a fixed (small) weight. The final score is
`Q = Σ w_d · score_d` over the eight dimensions — functionality, UX, visual,
reliability, security, maintainability, innovation, human-AI collaboration.

**Evidence everywhere.** Evidence items carry content digests; findings cite
evidence ids; reports render the full chain, so a "data persistence failed"
verdict always links to the reload-after-write log that proves it.

## Contributing a work

A work directory is all EviVibe needs:

```
works/my-work/
├── work.json           # metadata, requirement, expert labels (optional)
├── prompts.jsonl       # human-AI dialogue trajectory
├── versions.json       # version history w/ human_edited flags
├── runtime_trace.json  # recorded standard-task evidence (replay mode)
└── <source files>
```

Run live instead of replay with `--base-url http://localhost:5000`
(requires `pip install -e ".[browser]"` and a Chromium install).

## Citation

If you use EviVibe in your research, please cite:

```bibtex
@software{evivibe2026,
  title  = {EviVibe: An Evidence-Bound Evaluation Framework for Vibe Coding Artifacts},
  author = {EviVibe Contributors},
  year   = {2026},
  url    = {https://github.com/yourname/evivibe}
}
```

## License

MIT — see [LICENSE](LICENSE).
