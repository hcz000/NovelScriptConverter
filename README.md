# Novel2ScriptConverter

基于 `FastAPI + Vue 3 + Vite` 的小说改编剧本工作台原型。

## 目录结构

```text
backend/   FastAPI 后端
frontend/  Vue 3 + Vite 前端
开发文档.md
接口文档.md
```

## 后端启动

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

启动后访问：

- Swagger 文档：`http://127.0.0.1:8000/docs`
- OpenAPI：`http://127.0.0.1:8000/openapi.json`

## 前端启动

```bash
cd frontend
npm install
npm run dev
```

启动后访问：

- 前端页面：`http://127.0.0.1:5173`

## 当前已实现

- 项目创建
- 小说文件上传
- 章节自动切分与摘要生成
- 剧本初稿生成
- 场景列表与详情查看
- 场景人工编辑
- 场景 AI 重写占位流程
- 版本记录与导出

## 当前说明

- 当前版本使用本地 `JSON` 文件作为简易持久化存储，文件位于 `backend/data/store.json`
- 异步任务通过 FastAPI `BackgroundTasks` 实现，前端采用轮询获取进度
- 剧本生成与重写目前为规则驱动原型，后续可替换为真实大模型调用
