# AHU AI Dashboard

A full-stack app for querying an Excel dataset using natural language.

## Prerequisites

- Python 3.10+
- Node.js 18+

## Backend Setup

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### Optional AI query planner

To enable the LLM-based query planner, set one of these in your backend environment:

- OpenAI-compatible: `OPENAI_API_KEY`, optional `OPENAI_MODEL`, optional `OPENAI_BASE_URL`
- Anthropic-compatible: `ANTHROPIC_API_KEY`, optional `ANTHROPIC_MODEL`, optional `ANTHROPIC_BASE_URL`

If these are not set, the backend uses the deterministic parser and still supports the reviewed test cases.

For local development, you can place the OpenAI key in either `backend/.env` or the repository root `.env`:

```env
OPENAI_API_KEY=your_key_here
```

## Frontend Setup

```powershell
cd frontend
npm install
npm run dev
```

Open the app at http://localhost:5173 and submit a query.
