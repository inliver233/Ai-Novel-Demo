# ainovel - AI小说半自动创作平台开发计划 v2.0

> **项目名称**：ainovel
> **版本**：v2.0（根据专业反馈全面优化）
> **创建日期**：2025-11-23
> **更新日期**：2025-11-23
> **项目定位**：面向网文作者的AI辅助长篇小说创作平台
> **核心理念**：全环节可人工干预 + 长文一致性保障 + 文风可调节

---

## 📋 改进说明（v2.0）

**本次更新重点**：
1. ✅ 补充完整的**一致性保障方案**（三段检索优先级+生成闭环）
2. ✅ 扩展**数据模型**（版本评审/事件/时间线/伏笔/幂等更新）
3. ✅ 补充**架构稳健性**（异步队列/SSE 心跳重连/Redis 角色明确）
4. ✅ 加入**安全方案**（密钥管理/RBAC/审计日志/限流配额）
5. ✅ 加入**可观测性方案**（日志/指标/追踪/成本监控）
6. ✅ 加入**Prompt 治理方案**（JSON 校验/输出清洗/token 预算）
7. ✅ 细化**开发路线图**（DoD/性能基线/并行轨道）
8. ✅ 补充**前端交互流程**（上下文预览/选稿对比/分支重生）
9. ✅ 完善**风险防控**（降级策略/幂等/备份迁移）

---

## 一、项目概述

### 1.1 项目背景
本项目为毕业设计项目，旨在开发一款AI辅助小说创作软件，帮助网文作者快速实现创作想法，同时保证长文内容一致性和情节连贯性。

### 1.2 核心特性
- **半自动创作**：人工可干预全流程（世界观→大纲→章节→评审→选稿）
- **长文一致性**：三段式检索（世界书→结构化记忆→向量RAG）+ 选稿幂等入库
- **高度自定义**：支持多种LLM、自定义embedding/rerank模型
- **云端多用户**：网页应用，响应式设计（PC + 手机），RBAC权限隔离
- **灵活工作流**：核心流程固定 + 可选AI评审 + 多版本生成选稿
- **生产级稳健**：SSE心跳重连、异步队列、限流配额、审计日志、可观测性

### 1.3 目标用户
- 追求高效产出的网文作者
- 需要快速验证剧情设定的创作者
- 希望AI辅助但保持创作控制权的作者

---

## 二、技术选型

### 2.1 技术栈总览

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| **前端** | React 18 + TypeScript | 生态丰富，组件库完善 |
| **UI框架** | TailwindCSS + Ant Design | 响应式设计 + 企业级组件 |
| **状态管理** | Zustand | 轻量级，易于使用 |
| **后端** | FastAPI (Python 3.11+) | 高性能异步，LLM生态友好 |
| **ORM** | SQLAlchemy 2.0 | 成熟稳定，支持异步 |
| **数据验证** | Pydantic v2 | 类型安全，性能优秀 |
| **关系数据库** | PostgreSQL 15 | 稳定可靠，支持pgvector |
| **向量引擎** | pgvector | 统一数据库，减少组件 |
| **异步队列** | Arq (基于Redis) | 轻量级，易于部署 |
| **缓存/队列** | Redis 7 | 会话/限流/队列/SSE消息 |
| **日志** | Structlog + Python logging | 结构化日志 |
| **监控** | Prometheus + Grafana | 指标收集与可视化 |
| **追踪** | OpenTelemetry (可选) | 分布式追踪 |
| **部署** | Docker Compose + Nginx | 一键部署，易于维护 |

### 2.2 技术选型理由

#### 为什么选择 PostgreSQL + pgvector？
- **统一管理**：关系数据和向量数据在同一数据库，减少维护成本
- **事务一致性**：向量操作可参与事务，保证数据一致性（选稿幂等更新）
- **轻量部署**：无需额外部署独立向量数据库
- **后期可扩展**：如需更高性能，可平滑迁移至Chroma/Qdrant

#### 为什么选择 Arq？
- **轻量级**：基于Redis，无需额外部署Celery的Broker
- **类型安全**：原生支持Python类型提示
- **易于调试**：代码简洁，适合个人开发
- **性能足够**：满足MVP阶段的异步任务需求（摘要/嵌入/评审）

#### 为什么需要异步队列？
- **分离关键路径**：生成章节内容（SSE流式）不应等待嵌入/评审
- **失败重试**：嵌入/评审任务失败可自动重试
- **性能优化**：避免阻塞用户交互

---

## 三、系统架构

### 3.1 整体架构图（含异步队列）

```
┌─────────────────────────────────────────────────────────────┐
│                    Nginx (反向代理 + 限流)                   │
└─────────────────────────────────────────────────────────────┘
                    │                         │
                    ▼                         ▼
┌─────────────────────────────┐  ┌─────────────────────────────┐
│      Frontend (React)       │  │      Backend (FastAPI)      │
│  ┌───────────────────────┐  │  │  ┌───────────────────────┐  │
│  │   Pages (页面)         │  │  │  │   API Routes (路由)   │  │
│  │   ├── Dashboard        │  │  │  │   ├── auth + RBAC     │  │
│  │   ├── Editor           │  │  │  │   ├── projects        │  │
│  │   │   ├── ContextBox   │  │  │  │   ├── worldbuilding   │  │
│  │   │   ├── DraftPanel   │  │  │  │   ├── outline         │  │
│  │   │   └── VersionComp  │  │  │  │   ├── chapters        │  │
│  │   └── Settings         │  │  │  │   ├── memory          │  │
│  ├───────────────────────┤  │  │  │   └── analysis        │  │
│  │   Components (组件)    │  │  │  ├───────────────────────┤  │
│  │   ├── SSEStream        │  │  │  │   Services (服务)      │  │
│  │   │   (心跳/重连)      │  │  │  │   ├── GenerationSvc   │  │
│  │   └── VersionSelector  │  │  │  │   ├── MemoryService   │  │
│  └───────────────────────┘  │  │  │   ├── AnalysisService │  │
└─────────────────────────────┘  │  │   └── ReviewService   │  │
                                 │  ├───────────────────────┤  │
                                 │  │   Core (核心模块)       │  │
                                 │  │   ├── llm/             │  │
                                 │  │   ├── memory/          │  │
                                 │  │   │   ├── retriever    │  │
                                 │  │   │   └── injector     │  │
                                 │  │   ├── workflow/        │  │
                                 │  │   ├── security/        │  │
                                 │  │   │   ├── encryption   │  │
                                 │  │   │   ├── rate_limit   │  │
                                 │  │   │   └── audit_log    │  │
                                 │  │   └── observability/   │  │
                                 │  │       ├── logger       │  │
                                 │  │       └── metrics      │  │
                                 │  └───────────────────────┘  │
                                 └─────────────────────────────┘
                                               │
                    ┌──────────────────────────┼────────────────────────┐
                    ▼                          ▼                        ▼
          ┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
          │   PostgreSQL    │      │     Redis       │      │   Arq Workers   │
          │   + pgvector    │      │ ┌─────────────┐ │      │  (异步任务)     │
          │                 │      │ │ 队列        │ │      │ ├─摘要生成      │
          │ • 业务数据       │◄─────┤ │ 限流        │ │      │ ├─向量嵌入      │
          │ • 向量记忆       │      │ │ 缓存        │ │      │ ├─事件抽取      │
          │ • 审计日志       │      │ │ SSE状态     │ │      │ └─AI评审        │
          └─────────────────┘      │ └─────────────┘ │      └─────────────────┘
                                   └─────────────────┘
                                            │
                    ┌───────────────────────┼───────────────────────┐
                    ▼                       ▼                       ▼
          ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
          │ Prometheus      │    │   LLM APIs      │    │  Structlog      │
          │ (指标收集)       │    │  (多Provider)   │    │  (日志聚合)      │
          └─────────────────┘    └─────────────────┘    └─────────────────┘
```

### 3.2 Redis 角色明确

| 用途 | Key前缀 | 说明 |
|------|---------|------|
| **会话缓存** | `session:{user_id}` | JWT Token 黑名单、用户会话 |
| **限流** | `ratelimit:{user_id}:{endpoint}` | 滑动窗口限流计数 |
| **配额** | `quota:{user_id}:{model}:{date}` | 每日token配额跟踪 |
| **SSE状态** | `sse:{chapter_id}:status` | SSE生成进度/心跳 |
| **任务队列** | `arq:queue` | Arq异步任务队列 |
| **缓存** | `cache:{key}` | LLM配置、Prompt模板缓存 |

### 3.3 后端目录结构（扩展版）

