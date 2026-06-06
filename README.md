# NovelScriptConverter

`NovelScriptConverter` is a prototype workspace for turning long-form novel text into editable scene-based script drafts.

The stack is:

- `backend/`: FastAPI
- `frontend/`: Vue 3 + Vite

## Current scope

This repository is a working prototype, not a production-ready adaptation engine.

Implemented today:

- Project creation
- Source upload for `txt` and `md`
- Chapter splitting for multi-chapter source text
- Basic summary and character extraction
- Scene-oriented script draft generation
- Scene editing in the workspace
- Instruction-based scene rewrite flow
- Version tracking
- YAML / JSON export
- Backend schema validation for script structure
- Backend automated tests for the main flow

Important constraints:

- Script generation and rewrite are still rule-based prototype logic
- Data is stored in local JSON, not a database
- Tasks run through FastAPI `BackgroundTasks`
- The frontend polls task state instead of using streaming or websockets

## Run backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Backend endpoints:

- Swagger: `http://127.0.0.1:8000/docs`
- OpenAPI: `http://127.0.0.1:8000/openapi.json`

## Run frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend URL:

- `http://127.0.0.1:5173`

## Run tests

```bash
cd backend
pytest -q
```

## Repository notes

- Runtime project data is written under `backend/data/`
- Export files are generated under `backend/data/exports/`
- Uploaded source files are stored under `backend/data/uploads/`

## What is still missing

The following are not done yet:

- Real LLM-based novel understanding and rewrite quality
- Rich plot graph / conflict graph modeling
- Strong fidelity evaluation
- Database persistence
- Authentication and multi-user support
