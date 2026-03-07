# 项目增强 + 开发任务功能设计方案

## 一、概述

两个新功能：
1. **项目增强** — 项目新增 `code_paths`（多个代码目录），作为 agent 的 `extra_roots` 传入
2. **开发任务（DevTask）** — 项目下创建开发任务，指定分支名，自动从 master 切分支，每个任务有独立对话框

## 二、数据模型变更

### 2.1 Project 表新增字段

```sql
ALTER TABLE projects ADD COLUMN code_paths TEXT DEFAULT '[]';
-- JSON 数组，例如: ["/home/user/lib-a", "/home/user/lib-b"]
```

- `code_paths` 存 JSON 数组字符串
- 创建项目时前端可选择多个代码目录
- 这些路径在 chat 时作为 `extra_roots` 传给 `AgentRunner`

### 2.2 新增 dev_tasks 表

```sql
CREATE TABLE IF NOT EXISTS dev_tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    branch TEXT NOT NULL,
    base_branch TEXT DEFAULT 'master',
    status TEXT DEFAULT 'active',   -- active / completed / archived
    session_id TEXT,                -- 每个任务有独立的 cody session
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

## 三、后端变更

### 3.1 db.py — 数据层

**Project 变更：**
- `Project` dataclass 新增 `code_paths: list[str]`
- `create_project()` 接受 `code_paths` 参数，JSON 序列化存储
- `update_project()` 支持更新 `code_paths`
- `_row_to_project()` 反序列化 `code_paths`
- `_init_db()` 加 migration 逻辑（ALTER TABLE 添加新字段，已存在则忽略）

**DevTask 新增：**
- `DevTask` dataclass
- `create_task(project_id, title, branch, base_branch="master")` → DevTask
- `get_task(task_id)` → DevTask | None
- `list_tasks(project_id)` → list[DevTask]
- `update_task(task_id, status=None, title=None)` → DevTask | None
- `delete_task(task_id)` → bool
- `set_task_session_id(task_id, session_id)` → None

### 3.2 models.py — API 模型

```python
class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    workdir: str
    code_paths: list[str] = []   # 新增

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    code_paths: Optional[list[str]] = None  # 新增

class ProjectResponse(BaseModel):
    ...  # 现有字段
    code_paths: list[str] = []   # 新增

class DevTaskCreate(BaseModel):
    title: str
    branch: str
    base_branch: str = "master"

class DevTaskUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None  # active / completed / archived

class DevTaskResponse(BaseModel):
    id: str
    project_id: str
    title: str
    branch: str
    base_branch: str
    status: str
    session_id: Optional[str] = None
    created_at: str
    updated_at: str
```

### 3.3 routes/tasks.py — 新路由文件

```
POST   /api/projects/{project_id}/tasks          — 创建任务（切分支 + 创建 session）
GET    /api/projects/{project_id}/tasks           — 列出项目下所有任务
GET    /api/projects/{project_id}/tasks/{task_id} — 获取任务详情
PUT    /api/projects/{project_id}/tasks/{task_id} — 更新任务
DELETE /api/projects/{project_id}/tasks/{task_id} — 删除任务
```

**创建任务的流程：**
1. 验证 project 存在
2. 在 project.workdir 下执行 `git checkout -b {branch}` （从 base_branch）
3. 创建独立 cody session
4. 写入 dev_tasks 表

**Git 操作** 通过 `asyncio.create_subprocess_exec` 执行，不依赖 core 工具。

### 3.4 routes/chat.py — 任务对话支持

新增 WebSocket 端点：
```
/ws/chat/{project_id}/task/{task_id}
```

逻辑和现有 `/ws/chat/{project_id}` 基本一致，区别：
- 使用任务自己的 `session_id`
- `AgentRunner` 的 `extra_roots` 从 `project.code_paths` 取
- 执行前先 `git checkout {task.branch}`（确保在正确分支上）

### 3.5 app.py — 注册新路由

在 app.py 中注册任务的 CRUD 端点和新的 WebSocket 端点。

### 3.6 chat.py 修改现有逻辑

现有的 `/ws/chat/{project_id}` 也需要传入 `project.code_paths` 作为 `extra_roots`：
- `get_runner(workdir)` → `get_runner(workdir, extra_roots=code_paths)`

## 四、前端变更

### 4.1 types/index.ts

```typescript
// Project 新增字段
interface Project {
  ...
  code_paths: string[];  // 新增
}

// 新增 DevTask 类型
interface DevTask {
  id: string;
  project_id: string;
  title: string;
  branch: string;
  base_branch: string;
  status: "active" | "completed" | "archived";
  session_id: string | null;
  created_at: string;
  updated_at: string;
}
```

### 4.2 api/client.ts — 新增 API

```typescript
// Project API 更新
createProject(name, workdir, description?, codePaths?)

// DevTask API
createTask(projectId, title, branch, baseBranch?)
listTasks(projectId)
getTask(projectId, taskId)
updateTask(projectId, taskId, data)
deleteTask(projectId, taskId)

// Task chat WebSocket
connectTaskChat(projectId, taskId)  // ws://.../ws/chat/{projectId}/task/{taskId}
```

### 4.3 ProjectWizard.tsx — 支持选择多个代码目录

- 新增一个「添加代码目录」的区域
- 用户可以通过目录浏览器添加多个 code_paths
- 创建项目时一并提交

### 4.4 新页面：ProjectDetailPage.tsx

路由：`/project/:projectId`

展示：
- 项目基本信息（名称、描述、工作目录、代码路径）
- 「创建开发任务」按钮 → 弹出对话框填写任务名和分支名
- 任务列表卡片，点击进入任务对话页

### 4.5 新页面：TaskChatPage.tsx

路由：`/project/:projectId/task/:taskId`

- 复用 `ChatWindow` 组件
- 传入 task 的 `sessionId`
- 显示分支信息 + 任务状态
- WebSocket 连接到 `/ws/chat/{projectId}/task/{taskId}`

### 4.6 Sidebar.tsx 修改

- 项目列表点击进入 ProjectDetailPage（而不是直接进 chat）
- 或者：项目展开后显示其下的任务列表

### 4.7 App.tsx 路由

```tsx
<Route path="/project/:projectId" element={<ProjectDetailPage />} />
<Route path="/project/:projectId/task/:taskId" element={<TaskChatPage />} />
```

保留 `/chat/:projectId` 作为项目级直接对话（向后兼容）。

## 五、实现步骤

1. **后端数据层** — db.py 加 migration + DevTask CRUD
2. **后端模型** — models.py 新增/修改
3. **后端路由** — tasks.py 新文件 + chat.py 修改 + app.py 注册
4. **前端类型** — types/index.ts
5. **前端 API** — client.ts
6. **前端项目创建** — ProjectWizard 支持 code_paths
7. **前端项目详情页** — ProjectDetailPage + 任务创建对话框
8. **前端任务对话页** — TaskChatPage
9. **路由 + 侧边栏** — App.tsx + Sidebar.tsx
10. **样式** — index.css 新增样式