```
backend/
├── app/
│   ├── main.py                 # FastAPI应用入口
│   ├── config.py               # 配置管理（分dev/prod）
│   ├── database.py             # 数据库连接
│   │
│   ├── api/v1/                 # API路由层
│   │   ├── auth.py             # 认证 + RBAC
│   │   ├── projects.py
│   │   ├── chapters.py
│   │   │   ├── generate (SSE)  # 支持心跳/重连
│   │   │   ├── review          # 触发评审任务
│   │   │   └── select_version  # 选稿入库
│   │   ├── memory.py
│   │   └── admin.py            # 管理员接口（配额/审计）
│   │
│   ├── models/                 # 数据模型
│   │   ├── chapter.py
│   │   ├── chapter_version.py  # 新增 is_selected
│   │   ├── review.py           # 新增评审表
│   │   ├── event.py            # 新增事件表
│   │   ├── timeline.py         # 新增时间线表
│   │   ├── foreshadow.py       # 新增伏笔表
│   │   ├── vector_memory.py    # 扩展 source_type/version_id/deleted_at
│   │   └── audit_log.py        # 新增审计日志
│   │
│   ├── services/
│   │   ├── generation_service.py
│   │   │   └── generate_stream (SSE心跳)
│   │   ├── memory_service.py
│   │   │   ├── retrieve_context (三段检索)
│   │   │   └── update_memory_idempotent (幂等)
│   │   ├── review_service.py   # AI评审
│   │   └── analysis_service.py # 事件/伏笔抽取
│   │
│   ├── core/
│   │   ├── llm/
│   │   │   ├── provider.py     # 统一Provider抽象
│   │   │   └── output_parser.py # JSON校验+清洗
│   │   ├── memory/
│   │   │   ├── retriever.py    # 三段检索实现
│   │   │   └── injector.py     # 上下文注入策略
│   │   ├── security/
│   │   │   ├── encryption.py   # API Key加密
│   │   │   ├── rate_limiter.py # 限流器
│   │   │   ├── rbac.py         # 权限控制
│   │   │   └── audit.py        # 审计日志
│   │   ├── observability/
│   │   │   ├── logger.py       # Structlog配置
│   │   │   ├── metrics.py      # Prometheus指标
│   │   │   └── tracer.py       # OTEL追踪（可选）
│   │   └── prompt/
│   │       ├── templates.py    # Prompt模板
│   │       ├── validator.py    # JSON Schema校验
│   │       └── compressor.py   # Token压缩
│   │
│   ├── workers/                # 异步任务
│   │   ├── __init__.py
│   │   ├── summary.py          # 摘要生成任务
│   │   ├── embedding.py        # 向量嵌入任务
│   │   ├── extraction.py       # 事件抽取任务
│   │   └── review.py           # AI评审任务
│   │
│   ├── schemas/                # Pydantic Schema
│   ├── utils/
│   │   ├── sse.py              # SSE辅助函数（心跳）
│   │   └── idempotent.py       # 幂等更新工具
│   │
│   └── migrations/             # Alembic迁移
│
├── tests/
│   ├── test_memory_retrieval.py
│   ├── test_idempotent_update.py
│   └── test_sse_reconnect.py
│
├── prometheus/                 # 监控配置
│   └── prometheus.yml
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## 四、数据模型设计（完整版）

### 4.1 核心表扩展

#### 章节版本表（扩展）
```sql
CREATE TABLE chapter_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_id UUID REFERENCES chapters(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    is_selected BOOLEAN DEFAULT FALSE,     -- 【新增】是否被选中采纳
    selected_at TIMESTAMP,                 -- 【新增】选中时间
    word_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chapter_id, version)
);

-- 索引：快速查找已选版本
CREATE INDEX idx_chapter_versions_selected ON chapter_versions(chapter_id, is_selected) WHERE is_selected = TRUE;
```

#### 评审表（新增）
```sql
CREATE TABLE reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chapter_version_id UUID REFERENCES chapter_versions(id) ON DELETE CASCADE,
    reviewer_type VARCHAR(20) NOT NULL,    -- ai / human
    score INTEGER,                         -- 1-10评分
    summary TEXT,                          -- 评审摘要
    issues JSONB,                          -- 问题列表 {"character_conflicts": [...], "plot_holes": [...]}
    suggestions JSONB,                     -- 改进建议
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 事件表（新增）
```sql
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    chapter_id UUID REFERENCES chapters(id),
    version_id UUID REFERENCES chapter_versions(id), -- 【关键】关联采纳版本
    event_type VARCHAR(50) NOT NULL,       -- character_action, plot_turn, relationship_change
    title VARCHAR(200),
    description TEXT NOT NULL,
    characters JSONB,                      -- 涉及角色 ["角色A", "角色B"]
    timestamp_in_story VARCHAR(100),       -- 故事内时间（如"第3天晚上"）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP                   -- 【新增】软删除（版本更换时）
);

CREATE INDEX idx_events_project ON events(project_id, deleted_at);
CREATE INDEX idx_events_chapter ON events(chapter_id, deleted_at);
```

#### 时间线表（新增）
```sql
CREATE TABLE timelines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    event_id UUID REFERENCES events(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,             -- 时间线序号
    chapter_number INTEGER,
    story_time VARCHAR(100),               -- 故事内时间
    real_time_duration VARCHAR(50),        -- 持续时长（"3天"）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_timeline_sequence ON timelines(project_id, sequence);
```

#### 伏笔表（新增）
```sql
CREATE TABLE foreshadows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    setup_chapter_id UUID REFERENCES chapters(id),     -- 埋设章节
    setup_version_id UUID REFERENCES chapter_versions(id),
    setup_content TEXT NOT NULL,                       -- 伏笔内容
    payoff_chapter_id UUID REFERENCES chapters(id),    -- 揭示章节（可空）
    status VARCHAR(20) DEFAULT 'pending',              -- pending / resolved / abandoned
    importance INTEGER DEFAULT 1,                      -- 重要性 1-5
    tags TEXT[],                                       -- 标签 ["主线伏笔", "角色背景"]
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    deleted_at TIMESTAMP
);

CREATE INDEX idx_foreshadows_status ON foreshadows(project_id, status, deleted_at);
```

#### 向量记忆表（扩展幂等支持）
```sql
CREATE TABLE vector_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(1536),                -- OpenAI ada-002维度
    source_type VARCHAR(50) NOT NULL,      -- chapter_summary / event / review / blueprint
    source_id UUID NOT NULL,               -- 源记录ID
    version_id UUID,                       -- 【新增】关联版本ID（chapter_version）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP,                  -- 【新增】软删除（版本更换时先删旧）

    -- 唯一约束：同一源+版本只能有一条有效记录
    UNIQUE(source_type, source_id, version_id) WHERE deleted_at IS NULL
);

-- 索引：向量检索（排除已删除）
CREATE INDEX idx_vector_valid ON vector_memories(project_id, source_type)
WHERE deleted_at IS NULL;

CREATE INDEX idx_vector_embedding ON vector_memories
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100)
WHERE deleted_at IS NULL;
```

#### 审计日志表（新增）
```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    project_id UUID REFERENCES projects(id),
    action VARCHAR(50) NOT NULL,           -- llm_call / chapter_generate / version_select
    resource_type VARCHAR(50),             -- chapter / world / outline
    resource_id UUID,
    metadata JSONB,                        -- {"model": "gpt-4", "tokens": 1500, "cost": 0.03}
    ip_address INET,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_user ON audit_logs(user_id, created_at DESC);
CREATE INDEX idx_audit_project ON audit_logs(project_id, created_at DESC);
CREATE INDEX idx_audit_action ON audit_logs(action, created_at DESC);
```

### 4.2 幂等更新流程设计

#### 选稿入库流程（幂等）
```python
async def select_version_idempotent(
    chapter_id: str,
    version_number: int,
    db: AsyncSession,
) -> bool:
    """选择版本并幂等更新记忆系统"""

    async with db.begin():  # 事务保证原子性
        # 1. 检查是否已选中（幂等性）
        existing = await db.execute(
            select(ChapterVersion).where(
                ChapterVersion.chapter_id == chapter_id,
                ChapterVersion.is_selected == True
            )
        )
        current_selected = existing.scalar_one_or_none()

        # 2. 如果已选择目标版本，直接返回
        if current_selected and current_selected.version == version_number:
            return True  # 幂等：已选择

        # 3. 取消旧版本选中
        if current_selected:
            current_selected.is_selected = False

            # 软删除旧版本关联的向量/事件
            await db.execute(
                update(VectorMemory)
                .where(
                    VectorMemory.version_id == current_selected.id,
                    VectorMemory.deleted_at == None
                )
                .values(deleted_at=datetime.utcnow())
            )
            await db.execute(
                update(Event)
                .where(
                    Event.version_id == current_selected.id,
                    Event.deleted_at == None
                )
                .values(deleted_at=datetime.utcnow())
            )

        # 4. 选中新版本
        new_version = await db.get(ChapterVersion, version_number)
        new_version.is_selected = True
        new_version.selected_at = datetime.utcnow()

        # 5. 提交事务
        await db.commit()

        # 6. 异步任务：为新版本生成摘要/嵌入/事件（事务外）
        await arq.enqueue_job(
            "generate_summary_and_embed",
            chapter_id=chapter_id,
            version_id=new_version.id,
        )
        await arq.enqueue_job(
            "extract_events",
            chapter_id=chapter_id,
            version_id=new_version.id,
        )

    return True
```

---

## 五、核心功能设计（完整版）

### 5.1 一致性保障方案：三段式检索

#### 检索优先级与策略

```
┌─────────────────────────────────────────────────────────────┐
│               上下文检索管道（按优先级顺序执行）              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  【第一段】世界书检索（WorldBook Retrieval）                │
│  ┌────────────────────────────────────────────────────┐     │
│  │ 输入：用户提示 + 当前章节内容前缀                  │     │
│  │ 匹配：关键词触发（keywords LIKE %text%）           │     │
│  │ 常驻：is_constant = TRUE 的条目自动包含            │     │
│  │ 注入位置：                                         │     │
│  │   - system: 系统提示开头（世界观设定）             │     │
│  │   - before: 用户提示之前（人物卡/背景）            │     │
│  │   - after:  用户提示之后（写作规范）               │     │
│  │ 输出：按 priority 降序 + position 分组             │     │
│  └────────────────────────────────────────────────────┘     │
│            ↓（窗口预算：system 2000 tokens）                 │
│                                                             │
│  【第二段】结构化记忆检索（Structured Memory）              │
│  ┌────────────────────────────────────────────────────┐     │
│  │ 过滤条件：                                         │     │
│  │   - 角色关系：涉及当前章节出场角色                 │     │
│  │   - 事件：最近5章内发生的事件（deleted_at IS NULL）│     │
│  │   - 伏笔：status='pending' 且 setup_chapter <= 当前│     │
│  │ 排序：按时间线sequence或chapter_number倒序         │     │
│  │ 输出：JSON格式 {"characters": [...], "events": ...}│     │
│  └────────────────────────────────────────────────────┘     │
│            ↓（窗口预算：3000 tokens）                        │
│                                                             │
│  【第三段】向量检索（Vector RAG）                           │
│  ┌────────────────────────────────────────────────────┐     │
│  │ 查询向量：用户提示 + 当前章节摘要                  │     │
│  │ 分池检索：                                         │     │
│  │   - chapter_summary: Top 3（相似度 > 0.75）        │     │
│  │   - blueprint/outline: Top 2                       │     │
│  │   - review: Top 1（已选稿的评审摘要）              │     │
│  │ 降级策略：无高相似度结果时，召回最近3章摘要        │     │
│  │ 输出：按source_type分组 + 相似度排序               │     │
│  └────────────────────────────────────────────────────┘     │
│            ↓（窗口预算：4000 tokens）                        │
│                                                             │
│  【窗口裁剪】Token预算管理                                  │
│  ┌────────────────────────────────────────────────────┐     │
│  │ 总预算：12000 tokens（GPT-4 Turbo 128k 上下文）    │     │
│  │ 分配：                                             │     │
│  │   - 系统提示（世界书system）: 2000                 │     │
│  │   - 世界书before: 1000                             │     │
│  │   - 结构化记忆: 3000                               │     │
│  │   - 向量RAG: 4000                                  │     │
│  │   - 用户指令 + 世界书after: 2000                   │     │
│  │ 超限处理：截断最低优先级内容（向量→结构化→世界书） │     │
│  └────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

#### 代码实现

```python
# core/memory/retriever.py
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class RetrievalConfig:
    """检索配置"""
    max_total_tokens: int = 12000
    worldbook_system_tokens: int = 2000
    worldbook_before_tokens: int = 1000
    structured_tokens: int = 3000
    vector_tokens: int = 4000
    user_prompt_tokens: int = 2000
    vector_similarity_threshold: float = 0.75

