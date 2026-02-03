# SQLite 并发策略（LLM 并行，DB 串行）

> 目的：在保持 SQLite（WAL）稳定与数据一致性的前提下，最大化“可并行的网络/LLM 阶段”，并严格限制“写事务”的持有时间。
>
> 适用范围：ainovel 后端（FastAPI + SQLite + SQLAlchemy），含 inline worker / rq worker 的任务执行链路。

## 背景与问题

SQLite 在写入并发下的关键约束是：写事务会阻塞其它写事务（以及在某些场景下影响读写竞争）。当我们把 LLM 网络调用放进长事务里，会导致：

- 任务排队、请求阻塞（看起来像“系统卡死”）
- `busy_timeout` 触发，出现间歇性 `database is locked`
- 一次失败扩大为“全局写入退化”

因此必须强制：**LLM 调用不持有 DB 长事务**，并将 DB 写入压缩为**短、可回滚、可重试**的临界区。

## 目标（必须满足）

- 允许并行：LLM 调用、外部 HTTP、纯 CPU 计算（JSON repair/parse 等）。
- 必须串行：对 SQLite 的写入阶段（尤其是跨多表写入、批量 upsert/merge）。
- 锁粒度最小化：以“单任务/单变更集”为单位提交；避免跨网络 I/O 的事务。
- 失败可恢复：任务中断不会留下不可自愈的“running 永久占位”或半写入。
- 可观测：health/taskcenter 能解释“为什么排队”（effective backend / inline 指标 / 任务状态）。

## 执行模型：三段式（推荐）

以 ProjectTask / MemoryTask 等后台任务为例，统一采用三段式：

1) **Acquire（短事务）**
   - 读取任务行
   - 以条件更新把 `status: queued -> running`（需要幂等，避免覆盖 canceled）
   - 写入 `started_at`
   - `COMMIT`

2) **Work（无事务/短读事务）**
   - 读取必要上下文（可用短读事务或只读连接）
   - 调用 LLM / 外部服务（此阶段不得持有写事务）
   - 纯函数处理：schema 校验 / JSON repair / normalize

3) **Apply（短事务）**
   - 将最终结果写入（result/error、变更集落库、实体 upsert 等）
   - 写入 `finished_at`
   - `COMMIT`

> 关键点：**Work 阶段永远不持有写事务**；Apply 必须保证“要么全成，要么全回滚”。

## 幂等与去重（避免任务风暴）

当章节短时间多次触发自动更新时，应保证：

- **队列长度不线性增长**：对同一类 `...:since:<token>` 的任务，仅保留最新 queued；旧 queued 标记为 `canceled`（worker 侧跳过）。
- running 任务不强行中断：允许“running + 最新 queued”并存，最终收敛到最新状态。

实现要点：

- 通过 `idempotency_key` 的 `:since:` 前缀识别“同一类任务”
- 只取消 `params_json.reason` 以 `chapter` 开头的自动任务，避免误伤 manual 任务

## SQLite 写入策略（工程约束）

- **单 worker**：SQLite 下推荐 `rq` 单 worker 或 inline 单线程 worker（生产建议 rq 单 worker）。
- **短事务**：任何 LLM/外部调用前必须 `COMMIT` 或 `ROLLBACK`。
- **避免长时间持有 Session**：不要在 Session 仍处于事务状态时执行网络 I/O。
- **Fail-soft**：队列不可用/Redis 不可用时，dev 可回落 inline；prod 不回落但需可观测提示。

## 失败恢复策略（建议）

- `running` 超时检测：为长时间 running 的任务提供“标记为 failed + how_to_fix + 可重试”工具。
- `canceled` 语义：
  - queued 可取消（UI/接口）
  - worker 入口读到 `canceled` 直接返回（必要时补齐 `finished_at`）

## 可观测性（必须）

health / TaskCenter 至少暴露：

- `queue_backend`（配置）
- `effective_backend`（实际）
- inline 指标：`inline_queue_size`、`inline_last_processed_at`
- 任务失败需带 `run_id`（用于定位 generation_runs）与 `how_to_fix`

## 代码映射（现状参考）

- `backend/app/services/task_queue.py`：inline/rq backend 选择、inline 指标、health 输出
- `backend/app/services/project_task_service.py`：worker 入口 `run_project_task` 的 Acquire/Work/Apply 分段、queued 去重/取消

## 后续实现 Issue（引用）

- `MVP-009`：inline worker 有限并发（需严格控制 DB 写阶段串行）
- `MVP-010 ~ MVP-012`：失败可定位（run_id / error.details）
- `MVP-015 ~ MVP-019`：JSON repair/normalize（Work 阶段并行、Apply 阶段短事务）

