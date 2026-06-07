# Novel2ScriptConverter — AI 剧本改编工作台

> 将长篇小说文本转化为可编辑的场景化剧本草稿，支持规则引擎 + LLM 混合生成、版本管理和质量审稿。

## 项目简介

本项目是一个**"小说转剧本"智能工作台原型**，核心目标是解决传统小说改编过程中三个痛点：

| 痛点 | 解决方案 |
|------|---------|
| **小说文本难以结构化** | 自动章节分割、人物提取、冲突识别，将平文本转为结构化数据 |
| **改编依赖人工经验** | 规则引擎 + 可选 LLM 增强，自动生成场景节拍、对白和戏剧结构 |
| **剧本修改难以追踪** | 内置版本管理，支持场景级 diff、历史回溯和分支重写 |

### 核心流程

```
上传小说(.txt/.md) → 章节解析 → 剧本生成 → 场景编辑/重写 → 质量审稿 → 版本对比 → 导出(YAML/JSON)
```

### 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 后端框架 | FastAPI | 0.136 |
| 数据校验 | Pydantic | 2.12 |
| 数据库 | SQLite (WAL 模式) | — |
| 前端框架 | Vue 3 + Vite | 3.5 / 6.3 |
| 状态管理 | Pinia | 3.0 |
| HTTP 客户端 | Axios | 1.9 |
| AI/LLM | OpenAI SDK（可选） | ≥1.30 |

### 当前已实现功能

- 项目创建、列表、归档、删除
- 小说源文件上传（支持 `.txt` / `.md`）
- 多格式章节标题识别（第X章、Chapter、Markdown 标题等）
- 人物名启发式提取与关键词分析
- 场景级剧本初稿生成（含节拍、对白、戏剧结构）
- 剧本质量审稿报告（评分、亮点、分项指标、修订建议）
- 单场景在线编辑（标题、目标、节拍列表）
- 指令式场景 AI 重写（节奏压缩、冲突强化、情绪放大、反转前置）
- 版本管理：生成/编辑/重写自动创建版本记录
- 场景级版本对比（新增/删除/修改/未变 + 字段级变化）
- YAML / JSON 格式导出
- 后端自动 schema 校验
- 后端完整 API 流程测试覆盖

### 两种运行模式

| 模式 | 配置 | 说明 |
|------|------|------|
| **规则引擎模式**（默认） | 无需配置 | 纯规则驱动的脚本生成，适合快速原型和演示 |
| **LLM 增强模式** | 设置 `LLM_PROVIDER` | 调用大模型生成初稿、重写场景、审稿，失败时自动降级 |

支持的模型供应商：

| 供应商 | LLM_PROVIDER | 环境变量 | 说明 |
|--------|-------------|---------|------|
| OpenAI | `openai` | `OPENAI_API_KEY` / `LLM_API_KEY` | 默认模型 `gpt-4.1-mini` |
| 阿里云百炼 | `bailian` | `DASHSCOPE_API_KEY` / `LLM_API_KEY` | 默认模型 `qwen-plus` |
| 自定义 | `LLM_BASE_URL` | `LLM_API_KEY` | 指向任意 OpenAI 兼容服务 |

### 项目结构