class ThreeStageRetriever:
    """三段式上下文检索器"""

    async def retrieve(
        self,
        project_id: str,
        user_prompt: str,
        current_chapter_num: int,
        config: RetrievalConfig = None,
    ) -> Dict[str, any]:
        """执行三段检索"""
        config = config or RetrievalConfig()
        context = {
            "worldbook": {"system": [], "before": [], "after": []},
            "structured": {"characters": [], "events": [], "foreshadows": []},
            "vector": {"summaries": [], "blueprints": [], "reviews": []},
            "metadata": {"truncated": False, "token_usage": {}},
        }

        # 【第一段】世界书检索
        worldbook_items = await self._retrieve_worldbook(
            project_id, user_prompt, config
        )
        context["worldbook"] = self._group_by_position(worldbook_items)

        # 【第二段】结构化记忆检索
        structured = await self._retrieve_structured(
            project_id, current_chapter_num, config
        )
        context["structured"] = structured

        # 【第三段】向量检索
        vector_results = await self._retrieve_vector(
            project_id, user_prompt, current_chapter_num, config
        )
        context["vector"] = vector_results

        # 窗口裁剪
        context = self._trim_to_budget(context, config)

        return context

    async def _retrieve_worldbook(
        self, project_id: str, text: str, config: RetrievalConfig
    ) -> List[WorldBook]:
        """世界书检索：关键词匹配 + 常驻项"""
        query = (
            select(WorldBook)
            .where(
                WorldBook.project_id == project_id,
                WorldBook.enabled == True,
                or_(
                    WorldBook.is_constant == True,  # 常驻
                    WorldBook.keywords.op("&&")(text_to_keywords(text))  # 关键词
                )
            )
            .order_by(WorldBook.priority.desc())
        )
        result = await db.execute(query)
        return result.scalars().all()

    async def _retrieve_structured(
        self, project_id: str, current_chapter: int, config: RetrievalConfig
    ) -> Dict:
        """结构化记忆检索：角色/事件/伏笔"""
        # 最近5章的事件
        events = await db.execute(
            select(Event)
            .where(
                Event.project_id == project_id,
                Event.chapter_number >= current_chapter - 5,
                Event.chapter_number < current_chapter,
                Event.deleted_at == None
            )
            .order_by(Event.chapter_number.desc())
            .limit(10)
        )

        # 未解决的伏笔
        foreshadows = await db.execute(
            select(Foreshadow)
            .where(
                Foreshadow.project_id == project_id,
                Foreshadow.status == "pending",
                Foreshadow.setup_chapter_number <= current_chapter,
                Foreshadow.deleted_at == None
            )
            .order_by(Foreshadow.importance.desc())
            .limit(5)
        )

        return {
            "events": [e.to_dict() for e in events.scalars()],
            "foreshadows": [f.to_dict() for f in foreshadows.scalars()],
        }

    async def _retrieve_vector(
        self, project_id: str, query: str, current_chapter: int, config: RetrievalConfig
    ) -> Dict:
        """向量检索：分池召回"""
        query_embedding = await llm_provider.embed(query)

        results = {}

        # 分池检索
        for source_type, top_k in [
            ("chapter_summary", 3),
            ("blueprint", 2),
            ("review", 1),
        ]:
            vectors = await db.execute(
                select(
                    VectorMemory.content,
                    VectorMemory.embedding.cosine_distance(query_embedding).label("distance")
                )
                .where(
                    VectorMemory.project_id == project_id,
                    VectorMemory.source_type == source_type,
                    VectorMemory.deleted_at == None
                )
                .order_by("distance")
                .limit(top_k)
            )

            items = []
            for content, distance in vectors:
                similarity = 1 - distance
                if similarity >= config.vector_similarity_threshold:
                    items.append({"content": content, "similarity": similarity})

            # 降级策略：无高相似度结果时召回最近章节
            if not items and source_type == "chapter_summary":
                recent = await self._get_recent_summaries(project_id, current_chapter, 3)
                items = [{"content": s, "similarity": 0.0, "fallback": True} for s in recent]

            results[source_type] = items

        return results

    def _trim_to_budget(self, context: Dict, config: RetrievalConfig) -> Dict:
        """裁剪到token预算"""
        # TODO: 实现token计数与裁剪逻辑
        # 优先级：用户指令 > 世界书system > 结构化 > 向量 > 世界书before/after
        return context
```

### 5.2 生成闭环流程

```
┌─────────────────────────────────────────────────────────────┐
│           章节生成 → 评审 → 选稿 → 入库闭环                  │
└─────────────────────────────────────────────────────────────┘

【阶段1】生成阶段（SSE流式，用户实时查看）
  ┌──────────────────────────────────────┐
  │ 用户点击"生成章节"                   │
  └──────────────────────────────────────┘
           │
           ▼
  ┌──────────────────────────────────────┐
  │ 1. 三段式检索上下文                  │
  │ 2. 构建Prompt（带JSON Schema约束）   │
  │ 3. SSE流式生成（带心跳）             │
  │ 4. 保存为新版本（is_selected=FALSE）│
  └──────────────────────────────────────┘
           │
           ▼（生成完成后，不自动入库）

【阶段2】评审阶段（可选，异步后台）
  ┌──────────────────────────────────────┐
  │ 用户点击"AI评审"（可选）             │
  └──────────────────────────────────────┘
           │
           ▼
  ┌──────────────────────────────────────┐
  │ 异步任务：                           │
  │ 1. 分析人设一致性                    │
  │ 2. 检测伏笔矛盾                      │
  │ 3. 评估剧情合理性                    │
  │ 4. 保存评审结果（reviews表）         │
  └──────────────────────────────────────┘
           │
           ▼（前端展示评审报告）

【阶段3】选稿阶段（人工确认）
  ┌──────────────────────────────────────┐
  │ 前端展示：                           │
  │ • 多版本对比（版本1 vs 版本2）       │
  │ • 评审摘要（如有）                   │
  │ • 差异高亮                           │
  └──────────────────────────────────────┘
           │
           ▼
  ┌──────────────────────────────────────┐
  │ 用户选择版本X，点击"采纳"            │
  └──────────────────────────────────────┘
           │
           ▼

【阶段4】入库阶段（幂等更新）
  ┌──────────────────────────────────────┐
  │ 事务内：                             │
  │ 1. 取消旧版本选中（if exists）       │
  │ 2. 标记新版本 is_selected=TRUE       │
  │ 3. 软删除旧版本的向量/事件           │
  │    (UPDATE SET deleted_at=NOW())     │
  └──────────────────────────────────────┘
           │
           ▼
  ┌──────────────────────────────────────┐
  │ 异步任务（事务外）：                 │
  │ 1. 生成摘要 → 嵌入 → 入向量库        │
  │ 2. 抽取事件 → 写events表             │
  │ 3. 抽取伏笔 → 写foreshadows表        │
  │ 4. 更新时间线                        │
  └──────────────────────────────────────┘
           │
           ▼
  【完成】记忆系统已更新，下次生成可召回
```

#### 关键：选稿前不写入向量/事件

```python
# services/generation_service.py
async def generate_chapter_stream(
    chapter_id: str,
    user_prompt: str,
    config: GenerationConfig,
):
    """SSE流式生成（不自动入库）"""

    # 1. 检索上下文
    context = await retriever.retrieve(
        project_id=chapter.project_id,
        user_prompt=user_prompt,
        current_chapter_num=chapter.number,
    )

    # 2. 构建Prompt
    prompt = await prompt_builder.build(
        template="chapter_generation",
        context=context,
        user_input=user_prompt,
        json_schema=ChapterOutputSchema,  # 强制JSON格式
    )

    # 3. SSE流式生成
    full_content = ""
    async for chunk in llm_provider.generate_stream(prompt):
        full_content += chunk
        yield {"type": "chunk", "content": chunk}

        # 心跳（每5秒）
        if time.time() - last_heartbeat > 5:
            yield {"type": "heartbeat", "timestamp": time.time()}
            last_heartbeat = time.time()

    # 4. 清洗输出
    cleaned_content = output_cleaner.clean(full_content)  # 移除<think>标签等

    # 5. 保存为新版本（未选中）
    version = ChapterVersion(
        chapter_id=chapter_id,
        version=await get_next_version_number(chapter_id),
        content=cleaned_content,
        is_selected=False,  # 【关键】未选中，不触发入库
        word_count=count_words(cleaned_content),
    )
    db.add(version)
    await db.commit()

    yield {"type": "done", "version_id": version.id}

    # 【注意】不自动调用摘要/嵌入/事件抽取
    # 等待用户选稿后再执行
