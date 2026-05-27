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

## Frontend Setup

```powershell
cd frontend
npm install
npm run dev
```

Open the app at http://localhost:5173 and submit a query.