```
Novel2ScriptConverter/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── api/router.py       # REST API 路由（21 个端点）
│   │   ├── core/
│   │   │   ├── config.py        # 全局配置（路径、LLM 参数）
│   │   │   └── store.py         # SQLite 数据持久层
│   │   ├── schemas.py           # Pydantic 数据模型与校验
│   │   └── services/
│   │       ├── common.py        # 通用工具、状态常量、响应封装
│   │       ├── text_analysis.py # 文本分析（分章、提取人物、关键词）
│   │       ├── script_builder.py# 剧本构建引擎
│   │       ├── scene_rewriter.py# 场景重写服务
│   │       ├── quality_report.py# 质量审稿报告
│   │       ├── script_ops.py    # 剧本操作工具（版本、导出、对比）
│   │       ├── tasks.py         # 异步任务编排
│   │       ├── llm_provider.py  # LLM 调用封装
│   │       └── pipeline.py      # 服务聚合门面
│   ├── tests/                   # Pytest 测试
│   ├── data/                    # 运行时数据（SQLite、上传、导出）
│   └── requirements.txt         # Python 依赖
├── frontend/                    # Vue 3 前端
│   ├── src/
│   │   ├── api/                 # Axios API 封装
│   │   ├── components/          # 通用组件（StatusBanner）
│   │   ├── router/              # Vue Router 路由配置
│   │   ├── stores/              # Pinia 状态管理
│   │   ├── utils/               # 工具函数（YAML 格式化）
│   │   └── views/               # 页面组件
│   │       ├── ImportView.vue   # 导入页：上传小说并初始化
│   │       ├── ProjectsView.vue # 项目列表页
│   │       ├── WorkspaceView.vue# 剧本工作台
│   │       └── VersionsView.vue # 版本记录与对比
│   ├── vite.config.js           # Vite 构建配置
│   └── package.json             # NPM 依赖
├── 开发文档.md                   # 详细开发文档
├── 接口文档.md                   # REST API 接口文档
└── README.md                    # 本文档（项目简介与部署指南）
```

### 已知限制

以下功能尚未实现，属于原型后续迭代范围：

- 生产级 LLM 提示词编排、成本控制与审稿可观测性
- 完整的情节图谱 / 冲突关系建模
- 高保真度原文覆盖评估
- 用户鉴权与多用户隔离
- 前端自动化测试

---

## 部署文档

### 环境要求

| 依赖 | 最低版本 | 说明 |
|------|---------|------|
| Python | 3.10+ | 后端运行环境 |
| Node.js | 18+ | 前端构建环境 |
| npm | 9+ | 前端包管理 |
| pip | 23+ | Python 包管理 |
| 磁盘空间 | ~500 MB | 含 node_modules 依赖 |

### 方式一：开发环境部署

#### 1. 克隆项目

```bash
git clone <your-repo-url>
cd Novel2ScriptConverter
```

#### 2. 后端部署

```bash
# 进入后端目录
cd backend

# 创建虚拟环境（推荐）
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动后端服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

验证后端启动成功：

- Swagger 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/v1/health`

#### 3. 前端部署

```bash
# 打开新终端，进入前端目录
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端访问：`http://127.0.0.1:5173`

#### 4. 配置 LLM（可选）

**OpenAI：**

```bash
# Windows (PowerShell)
$env:LLM_PROVIDER="openai"
$env:OPENAI_API_KEY="<your-openai-api-key>"

# macOS / Linux
export LLM_PROVIDER=openai
export OPENAI_API_KEY=<your-openai-api-key>
```

**阿里云百炼（Qwen 系列）：**

```bash
# Windows (PowerShell)
$env:LLM_PROVIDER="bailian"
$env:DASHSCOPE_API_KEY="<your-dashscope-api-key>"
$env:BAILIAN_MODEL="qwen-plus"    # 可选，默认 qwen-plus

# macOS / Linux
export LLM_PROVIDER=bailian
export DASHSCOPE_API_KEY=<your-dashscope-api-key>
export BAILIAN_MODEL=qwen-plus
```

**自定义 API 地址：**

```bash
export LLM_PROVIDER=openai          # 仍用 openai provider
export LLM_BASE_URL=https://your-api.com/v1
export LLM_API_KEY=<your-compatible-api-key>
export LLM_MODEL=your-model-name
```

不设置以上环境变量时，后端自动使用**规则引擎模式**。

#### 5. 运行测试

```bash
cd backend
pytest -q
```

如果临时目录不可写，使用：
```bash
pytest -q --basetemp .test-tmp -p no:cacheprovider
```