```

### 5.3 SSE 稳健性设计

#### 心跳机制
```python
# utils/sse.py
import asyncio
import time

async def sse_stream_with_heartbeat(
    generator,
    heartbeat_interval: int = 5,
):
    """SSE流式输出 + 心跳"""
    last_heartbeat = time.time()

    async for item in generator:
        yield item

        # 发送心跳
        if time.time() - last_heartbeat > heartbeat_interval:
            yield {
                "type": "heartbeat",
                "timestamp": time.time(),
                "status": "generating",
            }
            last_heartbeat = time.time()
```

#### 前端重连逻辑
```typescript
// hooks/useSSEGeneration.ts
export function useSSEGeneration() {
  const [status, setStatus] = useState<'idle' | 'connecting' | 'streaming' | 'error'>('idle');
  const [content, setContent] = useState('');
  const reconnectAttempts = useRef(0);
  const eventSourceRef = useRef<EventSource | null>(null);

  const connect = (url: string) => {
    setStatus('connecting');
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'chunk') {
        setContent(prev => prev + data.content);
        setStatus('streaming');
      } else if (data.type === 'heartbeat') {
        console.log('Heartbeat received:', data.timestamp);
      } else if (data.type === 'done') {
        setStatus('idle');
        es.close();
      }
    };

    es.onerror = () => {
      console.error('SSE connection error');

      // 自动重连（最多3次）
      if (reconnectAttempts.current < 3) {
        reconnectAttempts.current++;
        setTimeout(() => {
          console.log(`Reconnecting... (${reconnectAttempts.current}/3)`);
          connect(url);
        }, 2000 * reconnectAttempts.current); // 指数退避
      } else {
        setStatus('error');
        message.error('连接中断，请点击"继续生成"按钮');
      }
    };
  };

  const resume = async (chapterId: string) => {
    // 调用后端"继续生成"接口（从上次中断处开始）
    const response = await api.post(`/chapters/${chapterId}/resume`);
    connect(response.data.stream_url);
  };

  return { status, content, connect, resume };
}
```

#### 继续生成支持
```python
# api/v1/chapters.py
@router.post("/{chapter_id}/resume")
async def resume_generation(
    chapter_id: str,
    db: AsyncSession = Depends(get_db),
):
    """从中断处继续生成"""

    # 从Redis获取上次生成状态
    state = await redis.get(f"sse:{chapter_id}:state")
    if not state:
        raise HTTPException(404, "No interrupted generation found")

    state = json.loads(state)

    # 构建Prompt（包含已生成内容）
    prompt = f"""
    【已生成内容】
    {state['partial_content']}

    【继续生成】
    请从上文自然继续...
    """

    # 继续流式生成
    return StreamingResponse(
        generation_service.generate_stream(
            chapter_id=chapter_id,
            prompt=prompt,
            partial_content=state['partial_content'],
        ),
        media_type="text/event-stream",
    )
```

### 5.4 Prompt 治理方案

#### JSON Schema 强制输出
```python
# core/prompt/validator.py
from pydantic import BaseModel, Field

class ChapterOutputSchema(BaseModel):
    """章节生成输出格式"""
    content: str = Field(..., description="章节正文内容")
    summary: str = Field(..., max_length=500, description="章节摘要（500字以内）")
    key_events: list[str] = Field(default_factory=list, description="关键事件列表")
    characters_appeared: list[str] = Field(default_factory=list, description="出场角色")

class PromptTemplate:
    """Prompt模板（带JSON Schema）"""

    CHAPTER_GENERATION = """
你是专业的网文作家助手。请根据以下信息生成章节内容。

【世界观设定】
{worldbook_system}

【已有上下文】
{structured_memory}

【相关章节】
{vector_summaries}

【用户指令】
{user_prompt}

【输出要求】
1. 严格遵循JSON格式输出
2. 章节正文2000-3000字
3. 摘要简洁明了，500字以内
4. 列出关键事件和出场角色

输出JSON Schema:
{json_schema}

请输出：
```json
"""

    @classmethod
    async def build(cls, context: dict, user_input: str) -> str:
        """构建Prompt"""
        schema = ChapterOutputSchema.schema_json(indent=2)

        prompt = cls.CHAPTER_GENERATION.format(
            worldbook_system=context["worldbook"]["system"],
            structured_memory=json.dumps(context["structured"], ensure_ascii=False),
            vector_summaries="\n".join([v["content"] for v in context["vector"]["summaries"]]),
            user_prompt=user_input,
            json_schema=schema,
        )

        return prompt
```

#### 输出清洗器
```python
# core/prompt/output_cleaner.py
import re
import json

class OutputCleaner:
    """LLM输出清洗器"""

    # 清洗规则
    PATTERNS = [
        (r'<think>.*?</think>', ''),           # 移除思维链
        (r'<internal>.*?</internal>', ''),     # 移除内部标记
        (r'```json\n(.*?)\n```', r'\1'),       # 提取JSON
        (r'【.*?】', ''),                       # 移除中文标记（可选）
    ]

    def clean(self, raw_output: str) -> str:
        """清洗LLM输出"""
        cleaned = raw_output

        # 应用清洗规则
        for pattern, replacement in self.PATTERNS:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.DOTALL)

        # 尝试解析JSON
        try:
            data = json.loads(cleaned)
            # 验证Schema
            validated = ChapterOutputSchema(**data)
            return validated.content  # 返回正文
        except json.JSONDecodeError:
            # JSON解析失败，返回原文（降级）
            logger.warning("Failed to parse JSON output, returning raw text")
            return cleaned
        except ValidationError as e:
            # Schema验证失败
            logger.error(f"Output validation failed: {e}")
            raise

    def validate_and_extract(self, raw_output: str) -> ChapterOutputSchema:
        """验证并提取结构化数据"""
        cleaned = self.clean(raw_output)
        data = json.loads(cleaned)
        return ChapterOutputSchema(**data)
```

#### Token 预算管理
```python
# core/prompt/compressor.py
import tiktoken

class TokenBudgetManager:
    """Token预算管理器"""

    def __init__(self, model: str = "gpt-4"):
        self.encoder = tiktoken.encoding_for_model(model)

    def count_tokens(self, text: str) -> int:
        """计算token数"""
        return len(self.encoder.encode(text))

    def trim_to_budget(
        self,
        texts: list[tuple[str, int]],  # [(text, max_tokens), ...]
        total_budget: int = 12000,
    ) -> list[str]:
        """裁剪到总预算"""
        results = []
        remaining = total_budget

        for text, max_tokens in texts:
            tokens = self.count_tokens(text)

            if tokens <= max_tokens and remaining >= tokens:
                results.append(text)
                remaining -= tokens
            elif remaining >= max_tokens:
                # 截断文本
                truncated = self._truncate(text, max_tokens)
                results.append(truncated)
                remaining -= max_tokens
            else:
                # 预算耗尽，跳过
                logger.warning(f"Budget exhausted, skipping context")
                break

        return results

    def _truncate(self, text: str, max_tokens: int) -> str:
        """截断文本到指定token数"""
        tokens = self.encoder.encode(text)
        if len(tokens) <= max_tokens:
            return text

        truncated_tokens = tokens[:max_tokens - 10]  # 留余量
        return self.encoder.decode(truncated_tokens) + "...[截断]"
```

---

## 六、安全与权限设计

### 6.1 API Key 管理

#### 方案选择（历史参考）：前端存储 + 后端透传

```typescript
// frontend/src/services/llm-config.ts
/**
 * 注意：demo 的 MVP 契约已在 `mvp开发计划.md` v2.4 变更为“API Key/Base URL 等贵重信息必须落库（llm_profiles）”。
 * 本段代码仅作为历史方案参考，现行实现不再以 localStorage 作为唯一来源。
 */
export class LLMConfigService {
  private static KEY_PREFIX = 'llm_key_';

  // 保存到本地存储（加密）
  static saveAPIKey(projectId: string, provider: string, apiKey: string) {
    const encrypted = CryptoJS.AES.encrypt(apiKey, projectId).toString();
    localStorage.setItem(`${this.KEY_PREFIX}${projectId}_${provider}`, encrypted);
  }

  // 读取并解密
  static getAPIKey(projectId: string, provider: string): string | null {
    const encrypted = localStorage.getItem(`${this.KEY_PREFIX}${projectId}_${provider}`);
    if (!encrypted) return null;

    const decrypted = CryptoJS.AES.decrypt(encrypted, projectId);
    return decrypted.toString(CryptoJS.enc.Utf8);
  }

  // API调用时携带Key
  static async generateChapter(chapterId: string, prompt: string) {
    const apiKey = this.getAPIKey(projectId, 'openai');

    return axios.post('/chapters/generate', {
      chapter_id: chapterId,
      prompt: prompt,
      llm_config: {
        provider: 'openai',
        api_key: apiKey,  // 请求时传递
        model: 'gpt-4',
      },
    });
  }
}
```

#### 后端：透传模式（不存储）
```python
# api/v1/chapters.py
from app.core.security import sanitize_api_key

@router.post("/{chapter_id}/generate")
async def generate_chapter(
    chapter_id: str,
    request: GenerateRequest,
    current_user: User = Depends(get_current_user),
):
    """生成章节（API Key 从请求中获取）"""

    # 1. 验证API Key格式（不存储）
    if not request.llm_config.api_key:
        raise HTTPException(400, "API Key is required")

    # 2. 脱敏记录日志
    sanitized_key = sanitize_api_key(request.llm_config.api_key)
    logger.info(f"User {current_user.id} generating with key: {sanitized_key}")

    # 3. 透传给LLM Provider
    async for chunk in generation_service.generate_stream(
        chapter_id=chapter_id,
        llm_config=request.llm_config,  # 临时使用，不存储
    ):
        yield chunk

    # 4. 审计日志（脱敏）
    await audit_log(
        user_id=current_user.id,
        action="llm_call",
        metadata={
            "provider": request.llm_config.provider,
            "model": request.llm_config.model,
            "key_prefix": sanitized_key,  # sk-***abc
        },
    )
