# Living Docs — 会"活着"的团队知识库

> 一个开源的、面向小团队的异步协作社区：文档像生物一样**生长、分叉、枯萎**，团队的每一次互动都在塑造知识的形态。

## 1. 项目定位

| 项 | 内容 |
|---|---|
| 名称 | **Living Docs**（暂定，可改） |
| 一句话 | 文档有生命：被关注则生长，被分叉则演化，被遗忘则枯萎归档 |
| 领域 | 协作 / 内容社区 |
| 目标用户 | 小团队（5–50 人） |
| 协作模式 | 异步为主 + 通知 |
| 定位 | 纯开源玩票（MIT / Apache-2.0），托管公开 demo |
| 阶段目标 | MVP 优先，1–2 周完成核心闭环 |

### 新颖性（核心玩法）

现有知识库（Notion / Outline / Wiki.js）里文档是静态的——写了就躺在那里。
Living Docs 让每篇文档成为一个**生命体**：

1. **生命系统（Life System）**
   - 每篇文档有 `vitality`（生命力）值，由浏览、编辑、评论、引用等互动充能
   - 长期无人互动 → 生命力衰减 → 进入"枯萎（withered）"状态，自动归档、在列表中沉底、视觉变灰
   - 枯萎文档被重新互动可"复苏（revive）"
   - 团队首页是一片"文档花园"：健康的翠绿、枯萎的灰败，一眼看出团队知识哪里活着、哪里死了

2. **分叉演化（Fork & Merge）**
   - 任何文档可以被 fork 成"变体"（变体继承生命力的一部分）
   - 变体独立生长；当变体明显更优（生命力、投票），可发起 merge 回主干
   - 文档有"演化树"可视化：像 Git 分支图一样展示一篇文档的全部后代
   - 由此产生"自然选择"：好内容活下来，坏内容枯萎淘汰

## 2. 技术栈

- **后端**：FastAPI（Python 3.12）+ SQLite（SQLAlchemy 2.x + Alembic 迁移）
- **前端**：Vue 3 + Vite + TypeScript + Pinia + Vue Router，Markdown 编辑用 Milkdown 或 CodeMirror
- **实时**：SSE（Server-Sent Events）做通知推送即可，不上 WebSocket
- **富媒体**：图片/附件上传本地磁盘（demo 限大小），Markdown 内嵌
- **部署**：单 `docker-compose.yml`（backend + 前端静态资源由后端托管）；demo 部署在一台 VPS 或 Fly.io/Render 免费层
- **测试**：pytest（后端）+ Vitest（前端核心逻辑）
- **CI**：GitHub Actions — lint + test + docker build

## 3. 功能范围（MVP）

### 3.1 必须有（MVP 核心闭环）
- [ ] 邮箱+密码注册/登录（JWT），团队（workspace）创建与邀请链接
- [ ] 文档 CRUD：Markdown 编辑、图片上传、标签
- [ ] 生命力引擎：
  - 互动事件（view/edit/comment/fork）累计 vitality
  - 后台定时任务（APScheduler）每日衰减 vitality
  - 状态机：`thriving → stable → fading → withered → (revive)`
- [ ] Fork / Merge：fork 变体、diff 预览、merge 请求与接受
- [ ] 演化树视图（简单树状图，前端 SVG 渲染）
- [ ] 花园首页：文档按生命状态可视化排列
- [ ] 评论（一级，不嵌套）+ SSE 站内通知

### 3.2 明确不做（本期砍掉）
- 实时协同编辑（CRDT）、多人光标
- 嵌套评论、@提及之外的复杂权限
- 全文搜索（MVP 用 SQLite LIKE，后续换 FTS5/Meilisearch）
- 第三方登录、移动端 App、插件系统

## 4. 数据模型（草案）

```
User(id, email, password_hash, display_name, created_at)
Workspace(id, name, slug, owner_id)
Membership(user_id, workspace_id, role)          -- owner/member
Document(id, workspace_id, parent_id nullable,   -- parent_id 非空即 fork 变体
         title, content_md, author_id,
         vitality REAL, status ENUM,
         last_interaction_at, created_at)
Interaction(id, document_id, user_id, kind,      -- view/edit/comment/fork/vote
            energy INT, created_at)              -- 生命力充能事件
MergeRequest(id, source_doc_id, target_doc_id,
             proposer_id, status, created_at)
Comment(id, document_id, author_id, body, created_at)
Attachment(id, document_id, path, uploader_id)
```

**生命力公式（初版）**：
```
vitality += Σ interaction.energy           （view=1, comment=5, edit=8, fork=10）
每日衰减: vitality *= 0.95                  （半衰期约 2 周）
状态阈值: thriving ≥ 60 | stable ≥ 30 | fading ≥ 10 | withered < 10
```

## 5. 里程碑

| 里程碑 | 内容 | 验收标准 |
|---|---|---|
| **M1 骨架**（D1–D2） | 仓库初始化、FastAPI+Vue3 脚手架、docker-compose、CI | `docker compose up` 能打开登录页 |
| **M2 认证与团队**（D3–D4） | 注册/登录/JWT、workspace、邀请链接 | 两个用户能加入同一团队 |
| **M3 文档核心**（D5–D7） | 文档 CRUD、Markdown 编辑渲染、图片上传 | 完整写一篇带图文档 |
| **M4 生命引擎**（D8–D9） | 互动充能、每日衰减任务、状态机、花园首页 | 手工快进时间能看到枯萎/复苏 |
| **M5 分叉演化**（D10–D11） | fork、merge 请求、演化树视图 | 演示分叉→演化→合并全流程 |
| **M6 收尾发布**（D12–D14） | 评论+通知、README、demo 部署、开源协议 | demo 公网可访问，README 有 GIF 演示 |

## 6. 开源准备

- 协议：Apache-2.0
- 仓库：`nsfxdyj/living-docs`（建议）
- 必备文件：`README.md`（含 demo 截图/GIF）、`LICENSE`、`CONTRIBUTING.md`、`docker-compose.yml`、GitHub Actions CI
- 发布渠道：GitHub Release + Show HN / V2EX / 掘金 推广（可选）

## 7. 风险与对策

| 风险 | 对策 |
|---|---|
| 生命引擎参数拍脑袋，体验不好 | 参数全部放配置，M4 用脚本模拟 30 天数据调参 |
| 演化树可视化复杂度膨胀 | MVP 只画直系树，不做交叉合并边 |
| demo 被刷流量/上传滥用 | 附件限 2MB、注册需邀请码、demo 每日重置数据 |
| 范围蔓延 | 3.2 清单即"不做清单"，新想法进 issue backlog |

## 8. 下一步

计划确认后：
1. 在 GitHub 创建仓库 `living-docs`（含 README/LICENSE）
2. 初始化 M1 骨架并跑通 `docker compose up`
3. 按里程碑逐 M 推进，每个 M 结束后跑通验收标准再继续