### 方式二：生产环境部署（Linux + systemd）

```bash
# 1. 安装系统依赖
sudo apt update && sudo apt install python3.11 python3.11-venv nginx -y

# 2. 部署后端代码
sudo mkdir -p /opt/novel2script
sudo cp -r backend /opt/novel2script/
cd /opt/novel2script/backend

# 3. 创建虚拟环境并安装依赖
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. 创建数据目录
mkdir -p data/uploads data/exports

# 5. 配置环境变量
cat > /opt/novel2script/backend/.env << 'EOF'
LLM_PROVIDER=rule
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
EOF

# 6. 创建 systemd 服务
sudo tee /etc/systemd/system/novel2script.service > /dev/null << 'EOF'
[Unit]
Description=Novel2Script Backend Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/novel2script/backend
EnvironmentFile=/opt/novel2script/backend/.env
ExecStart=/opt/novel2script/backend/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 7. 启动服务
sudo systemctl daemon-reload
sudo systemctl enable novel2script
sudo systemctl start novel2script
sudo systemctl status novel2script

# 8. 构建前端生产版本
cd ../frontend
npm ci --production
npm run build
```

#### Nginx 反向代理配置

```nginx
# /etc/nginx/sites-available/novel2script
server {
    listen 80;
    server_name your-domain.com;

    # 前端静态文件
    root /opt/novel2script/frontend/dist;
    index index.html;

    # 前端 SPA 路由回退（Vue Router history 模式）
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理到后端
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 50m;
    }
}
```

启用站点：

```bash
sudo ln -s /etc/nginx/sites-available/novel2script /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 方式三：Docker 部署

创建 `docker-compose.yml`：

```yaml
version: "3.8"

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: novel2script-backend
    ports:
      - "8000:8000"
    environment:
      - LLM_PROVIDER=${LLM_PROVIDER:-rule}
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
      - OPENAI_MODEL=${OPENAI_MODEL:-gpt-4.1-mini}
    volumes:
      - ./backend/data:/app/data
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: novel2script-frontend
    ports:
      - "80:80"
    depends_on:
      - backend
    restart: unless-stopped
```

**`backend/Dockerfile`**：

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
RUN mkdir -p data/uploads data/exports

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**`frontend/Dockerfile`**：

```dockerfile
FROM node:18-alpine AS builder
WORKDIR /build
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

创建 `frontend/nginx.conf`：

```nginx
server {
    listen 80;
    server_name localhost;

    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        client_max_body_size 50m;
    }
}
```

启动：

```bash
docker-compose up -d
```

### 数据库与备份

| 数据 | 路径 | 说明 |
|------|------|------|
| SQLite 数据库 | `backend/data/studio.sqlite3` | 项目、任务、剧本所有数据 |
| 上传文件 | `backend/data/uploads/` | 用户上传的小说源文件 |
| 导出文件 | `backend/data/exports/` | YAML/JSON 导出产物 |
| 旧版数据 | `backend/data/store.json` | 首次启动时自动迁移到 SQLite |

**建议：定期备份 `backend/data/` 整个目录。**

### 常见问题

| 问题 | 解决方案 |
|------|---------|
| 前端无法连接后端 | 检查后端是否在 8000 端口启动，Vite proxy 配置是否正确 |
| 中文显示乱码 | 上传文件请使用 UTF-8 编码保存（后端已支持 GBK 自动降级检测） |
| LLM 调用失败 | 检查 API Key 是否正确、供应商是否有额度；百炼需确认模型开通状态 |
| LLM 返回非标准格式 | 设置了 `response_format: json_object`，如模型不支持会自动降级解析 |
| 端口被占用 | 修改 `--port` 参数或 `vite.config.js` 中的 proxy target |
| 权限错误 | 确保后端进程对 `data/` 目录有读写权限 |
| CORS 错误 | 检查 `main.py` 中 `allow_origins` 是否包含前端地址 |