```

#### 可选：后端加密存储
```python
# core/security/encryption.py
from cryptography.fernet import Fernet
import os

class APIKeyEncryption:
    """API Key 加密存储（可选方案）"""

    def __init__(self):
        # 从环境变量读取加密密钥
        self.key = os.getenv("ENCRYPTION_KEY").encode()
        self.cipher = Fernet(self.key)

    def encrypt(self, api_key: str) -> str:
        """加密API Key"""
        return self.cipher.encrypt(api_key.encode()).decode()

    def decrypt(self, encrypted_key: str) -> str:
        """解密API Key"""
        return self.cipher.decrypt(encrypted_key.encode()).decode()

# 使用示例
# llm_config.api_key_encrypted = encryption.encrypt(api_key)
# api_key = encryption.decrypt(llm_config.api_key_encrypted)
```

### 6.2 RBAC 权限控制

#### 角色定义
```python
# models/user.py
from enum import Enum

class UserRole(str, Enum):
    ADMIN = "admin"        # 管理员：查看所有项目、审计日志
    USER = "user"          # 普通用户：仅访问自己的项目

# 扩展用户表
class User(Base):
    __tablename__ = "users"

    id = Column(UUID, primary_key=True, default=uuid4)
    username = Column(String(50), unique=True)
    email = Column(String(100), unique=True)
    password_hash = Column(String(255))
    role = Column(Enum(UserRole), default=UserRole.USER)  # 【新增】
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

#### 权限装饰器
```python
# core/security/rbac.py
from fastapi import Depends, HTTPException
from functools import wraps

def require_role(role: UserRole):
    """权限检查装饰器"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, current_user: User = Depends(get_current_user), **kwargs):
            if current_user.role != role and current_user.role != UserRole.ADMIN:
                raise HTTPException(403, "Insufficient permissions")
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator

def require_project_owner(func):
    """项目所有权检查"""
    @wraps(func)
    async def wrapper(
        project_id: str,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
        *args,
        **kwargs
    ):
        project = await db.get(Project, project_id)
        if not project:
            raise HTTPException(404, "Project not found")

        # 仅管理员或项目所有者可访问
        if project.user_id != current_user.id and current_user.role != UserRole.ADMIN:
            raise HTTPException(403, "Access denied")

        return await func(project_id=project_id, current_user=current_user, db=db, *args, **kwargs)
    return wrapper
```

#### 使用示例
```python
# api/v1/projects.py
@router.get("/{project_id}")
@require_project_owner
async def get_project(
    project_id: str,
    current_user: User,
    db: AsyncSession,
):
    """获取项目详情（仅所有者或管理员）"""
    project = await db.get(Project, project_id)
    return project

@router.get("/admin/audit-logs")
@require_role(UserRole.ADMIN)
async def get_audit_logs(
    current_user: User,
    db: AsyncSession,
):
    """查看审计日志（仅管理员）"""
    logs = await db.execute(select(AuditLog).limit(100))
    return logs.scalars().all()
```

### 6.3 限流与配额

#### 限流器（基于Redis滑动窗口）
```python
# core/security/rate_limiter.py
import time
from redis import Redis

class RateLimiter:
    """滑动窗口限流器"""

    def __init__(self, redis: Redis):
        self.redis = redis

    async def check_rate_limit(
        self,
        key: str,
        limit: int,
        window: int = 60,  # 秒
    ) -> tuple[bool, int]:
        """检查是否超过限流

        Returns:
            (是否允许, 剩余配额)
        """
        now = time.time()
        window_start = now - window

        pipe = self.redis.pipeline()

        # 移除窗口外的记录
        pipe.zremrangebyscore(key, 0, window_start)
        # 统计窗口内请求数
        pipe.zcard(key)
        # 添加当前请求
        pipe.zadd(key, {str(now): now})
        # 设置过期时间
        pipe.expire(key, window + 10)

        results = pipe.execute()
        request_count = results[1]

        if request_count >= limit:
            return False, 0

        return True, limit - request_count - 1
```

#### 使用限流中间件
```python
# api/deps.py
from fastapi import Request, HTTPException

async def check_rate_limit(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """全局限流检查"""
    limiter = request.app.state.rate_limiter

    # 每用户每分钟60次请求
    key = f"ratelimit:{current_user.id}:{request.url.path}"
    allowed, remaining = await limiter.check_rate_limit(
        key=key,
        limit=60,
        window=60,
    )

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": "60"},
        )

    # 添加响应头
    request.state.rate_limit_remaining = remaining
```

#### Token配额管理
```python
# core/security/quota.py
from datetime import date

class QuotaManager:
    """Token配额管理器"""

    def __init__(self, redis: Redis):
        self.redis = redis

    async def check_quota(
        self,
        user_id: str,
        model: str,
        tokens_needed: int,
        daily_limit: int = 100000,  # 每日10万token
    ) -> bool:
        """检查token配额"""
        today = date.today().isoformat()
        key = f"quota:{user_id}:{model}:{today}"

        used = await self.redis.get(key) or 0
        used = int(used)

        if used + tokens_needed > daily_limit:
            return False

        # 增加使用量
        await self.redis.incrby(key, tokens_needed)
        await self.redis.expire(key, 86400 * 2)  # 保留2天

        return True

    async def record_usage(
        self,
        user_id: str,
        model: str,
        tokens_used: int,
        cost: float,
    ):
        """记录实际使用量"""
        today = date.today().isoformat()

        # 更新token统计
        token_key = f"quota:{user_id}:{model}:{today}"
        await self.redis.incrby(token_key, tokens_used)

        # 更新成本统计
        cost_key = f"cost:{user_id}:{today}"
        await self.redis.incrbyfloat(cost_key, cost)

        # 审计日志
        await audit_log(
            user_id=user_id,
            action="llm_usage",
            metadata={
                "model": model,
                "tokens": tokens_used,
                "cost": cost,
                "date": today,
            },
        )
```

### 6.4 审计日志

#### 日志记录
```python
# core/security/audit.py
from sqlalchemy.ext.asyncio import AsyncSession
from models.audit_log import AuditLog

async def audit_log(
    user_id: str,
    action: str,
    db: AsyncSession,
    project_id: str = None,
    resource_type: str = None,
    resource_id: str = None,
    metadata: dict = None,
    ip_address: str = None,
):
    """记录审计日志"""
    log = AuditLog(
        user_id=user_id,
        project_id=project_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata or {},
        ip_address=ip_address,
    )
    db.add(log)
    await db.commit()
```

#### 日志查询API
```python
# api/v1/admin.py
@router.get("/audit-logs")
@require_role(UserRole.ADMIN)
async def get_audit_logs(
    user_id: str = None,
    action: str = None,
    start_date: date = None,
    end_date: date = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """查询审计日志（管理员）"""
    query = select(AuditLog)

    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if action:
        query = query.where(AuditLog.action == action)
    if start_date:
        query = query.where(AuditLog.created_at >= start_date)
    if end_date:
        query = query.where(AuditLog.created_at <= end_date)

    query = query.order_by(AuditLog.created_at.desc()).limit(limit)

    result = await db.execute(query)
    logs = result.scalars().all()

    # 计算统计信息
    stats = await db.execute(
        select(
            func.sum(AuditLog.metadata["tokens"].astext.cast(Integer)).label("total_tokens"),
            func.sum(AuditLog.metadata["cost"].astext.cast(Float)).label("total_cost"),
        )
        .where(AuditLog.user_id == user_id if user_id else true())
    )

    return {
        "logs": [log.to_dict() for log in logs],
        "stats": stats.first()._asdict(),
    }
```

---

## 七、可观测性方案

### 7.1 结构化日志

#### Structlog 配置
```python
# core/observability/logger.py
import structlog
import logging

def configure_logging():
    """配置结构化日志"""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),  # JSON格式输出
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

# 使用示例
logger = structlog.get_logger()

logger.info(
    "chapter_generated",
    user_id=user.id,
    chapter_id=chapter.id,
    model="gpt-4",
    tokens=1500,
    duration_ms=3200,
)
```

#### 日志脱敏
```python
# core/security/__init__.py
def sanitize_api_key(api_key: str) -> str:
    """脱敏API Key"""
    if not api_key or len(api_key) < 8:
        return "***"
    return f"{api_key[:3]}***{api_key[-4:]}"

def sanitize_email(email: str) -> str:
    """脱敏邮箱"""
    parts = email.split('@')
    if len(parts) != 2:
        return "***@***"
    return f"{parts[0][:2]}***@{parts[1]}"
```

### 7.2 Prometheus 指标

#### 指标定义
```python
# core/observability/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# 请求计数器
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

# LLM调用计数
llm_calls_total = Counter(
    "llm_calls_total",
    "Total LLM API calls",
    ["provider", "model", "status"],
)

# LLM调用延迟
llm_call_duration_seconds = Histogram(
    "llm_call_duration_seconds",
    "LLM API call duration",
    ["provider", "model"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60],
)

# Token使用量
llm_tokens_used = Counter(
    "llm_tokens_used_total",
    "Total LLM tokens consumed",
    ["provider", "model", "user_id"],
)

# 成本统计
llm_cost_usd = Counter(
    "llm_cost_usd_total",
    "Total LLM cost in USD",
    ["provider", "model", "user_id"],
)

# 活跃SSE连接数
active_sse_connections = Gauge(
    "active_sse_connections",
    "Number of active SSE connections",
)

# 异步队列任务
arq_jobs_total = Counter(
    "arq_jobs_total",
    "Total Arq jobs",
    ["job_type", "status"],
)

arq_job_duration_seconds = Histogram(
    "arq_job_duration_seconds",
    "Arq job duration",
    ["job_type"],
)
```

