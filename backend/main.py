
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
from rapidfuzz import process
import re
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploaded_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)

current_dataset = None
df = pd.DataFrame()

class QueryRequest(BaseModel):
    query: str

def load_dataset(path):
    global df, current_dataset

    if path.endswith(".csv"):
        loaded = pd.read_csv(path)
    else:
        raw = pd.read_excel(path, header=None)

        header_row = 0
        for i in range(min(10, len(raw))):
            row_vals = [str(val).lower() for val in raw.iloc[i].tolist()]
            if any("datetime" in val for val in row_vals):
                header_row = i
                break

        loaded = pd.read_excel(path, header=header_row)

    loaded.columns = [str(col).strip() for col in loaded.columns]
    loaded = loaded.loc[:, loaded.notna().any()]

    df = loaded
    current_dataset = path

def get_numeric_columns():
    cols = []

    for col in df.columns:
        try:
            numeric_series = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(numeric_series) > 0:
                cols.append(col)
        except:
            pass

    return cols

def find_best_column(query):
    numeric_cols = get_numeric_columns()

    if numeric_cols:
        match = process.extractOne(query, numeric_cols)

        if match:
            return match[0]

    match = process.extractOne(query, list(df.columns))

    if match:
        return match[0]

    return None

def process_single_query(query):
    query = query.lower().strip()

    column = find_best_column(query)

    if not column:
        return {"query": query, "answer": "No matching column found"}

    try:
        numeric_series = pd.to_numeric(df[column], errors="coerce").dropna()

        if len(numeric_series) == 0:
            return {"query": query, "answer": f"{column} is not numeric"}

        if "maximum" in query or "max" in query:
            return {
                "query": query,
                "answer": f"Maximum value in {column} is {numeric_series.max()}"
            }

        elif "minimum" in query or "min" in query:
            return {
                "query": query,
                "answer": f"Minimum value in {column} is {numeric_series.min()}"
            }

        elif "average" in query or "avg" in query or "mean" in query:
            return {
                "query": query,
                "answer": f"Average value in {column} is {round(numeric_series.mean(), 2)}"
            }

        elif "median" in query:
            return {
                "query": query,
                "answer": f"Median of {column} is {round(numeric_series.median(), 2)}"
            }

        elif "mode" in query:
            mode_value = numeric_series.mode()

            if len(mode_value) > 0:
                mode_value = mode_value.iloc[0]

            return {
                "query": query,
                "answer": f"Mode of {column} is {mode_value}"
            }

        elif (
            "standard deviation" in query
            or "std" in query
            or "std dev" in query
            or "stdev" in query
            or "standard dev" in query
        ):
            return {
                "query": query,
                "answer": f"Standard deviation of {column} is {round(numeric_series.std(), 2)}"
            }

        elif "count" in query:
            return {
                "query": query,
                "answer": f"Count of {column} is {numeric_series.count()}"
            }

        elif "latest" in query:
            return {
                "query": query,
                "answer": f"Latest value in {column} is {df[column].iloc[-1]}"
            }

        elif "above" in query:
            nums = re.findall(r'\d+', query)

            if nums:
                threshold = float(nums[0])

                filtered = df[pd.to_numeric(df[column], errors="coerce") > threshold]

                return {
                    "query": query,
                    "answer": f"Found {len(filtered)} rows where {column} > {threshold}",
                    "data": filtered.head(10).fillna("").to_dict(orient="records")
                }

        return {
            "query": query,
            "answer": f"Matched column: {column}"
        }

    except Exception as e:
        return {
            "query": query,
            "answer": f"Error: {str(e)}"
        }

@app.get("/")
def root():
    return {
        "message": "AHU AI Backend Running",
        "dataset": current_dataset
    }

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    global df

    try:
        filepath = os.path.join(UPLOAD_DIR, file.filename)

        with open(filepath, "wb") as f:
            f.write(await file.read())

        load_dataset(filepath)

        return {
            "message": "Dataset uploaded successfully",
            "rows": len(df),
            "columns": list(df.columns)
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/query")
def query_data(request: QueryRequest):

    if df.empty:
        return {
            "answers": [
                {
                    "answer": "Please upload a dataset first"
                }
            ]
        }

    raw_query = request.query

    split_queries = re.split(r',|\n|\|', raw_query)

    results = []

    for q in split_queries:
        q = q.strip()

        if q:
            results.append(process_single_query(q))

    return {
        "answers": results
    }

@app.get("/columns")
def columns():
    return {
        "columns": list(df.columns)
    }

@app.get("/preview")
def preview():
    return {
        "rows": df.head(5).fillna("").to_dict(orient="records")
    }