#### 使用示例
```python
# services/generation_service.py
import time

async def generate_chapter_stream(chapter_id: str, config: LLMConfig):
    start_time = time.time()

    try:
        async for chunk in llm_provider.generate_stream(...):
            yield chunk

        # 记录成功
        llm_calls_total.labels(
            provider=config.provider,
            model=config.model,
            status="success",
        ).inc()

    except Exception as e:
        # 记录失败
        llm_calls_total.labels(
            provider=config.provider,
            model=config.model,
            status="error",
        ).inc()
        raise

    finally:
        # 记录延迟
        duration = time.time() - start_time
        llm_call_duration_seconds.labels(
            provider=config.provider,
            model=config.model,
        ).observe(duration)

        # 记录token使用（假设从响应中获取）
        tokens_used = 1500  # 示例
        cost = calculate_cost(config.model, tokens_used)

        llm_tokens_used.labels(
            provider=config.provider,
            model=config.model,
            user_id=user.id,
        ).inc(tokens_used)

        llm_cost_usd.labels(
            provider=config.provider,
            model=config.model,
            user_id=user.id,
        ).inc(cost)
```

#### Prometheus 配置
```yaml
# prometheus/prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'ainovel-backend'
    static_configs:
      - targets: ['backend:8000']
    metrics_path: '/metrics'
```

#### Grafana 仪表板
```json
{
  "dashboard": {
    "title": "ainovel - LLM Metrics",
    "panels": [
      {
        "title": "LLM Calls (Success vs Error)",
        "targets": [
          {
            "expr": "rate(llm_calls_total{status=\"success\"}[5m])"
          },
          {
            "expr": "rate(llm_calls_total{status=\"error\"}[5m])"
          }
        ]
      },
      {
        "title": "LLM Call Duration (P50, P95, P99)",
        "targets": [
          {
            "expr": "histogram_quantile(0.5, rate(llm_call_duration_seconds_bucket[5m]))"
          },
          {
            "expr": "histogram_quantile(0.95, rate(llm_call_duration_seconds_bucket[5m]))"
          }
        ]
      },
      {
        "title": "Daily Token Usage by User",
        "targets": [
          {
            "expr": "increase(llm_tokens_used_total[1d])"
          }
        ]
      },
      {
        "title": "Daily Cost by Model",
        "targets": [
          {
            "expr": "increase(llm_cost_usd_total[1d])"
          }
        ]
      }
    ]
  }
}
```

### 7.3 OpenTelemetry 追踪（可选）

#### 配置
```python
# core/observability/tracer.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter

def configure_tracing():
    """配置分布式追踪"""
    trace.set_tracer_provider(TracerProvider())

    jaeger_exporter = JaegerExporter(
        agent_host_name="jaeger",
        agent_port=6831,
    )

    trace.get_tracer_provider().add_span_processor(
        BatchSpanProcessor(jaeger_exporter)
    )

tracer = trace.get_tracer(__name__)
```

#### 使用示例
```python
# services/generation_service.py
@tracer.start_as_current_span("generate_chapter")
async def generate_chapter_stream(chapter_id: str):
    with tracer.start_as_current_span("retrieve_context"):
        context = await retriever.retrieve(...)

    with tracer.start_as_current_span("llm_call"):
        async for chunk in llm_provider.generate_stream(...):
            yield chunk

    with tracer.start_as_current_span("update_memory"):
        await memory_service.update(...)
```

---

## 八、前端交互流程（补充）

### 8.1 上下文预览组件

```typescript
// components/ContextPreview.tsx
/**
 * 上下文盒组件：展示即将注入的上下文
 */
interface ContextPreviewProps {
  context: RetrievedContext;
}

export function ContextPreview({ context }: ContextPreviewProps) {
  return (
    <Card title="上下文预览" size="small">
      <Collapse>
        <Panel header={`世界书 (${context.worldbook.length}条)`} key="worldbook">
          {context.worldbook.map((item, i) => (
            <Tag key={i} color={item.is_constant ? 'gold' : 'blue'}>
              {item.name} [{item.position}]
            </Tag>
          ))}
        </Panel>

        <Panel header={`结构化记忆 (${context.structured.events.length}个事件)`} key="structured">
          <Timeline>
            {context.structured.events.map((event, i) => (
              <Timeline.Item key={i}>
                <strong>{event.title}</strong>
                <p>{event.description}</p>
              </Timeline.Item>
            ))}
          </Timeline>
        </Panel>

        <Panel header={`向量检索 (${context.vector.summaries.length}章)`} key="vector">
          {context.vector.summaries.map((item, i) => (
            <Card size="small" key={i} style={{ marginBottom: 8 }}>
              <Text type="secondary">相似度: {(item.similarity * 100).toFixed(1)}%</Text>
              <Paragraph ellipsis={{ rows: 2 }}>{item.content}</Paragraph>
            </Card>
          ))}
        </Panel>
      </Collapse>

      <Divider />

      <Space>
        <Text type="secondary">Token预算：</Text>
        <Progress
          percent={(context.metadata.token_usage.total / 12000) * 100}
          size="small"
          status={context.metadata.truncated ? 'exception' : 'normal'}
        />
        <Text>{context.metadata.token_usage.total} / 12000</Text>
      </Space>
    </Card>
  );
}
```

### 8.2 版本选稿面板

```typescript
// components/VersionSelector.tsx
/**
 * 多版本对比与选稿组件
 */
interface VersionSelectorProps {
  chapterId: string;
  versions: ChapterVersion[];
  reviews: Review[];
  onSelect: (versionId: string) => void;
}

export function VersionSelector({ versions, reviews, onSelect }: VersionSelectorProps) {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  // 差异高亮
  const getDiff = (v1: string, v2: string) => {
    const diff = Diff.diffChars(v1, v2);
    return diff.map((part, i) => (
      <span
        key={i}
        style={{
          backgroundColor: part.added ? '#b7eb8f' : part.removed ? '#ffccc7' : 'transparent',
        }}
      >
        {part.value}
      </span>
    ));
  };

  return (
    <div>
      <Row gutter={16}>
        {versions.map(version => {
          const review = reviews.find(r => r.chapter_version_id === version.id);

          return (
            <Col span={12} key={version.id}>
              <Card
                title={`版本 ${version.version}`}
                extra={
                  <Button
                    type="primary"
                    disabled={version.is_selected}
                    onClick={() => onSelect(version.id)}
                  >
                    {version.is_selected ? '已采纳' : '采纳此版本'}
                  </Button>
                }
              >
                {review && (
                  <Alert
                    message={`AI评分: ${review.score}/10`}
                    description={review.summary}
                    type={review.score >= 7 ? 'success' : 'warning'}
                    style={{ marginBottom: 16 }}
                  />
                )}

                <Paragraph ellipsis={{ rows: 10, expandable: true }}>
                  {version.content}
                </Paragraph>

                <Divider />

                <Statistic title="字数" value={version.word_count} />
              </Card>
            </Col>
          );
        })}
      </Row>

      {selectedIds.length === 2 && (
        <Card title="差异对比" style={{ marginTop: 16 }}>
          <pre style={{ whiteSpace: 'pre-wrap' }}>
            {getDiff(
              versions.find(v => v.id === selectedIds[0])!.content,
              versions.find(v => v.id === selectedIds[1])!.content
            )}
          </pre>
        </Card>
      )}
    </div>
  );
}
```

### 8.3 分支/重生入口

```typescript
// pages/Editor/ChapterView.tsx
export function ChapterView() {
  const [showBranchModal, setShowBranchModal] = useState(false);

  return (
    <div>
      {/* 章节工具栏 */}
      <Space style={{ marginBottom: 16 }}>
        <Button
          icon={<ThunderboltOutlined />}
          onClick={() => generateChapter()}
        >
          生成章节
        </Button>

        <Button
          icon={<BranchesOutlined />}
          onClick={() => setShowBranchModal(true)}
        >
          创建分支
        </Button>

        <Button
          icon={<RedoOutlined />}
          onClick={() => regenerateFromPoint()}
        >
          从此处重生
        </Button>
      </Space>

      {/* 分支创建弹窗 */}
      <Modal
        title="创建剧情分支"
        visible={showBranchModal}
        onOk={handleCreateBranch}
        onCancel={() => setShowBranchModal(false)}
      >
        <Form>
          <Form.Item label="分支点">
            <Select placeholder="选择分支起点章节">
              {chapters.map(ch => (
                <Option key={ch.id} value={ch.id}>
                  第{ch.number}章 - {ch.title}
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item label="分支方向">
            <TextArea
              rows={4}
              placeholder="描述分支剧情走向..."
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
```

---

## 九、开发路线图（细化版）

### 9.1 并行轨道策略

```
功能流（Feature Track）:  世界观 → 大纲 → 章节 → 选稿 → 记忆
平台流（Platform Track）: 观测 → 安全 → DevOps
```

### Phase 1: MVP 可用主链路（Week 1-8）

#### Week 1-2: 基础设施
**功能流**：
- [ ] 后端项目初始化（FastAPI + SQLAlchemy + Alembic）
- [ ] 前端项目初始化（React + Vite + TailwindCSS + Ant Design）
- [ ] 数据库设计与迁移脚本
- [ ] 用户认证系统（注册/登录/JWT + RBAC）

**平台流**：
- [ ] Structlog 日志配置
- [ ] Prometheus 指标暴露（/metrics端点）
- [ ] Docker Compose 配置（dev环境）
- [ ] Redis 集成（限流/会话）

**DoD (Definition of Done)**：
- ✅ 用户可注册登录
- ✅ JWT Token 正常签发
- ✅ RBAC 权限检查生效
- ✅ 日志以JSON格式输出
- ✅ /metrics 端点返回基础指标
- ✅ `docker-compose up` 可一键启动

**性能基线**：
- 登录响应 < 500ms
- JWT验证 < 50ms

---

#### Week 3-4: 项目与设定管理
**功能流**：
- [ ] 项目CRUD（创建/列表/删除/更新）
- [ ] LLM配置管理（多Provider支持）
- [ ] 世界观设定（手动编辑）
- [ ] 角色管理（CRUD）

**平台流**：
- [ ] API Key 加密存储（可选）或前端存储方案
- [ ] 审计日志：记录项目创建/删除
- [ ] 限流中间件（60req/min/user）

**DoD**：
- ✅ 用户可创建项目并配置LLM
- ✅ 支持OpenAI/自定义API
- ✅ 世界观表单可保存
- ✅ 角色列表可增删改查
- ✅ 审计日志记录操作

**性能基线**：
- 项目列表加载 < 1s
- 角色列表加载 < 500ms

---

#### Week 5-6: 大纲系统
**功能流**：
- [ ] 大纲数据模型（卷/章节计划）
- [ ] 大纲AI生成（SSE流式）
- [ ] 大纲树形编辑界面
- [ ] 大纲手动调整（拖拽排序）

**平台流**：
- [ ] SSE 心跳机制
- [ ] 前端重连逻辑
- [ ] LLM调用指标（llm_calls_total）
- [ ] Token使用统计

**DoD**：
- ✅ AI可生成3卷大纲
- ✅ SSE 流式输出正常
- ✅ 心跳每5秒发送
- ✅ 断线后自动重连（最多3次）
- ✅ Prometheus 记录LLM调用

**性能基线**：
- 大纲生成首包 < 2s
- SSE 不中断（60s内）
- 心跳延迟 < 100ms

---

#### Week 7-8: 章节生成与选稿
**功能流**：
- [ ] 章节生成服务（SSE流式）
- [ ] 富文本编辑器（TipTap/Quill）
- [ ] 章节版本管理（is_selected字段）
- [ ] 多版本生成（一次生成3个版本）
- [ ] 版本选稿界面
- [ ] 选稿幂等入库

**平台流**：
- [ ] Arq 异步队列集成
- [ ] 继续生成支持（断点恢复）
- [ ] 成本统计（llm_cost_usd）

**DoD**：
- ✅ 用户可生成章节（2000-3000字）
- ✅ 一次生成3个版本供选择
- ✅ 选稿后 is_selected 标记正确
- ✅ 选稿时软删除旧版本记忆（幂等）
- ✅ 断线后可点击"继续生成"
- ✅ 异步队列正常运行

**性能基线**：
- 章节生成 < 60s
- 首包响应 < 2s
- SSE 不中断
- 选稿操作 < 1s（事务提交）

---

### Phase 2: 记忆系统 v1（Week 9-12）

#### Week 9-10: 向量记忆
**功能流**：
- [ ] pgvector 扩展安装
- [ ] 向量记忆表（扩展 version_id/deleted_at）
- [ ] 摘要自动生成（异步任务）
- [ ] 向量嵌入（异步任务）
- [ ] 向量检索（分池Top-K）

**平台流**：
- [ ] Arq任务监控（arq_jobs_total）
- [ ] 失败重试策略

**DoD**：
- ✅ 选稿后自动生成摘要并嵌入
- ✅ 向量检索返回Top3相关章节
- ✅ 幂等更新：选稿前软删除旧向量
- ✅ Arq任务成功率 > 95%

**性能基线**：
- 摘要生成 < 10s
- 向量嵌入 < 5s
- 向量检索 < 200ms

---

#### Week 11-12: 世界书与结构化记忆
**功能流**：
- [ ] 世界书管理界面
- [ ] 关键词匹配注入
- [ ] 事件表（events）
- [ ] 时间线表（timelines）
- [ ] 伏笔表（foreshadows）
- [ ] 事件抽取（异步任务）
- [ ] 三段式检索整合

**平台流**：
- [ ] 上下文预览组件（前端）
- [ ] Token预算可视化

**DoD**：
- ✅ 世界书条目可触发注入
- ✅ 事件自动抽取并入库
- ✅ 伏笔追踪表可查看
- ✅ 三段检索优先级正确
- ✅ 上下文盒展示检索结果

**性能基线**：
- 世界书匹配 < 100ms
- 结构化记忆查询 < 200ms
- 事件抽取 < 15s

---

### Phase 3: 稳健性与优化（Week 13-16）

#### Week 13-14: 分析与评审
**功能流**：
- [ ] 章节分析服务（人设冲突）
- [ ] 伏笔检测
- [ ] AI评审（异步任务）
- [ ] 评审表（reviews）
- [ ] 一致性检查报告

**平台流**：
- [ ] OTEL 追踪（可选）
- [ ] Grafana 仪表板

**DoD**：
- ✅ AI评审可生成报告
- ✅ 人设冲突可检测
- ✅ 伏笔状态可追踪
- ✅ Grafana 展示关键指标

**性能基线**：
- 评审生成 < 30s
- 一致性检查 < 5s

---

#### Week 15-16: 完善与部署
**功能流**：
- [ ] UI响应式优化（手机端）
- [ ] 项目备份/恢复
- [ ] 导出功能（TXT/Markdown）
- [ ] 错误处理优化

**平台流**：
- [ ] 生产环境Docker配置
- [ ] Nginx配置（限流/缓存）
- [ ] 备份脚本（pg_dump）
- [ ] CI/CD（GitHub Actions）

**DoD**：
- ✅ 手机端可正常使用
- ✅ 项目可全量导出
- ✅ 备份脚本可运行
- ✅ 生产环境可部署

**安全基线**：
- ✅ 限流生效（429返回）
- ✅ RBAC权限隔离
- ✅ 审计日志完整

**性能基线**：
- 首屏加载 < 3s（PC）
- 首屏加载 < 5s（手机）

---

### Phase 4: 高级功能（Week 17+，可选）

- [ ] 自定义Agent接入框架
- [ ] 文风预设管理
- [ ] 对话分支树（dialogue_nodes）
- [ ] 第三方平台对接（番茄小说）
- [ ] API开放接口
- [ ] Webhook 通知

---

## 十、风险防控与降级策略

### 10.1 关键风险点

| 风险 | 影响 | 检测方式 | 降级策略 | 优先级 |
|------|------|---------|---------|-------|
| **LLM API失败** | 生成中断 | 状态码监控 | 重试3次 → 切换备用模型 → 返回友好错误 | P0 |
| **SSE 连接断开** | 用户体验差 | 心跳超时 | 前端自动重连（3次）→ 提示"继续生成" | P0 |
| **向量检索无结果** | 上下文质量差 | 相似度阈值 | 降级：召回最近3章摘要 | P1 |
| **异步任务失败** | 记忆未更新 | Arq失败日志 | 重试3次 → 记录失败日志 → 人工触发 | P1 |
| **数据幂等性失败** | 重复入库 | 唯一约束检查 | 事务回滚 → 重新执行 | P0 |
| **Token配额耗尽** | 无法生成 | Redis配额检查 | 提前提示用户 → 管理员审批临时增额 | P1 |
| **数据库连接池耗尽** | 服务不可用 | 连接池监控 | 等待队列 → 拒绝新请求（503） | P0 |
| **磁盘空间不足** | 无法写入 | 磁盘监控 | 告警 → 清理旧日志 → 扩容 | P1 |

### 10.2 降级策略实现

#### LLM API 失败重试
```python
# core/llm/provider.py
from tenacity import retry, stop_after_attempt, wait_exponential

class LLMProvider:

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def generate_with_retry(self, prompt: str) -> str:
        """带重试的生成"""
        try:
            return await self._call_api(prompt)
        except APIError as e:
            logger.warning(f"LLM API failed: {e}, retrying...")
            raise

    async def generate_with_fallback(self, prompt: str) -> str:
        """带降级的生成"""
        try:
            return await self.generate_with_retry(prompt)
        except Exception as e:
            logger.error(f"All retries failed: {e}")

            # 降级1：切换到备用模型
            if self.fallback_model:
                logger.info(f"Falling back to {self.fallback_model}")
                return await self._call_api(prompt, model=self.fallback_model)

            # 降级2：返回友好错误
            raise HTTPException(
                status_code=503,
                detail="AI服务暂时不可用，请稍后重试或联系管理员",
            )
```

#### 向量检索降级
```python
# core/memory/retriever.py
async def _retrieve_vector_with_fallback(
    self,
    project_id: str,
    query: str,
    current_chapter: int,
    threshold: float = 0.75,
) -> list:
    """向量检索 + 降级"""
    results = await self._vector_search(project_id, query, top_k=5)

    # 过滤低相似度结果
    filtered = [r for r in results if r.similarity >= threshold]

    if filtered:
        return filtered

    # 降级：无高相似度结果时，召回最近3章
    logger.info("Vector search below threshold, falling back to recent chapters")
    recent = await self._get_recent_chapters(project_id, current_chapter, limit=3)

    return [
        {"content": ch.summary, "similarity": 0.0, "fallback": True}
        for ch in recent
    ]
```

#### 异步任务失败处理
```python
# workers/summary.py
from arq import Retry

async def generate_summary_task(ctx, chapter_id: str, version_id: str):
    """生成摘要任务（带重试）"""
    try:
        # 生成摘要
        summary = await llm_provider.generate(...)

        # 保存到数据库
        await db.execute(
            update(ChapterVersion)
            .where(ChapterVersion.id == version_id)
            .values(summary=summary)
        )

    except Exception as e:
        logger.error(f"Summary generation failed: {e}")

        # 重试3次（指数退避）
        if ctx['job_try'] <= 3:
            raise Retry(defer=ctx['job_try'] * 60)  # 1min, 2min, 3min

        # 失败后记录
        await db.execute(
            insert(FailedTask).values(
                task_type="summary",
                resource_id=chapter_id,
                error=str(e),
            )
        )
```

### 10.3 数据备份与迁移

#### 备份脚本
```bash
#!/bin/bash
# scripts/backup.sh

# 配置
BACKUP_DIR="/backups/ainovel"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="ainovel"
DB_USER="ainovel"

# 创建备份目录
mkdir -p $BACKUP_DIR

# 1. PostgreSQL 全量备份（含向量数据）
pg_dump -U $DB_USER -h localhost -F c -b -v -f "$BACKUP_DIR/db_$DATE.dump" $DB_NAME

# 2. 仅备份向量表（更快恢复）
pg_dump -U $DB_USER -h localhost -t vector_memories -F c -f "$BACKUP_DIR/vectors_$DATE.dump" $DB_NAME

# 3. 备份 Redis 数据（可选）
redis-cli --rdb "$BACKUP_DIR/redis_$DATE.rdb"

# 4. 清理7天前的备份
find $BACKUP_DIR -name "*.dump" -mtime +7 -delete

echo "Backup completed: $BACKUP_DIR/db_$DATE.dump"
```

#### 恢复脚本
```bash
#!/bin/bash
# scripts/restore.sh

BACKUP_FILE=$1
DB_NAME="ainovel"
DB_USER="ainovel"

if [ -z "$BACKUP_FILE" ]; then
  echo "Usage: ./restore.sh <backup_file.dump>"
  exit 1
fi

# 停止服务
docker-compose stop backend workers

# 删除旧数据库（危险！）
psql -U postgres -c "DROP DATABASE IF EXISTS $DB_NAME;"
psql -U postgres -c "CREATE DATABASE $DB_NAME;"

# 安装pgvector扩展
psql -U postgres -d $DB_NAME -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 恢复数据
pg_restore -U $DB_USER -h localhost -d $DB_NAME -v $BACKUP_FILE

# 重启服务
docker-compose start backend workers

echo "Restore completed from $BACKUP_FILE"
```

#### 迁移导出 API
```python
# api/v1/projects.py
@router.post("/{project_id}/export")
async def export_project_full(
    project_id: str,
    include_versions: bool = True,
    include_memory: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """全量导出项目（含选稿版本与记忆）"""

    export_data = {
        "project": await get_project(project_id),
        "world_setting": await get_world_setting(project_id),
        "characters": await get_characters(project_id),
        "outline": await get_outline(project_id),
        "chapters": [],
        "worldbook": [],
        "events": [],
        "foreshadows": [],
    }

    # 导出章节（含已选版本）
    chapters = await db.execute(
        select(Chapter).where(Chapter.project_id == project_id)
    )

    for chapter in chapters.scalars():
        chapter_data = {
            "metadata": chapter.to_dict(),
            "versions": [],
        }

        if include_versions:
            versions = await db.execute(
                select(ChapterVersion).where(
                    ChapterVersion.chapter_id == chapter.id,
                    or_(
                        ChapterVersion.is_selected == True,
                        ChapterVersion.version == 1,  # 保留初版
                    )
                )
            )
            chapter_data["versions"] = [v.to_dict() for v in versions.scalars()]

        export_data["chapters"].append(chapter_data)

    # 导出记忆
    if include_memory:
        export_data["worldbook"] = await get_worldbooks(project_id)
        export_data["events"] = await get_events(project_id, deleted=False)
        export_data["foreshadows"] = await get_foreshadows(project_id)

        # 向量记忆（仅元数据，不含embedding）
        vectors = await db.execute(
            select(VectorMemory.source_type, VectorMemory.source_id, VectorMemory.content)
            .where(
                VectorMemory.project_id == project_id,
                VectorMemory.deleted_at == None,
            )
        )
        export_data["vector_metadata"] = [
            {"source_type": v[0], "source_id": v[1], "content": v[2]}
            for v in vectors
        ]

    # 返回ZIP文件
    zip_buffer = create_zip_archive(export_data)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=project_{project_id}.zip"},
    )
```

---

## 十一、部署方案（完整版）

### 11.1 开发环境

```bash
# 后端
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 安装pgvector
psql -U postgres -c "CREATE EXTENSION vector;"

# 数据库迁移
alembic upgrade head

# 启动后端
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 启动Arq worker
arq app.workers.WorkerSettings

# 前端
cd frontend
npm install
npm run dev
```

### 11.2 Docker Compose（完整版）

```yaml
# docker-compose.yml
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg15
    container_name: ainovel-postgres
    environment:
      POSTGRES_USER: ainovel
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: ainovel
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups  # 备份目录
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ainovel"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - ainovel-network

  redis:
    image: redis:7-alpine
    container_name: ainovel-redis
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    networks:
      - ainovel-network

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: ainovel-backend
    environment:
      DATABASE_URL: postgresql+asyncpg://ainovel:${DB_PASSWORD}@postgres:5432/ainovel
      REDIS_URL: redis://redis:6379
      SECRET_KEY: ${SECRET_KEY}
      ENCRYPTION_KEY: ${ENCRYPTION_KEY}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./backend:/app
    ports:
      - "8000:8000"
    networks:
      - ainovel-network
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000

  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: ainovel-worker
    environment:
      DATABASE_URL: postgresql+asyncpg://ainovel:${DB_PASSWORD}@postgres:5432/ainovel
      REDIS_URL: redis://redis:6379
      SECRET_KEY: ${SECRET_KEY}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./backend:/app
    networks:
      - ainovel-network
    command: arq app.workers.WorkerSettings

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: ainovel-frontend
    environment:
      VITE_API_URL: ${VITE_API_URL:-http://localhost:8000}
    ports:
      - "3000:3000"
    networks:
      - ainovel-network

  nginx:
    image: nginx:alpine
    container_name: ainovel-nginx
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./nginx/conf.d:/etc/nginx/conf.d
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - backend
      - frontend
    networks:
      - ainovel-network

  prometheus:
    image: prom/prometheus:latest
    container_name: ainovel-prometheus
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    networks:
      - ainovel-network

  grafana:
    image: grafana/grafana:latest
    container_name: ainovel-grafana
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-admin}
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
    ports:
      - "3001:3000"
    networks:
      - ainovel-network

volumes:
  postgres_data:
  redis_data:
  prometheus_data:
  grafana_data:

networks:
  ainovel-network:
    driver: bridge
```

### 11.3 Nginx 配置

```nginx
# nginx/conf.d/ainovel.conf
upstream backend {
    server backend:8000;
}

upstream frontend {
    server frontend:3000;
}

# 限流配置
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=sse_limit:10m rate=2r/s;

server {
    listen 80;
    server_name localhost;

    # 前端
    location / {
        proxy_pass http://frontend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    # API
    location /api/ {
        limit_req zone=api_limit burst=20 nodelay;

        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 超时设置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # SSE 流式接口
    location /api/v1/chapters/ {
        limit_req zone=sse_limit burst=5 nodelay;

        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;

        # SSE 特殊设置
        proxy_read_timeout 300s;  # 5分钟
        chunked_transfer_encoding on;

        # 禁用缓存
        add_header Cache-Control 'no-cache';
        add_header X-Accel-Buffering 'no';
    }

    # 健康检查
    location /health {
        access_log off;
        proxy_pass http://backend/health;
    }

    # Prometheus 指标（仅内部访问）
    location /metrics {
        allow 172.16.0.0/12;  # Docker 网络
        deny all;
        proxy_pass http://backend/metrics;
    }
}
```

### 11.4 环境变量

```env
# .env.example

# ========== 数据库 ==========
DB_PASSWORD=your_secure_password_here
DATABASE_URL=postgresql+asyncpg://ainovel:${DB_PASSWORD}@postgres:5432/ainovel

# ========== 安全 ==========
SECRET_KEY=your_jwt_secret_key_min_32_chars
ENCRYPTION_KEY=your_fernet_encryption_key  # 使用 Fernet.generate_key()

# ========== Redis ==========
REDIS_URL=redis://redis:6379/0

# ========== 日志 ==========
LOG_LEVEL=INFO  # DEBUG / INFO / WARNING / ERROR

# ========== LLM（可选默认配置）==========
DEFAULT_LLM_PROVIDER=openai
DEFAULT_LLM_MODEL=gpt-4-turbo-preview
DEFAULT_EMBED_MODEL=text-embedding-ada-002

# ========== 前端 ==========
VITE_API_URL=http://localhost:8000

# ========== 监控 ==========
GRAFANA_PASSWORD=admin

# ========== 限流配额 ==========
RATE_LIMIT_PER_MINUTE=60
DAILY_TOKEN_QUOTA=100000

# ========== 环境标识 ==========
ENVIRONMENT=development  # development / production
```

### 11.5 生产环境差异

| 配置项 | 开发环境 | 生产环境 |
|--------|---------|---------|
| DEBUG模式 | True | False |
| 日志级别 | DEBUG | INFO/WARNING |
| CORS | `*` | 特定域名 |
| HTTPS | 可选 | 必须 |
| SSL证书 | 自签名 | Let's Encrypt |
| 数据库连接池 | 5-10 | 20-50 |
| Redis持久化 | AOF | AOF + RDB |
| 备份频率 | 无 | 每日 + 每周 |
| 监控告警 | 无 | Prometheus Alertmanager |
| 日志聚合 | 本地 | ELK/Loki |

---

## 十二、参考项目

本设计参考了以下开源项目的优秀实践：

| 项目 | 借鉴点 |
|------|--------|
| MuMuAINovel | SSE流式生成、Chroma向量库、Prompt集中管理 |
| 马良AI | LLM可观测性、限流计费、SSE稳健性 |
| NovelForge | 工作流引擎、知识图谱、JSON Schema校验 |
| AI_NovelCraft | 长篇Agent、记忆库、用户自带Key |
| Arboris-Novel | 多版本生成、评审闭环、提示词热更新 |
| WriteHERE | 递归规划、任务图可视化 |
| Narratium.ai | NodeFlow工作流、对话分支、世界书注入 |
| Amily2 | 表格记忆、预设链管理、RAG多池检索 |

---

## 十三、文档维护

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| v1.0 | 2025-11-23 | 初始版本，完成整体设计 |
| v2.0 | 2025-11-23 | 根据专业反馈全面优化：补充一致性方案、数据模型、SSE稳健性、安全、可观测性、Prompt治理、DoD/基线、交互流程、风险防控 |

---

## 十四、下一步行动

1. ✅ 确认 v2.0 设计方案
2. [ ] 创建项目目录结构
3. [ ] 初始化后端项目（FastAPI + Alembic）
4. [ ] 初始化前端项目（React + Vite）
5. [ ] 配置 Docker Compose
6. [ ] 开始 Phase 1 Week 1 开发
