
from datetime import datetime
import json
import urllib.error
import urllib.request
import urllib.parse
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, UploadFile, File, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
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
datasets = {}
active_session_id = None

MONTH_MAP = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

STAT_KEYWORDS = {
    "mean": ["average", "avg", "mean"],
    "median": ["median"],
    "max": ["maximum", "max", "highest", "largest"],
    "min": ["minimum", "min", "lowest", "smallest"],
    "std": ["standard deviation", "std dev", "stdev", "standard dev", "std"],
    "count": ["count", "total number of records", "number of records", "how many records"],
}

STATUS_ALIASES = {
    "running": ["running", "run", "running status"],
    "stopped": ["stopped", "stop", "stopping", "stopped status"],
}

AI_PROVIDER = os.getenv("AI_PROVIDER", "").strip().lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest").strip()
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").strip().rstrip("/")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").strip().rstrip("/")


def load_local_env_file():
    env_paths = [
        os.path.join(os.path.dirname(__file__), ".env"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
    ]

    for env_path in env_paths:
        if not os.path.exists(env_path):
            continue

        try:
            with open(env_path, "r", encoding="utf-8") as env_file:
                for raw_line in env_file:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue

                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    os.environ.setdefault(key, value)
        except Exception:
            pass


load_local_env_file()

AI_PROVIDER = os.getenv("AI_PROVIDER", "").strip().lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest").strip()
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").strip().rstrip("/")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip()
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta").strip().rstrip("/")

if not AI_PROVIDER and OPENAI_API_KEY:
    AI_PROVIDER = "openai"
elif not AI_PROVIDER and GEMINI_API_KEY:
    AI_PROVIDER = "gemini"

class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None


class AIPlan(BaseModel):
    action: str
    column: Optional[str] = None
    value: Optional[str] = None
    value2: Optional[str] = None
    operator: Optional[str] = None
    statistic: Optional[str] = None
    date_text: Optional[str] = None
    status_value: Optional[str] = None
    limit: Optional[int] = None
    rationale: Optional[str] = None


def normalize_text(value):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value).lower())).strip()


def frame_summary(frame):
    columns = []
    for column in frame.columns:
        series = frame[column]
        dtype = "datetime" if pd.api.types.is_datetime64_any_dtype(series) else "numeric" if pd.api.types.is_numeric_dtype(series) else "text"
        sample_values = [str(value) for value in series.dropna().astype(str).head(3).tolist()]
        columns.append({
            "name": str(column),
            "dtype": dtype,
            "samples": sample_values,
        })

    return {
        "row_count": int(len(frame)),
        "columns": columns,
    }


def ai_enabled():
    return bool(OPENAI_API_KEY or ANTHROPIC_API_KEY or GEMINI_API_KEY)


def post_json(url, headers, payload, timeout=25):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AI request failed ({exc.code}): {body}") from exc


def is_retryable_ai_error(error_message):
    return any(code in error_message for code in ["503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED"])


def normalize_gemini_model_name(model_name):
    name = (model_name or "").strip()
    return name.removeprefix("models/")


def parse_ai_json(text):
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end >= start:
        cleaned = cleaned[start : end + 1]

    return json.loads(cleaned)


def build_ai_prompt(query, frame):
    schema = frame_summary(frame)
    schema_text = json.dumps(schema, ensure_ascii=False)
    return f"""You are a data query planner for a pandas dataframe.
Return only valid JSON with one of these actions: stat, filter, categorical_count, percentage, latest, date_filter, row_count, explain.
Use only exact column names from the schema.
Choose the smallest safe action that answers the query.
Do not write pandas code. Do not include markdown.

Query: {query}
Schema: {schema_text}

JSON shape examples:
{{"action": "stat", "column": "Supply Air Temp.", "statistic": "mean"}}
{{"action": "filter", "column": "Return Air Temperature", "value": "30", "operator": ">"}}
{{"action": "categorical_count", "column": "Run Status.", "value": "running"}}
{{"action": "date_filter", "column": "DateTime", "date_text": "April 15"}}
{{"action": "percentage", "column": "Run Status.", "value": "running"}}
{{"action": "row_count"}}
{{"action": "explain", "rationale": "why the query cannot be answered safely"}}
"""

def resolve_exact_column(frame, column_name):
    if not column_name:
        return None

    normalized_target = normalize_text(column_name)

    for column in frame.columns:
        if normalize_text(column) == normalized_target:
            return column

    return None


def find_query_column(query, frame, prefer_numeric=True):
    normalized_query = normalize_text(query)
    candidates = []

    for column in frame.columns:
        normalized_column = normalize_text(column)
        if not normalized_column or normalized_column not in normalized_query:
            continue

        is_numeric = pd.api.types.is_numeric_dtype(frame[column]) or pd.to_numeric(frame[column], errors="coerce").notna().any()
        score = len(normalized_column.split())
        if prefer_numeric and is_numeric:
            score += 10

        candidates.append((score, column))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][1]

def call_openai_ai(query, frame):
    prompt = build_ai_prompt(query, frame)
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }

    response = post_json(
        f"{OPENAI_BASE_URL}/chat/completions",
        {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        payload,
    )

    content = response["choices"][0]["message"]["content"]
    return AIPlan.model_validate(parse_ai_json(content))


def call_anthropic_ai(query, frame):
    prompt = build_ai_prompt(query, frame)
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 700,
        "temperature": 0,
        "messages": [
            {"role": "user", "content": prompt},
        ],
    }

    response = post_json(
        f"{ANTHROPIC_BASE_URL}/v1/messages",
        {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        payload,
    )

    text_blocks = [part.get("text", "") for part in response.get("content", []) if part.get("type") == "text"]
    content = "\n".join(text_blocks)
    return AIPlan.model_validate(parse_ai_json(content))


def call_gemini_ai(query, frame):
    prompt = build_ai_prompt(query, frame)
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": "Return JSON only."},
                    {"text": prompt},
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0,
        },
    }

    model_candidates = [
        normalize_gemini_model_name(GEMINI_MODEL),
        "gemini-2.0-flash-lite-001",
        "gemini-flash-lite-latest",
        "gemini-2.0-flash",
    ]
    seen_models = set()
    last_error = None

    for model_name in model_candidates:
        if not model_name or model_name in seen_models:
            continue
        seen_models.add(model_name)

        try:
            response = post_json(
                f"{GEMINI_BASE_URL}/models/{urllib.parse.quote(model_name, safe='')}:generateContent?key={GEMINI_API_KEY}",
                {
                    "Content-Type": "application/json",
                },
                payload,
            )

            candidates = response.get("candidates", [])
            if not candidates:
                raise RuntimeError("Gemini returned no candidates")

            parts = candidates[0].get("content", {}).get("parts", [])
            content = "\n".join(part.get("text", "") for part in parts if part.get("text"))
            if not content:
                raise RuntimeError("Gemini returned empty content")

            return AIPlan.model_validate(parse_ai_json(content))
        except RuntimeError as exc:
            last_error = str(exc)
            if not is_retryable_ai_error(last_error):
                raise

    if last_error:
        raise RuntimeError(last_error)

    raise RuntimeError("Gemini request failed")


def generate_ai_plan(query, frame):
    if not ai_enabled():
        return None

    if AI_PROVIDER == "gemini" or (GEMINI_API_KEY and not OPENAI_API_KEY and not ANTHROPIC_API_KEY):
        return call_gemini_ai(query, frame)

    if AI_PROVIDER == "anthropic" or (ANTHROPIC_API_KEY and not OPENAI_API_KEY):
        return call_anthropic_ai(query, frame)

    if OPENAI_API_KEY:
        return call_openai_ai(query, frame)

    return None


def generate_ai_plan_or_error(query, frame):
    plan = generate_ai_plan(query, frame)
    if plan is None:
        raise RuntimeError("LLM planning is not configured. Add GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY to .env.")

    return plan


def resolve_ai_plan(plan, query, frame):
    action = (plan.action or "").strip().lower()
    column = resolve_exact_column(frame, plan.column)
    target_frame = frame

    if plan.column and column is None and action not in {"row_count", "explain"}:
        return {
            "query": query,
            "answer": f"The model selected an unknown column: {plan.column}",
        }

    if action in {"row_count", "count_rows"}:
        return {
            "query": query,
            "answer": f"Total records: {len(target_frame)}",
        }

    if action == "date_filter" and plan.date_text:
        filtered, label = apply_date_filter(target_frame, plan.date_text)
        extreme_answer = resolve_extreme_timestamp_answer(query, target_frame)
        if extreme_answer is not None:
            return extreme_answer

        if column and column in filtered.columns:
            return {
                "query": query,
                "answer": f"Found {len(filtered)} readings for {column} on {label or plan.date_text}",
                "data": filtered.head(10).fillna("").to_dict(orient="records"),
            }

        return {
            "query": query,
            "answer": f"Found {len(filtered)} rows on {label or plan.date_text}",
            "data": filtered.head(10).fillna("").to_dict(orient="records"),
        }

    if action == "categorical_count" and column and column in target_frame.columns:
        normalized_value = (plan.value or plan.status_value or "").strip().lower()
        if normalized_value:
            filtered = target_frame[target_frame[column].astype(str).str.lower().str.contains(normalized_value, na=False)]
            return {
                "query": query,
                "answer": f"Found {len(filtered)} rows where {column} contains {normalized_value}",
                "data": filtered.head(10).fillna("").to_dict(orient="records"),
            }

        counts = target_frame[column].astype(str).value_counts()
        return {
            "query": query,
            "answer": f"Top values in {column}: {counts.head(5).to_dict()}",
        }

    if action == "percentage" and column and column in target_frame.columns:
        normalized_value = (plan.value or plan.status_value or "").strip().lower()
        if normalized_value:
            total = len(target_frame)
            filtered = target_frame[target_frame[column].astype(str).str.lower().str.contains(normalized_value, na=False)]
            percentage = round((len(filtered) / total) * 100, 2) if total else 0
            return {
                "query": query,
                "answer": f"{normalized_value.title()} rows represent {percentage}% of the dataset",
            }

    if action == "latest" and column and column in target_frame.columns:
        return {
            "query": query,
            "answer": f"Latest value in {column} is {target_frame[column].iloc[-1]}",
        }

    if action == "stat" and column and column in target_frame.columns:
        statistic = (plan.statistic or "").strip().lower()
        numeric_series = pd.to_numeric(target_frame[column], errors="coerce").dropna()
        if not numeric_series.empty:
            normalized_stat = {
                "average": "mean",
                "avg": "mean",
                "mean": "mean",
                "median": "median",
                "maximum": "max",
                "max": "max",
                "minimum": "min",
                "min": "min",
                "std": "std",
                "standard deviation": "std",
            }.get(statistic, statistic)
            if normalized_stat in {"mean", "median", "max", "min", "std"}:
                return {
                    "query": query,
                    "answer": build_stat_answer(normalized_stat, column, numeric_series),
                }

    if action == "filter" and column and column in target_frame.columns:
        threshold_value = plan.value or plan.value2
        if threshold_value is not None:
            numeric_series = pd.to_numeric(target_frame[column], errors="coerce")
            try:
                number = float(threshold_value)
            except ValueError:
                number = None

            if number is not None:
                operator = (plan.operator or "").strip().lower()
                if operator in {">", "gt", "above", "exceed", "greater", "greater than", "more than", "over"}:
                    filtered = target_frame[numeric_series > number]
                elif operator in {"<", "lt", "below", "less", "less than", "under"}:
                    filtered = target_frame[numeric_series < number]
                else:
                    filtered = target_frame[numeric_series == number]

                return {
                    "query": query,
                    "answer": f"Found {len(filtered)} rows where {column} matches the requested filter",
                    "data": filtered.head(10).fillna("").to_dict(orient="records"),
                }

    if action == "explain" and plan.rationale:
        return {
            "query": query,
            "answer": plan.rationale,
        }

    return None


def get_session_frame(session_id=None):
    if session_id and session_id in datasets:
        return datasets[session_id]["df"]

    if active_session_id and active_session_id in datasets:
        return datasets[active_session_id]["df"]

    return df


def store_dataset(frame, path, filename):
    global df, current_dataset, active_session_id

    session_id = str(uuid4())
    datasets[session_id] = {
        "df": frame,
        "path": path,
        "filename": filename,
    }
    df = frame
    current_dataset = path
    active_session_id = session_id
    return session_id


def parse_datetime_columns(frame):
    loaded = frame.copy()

    for column in loaded.columns:
        column_name = str(column).lower()

        if any(token in column_name for token in ["datetime", "date", "timestamp", "time"]):
            loaded[column] = pd.to_datetime(loaded[column], errors="coerce")

    return loaded


def clean_sensor_columns(frame):
    loaded = frame.copy()

    for column in loaded.columns:
        column_name = str(column).lower()

        if ("temp" in column_name or "temperature" in column_name) and "set point" not in column_name:
            numeric_series = pd.to_numeric(loaded[column], errors="coerce")
            loaded[column] = numeric_series.mask(numeric_series < 1)

    return loaded

def load_dataset(path):
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

    if loaded.empty:
        raise ValueError("Uploaded file contains no data rows")

    loaded = parse_datetime_columns(loaded)
    loaded = clean_sensor_columns(loaded)

    return loaded


def get_numeric_columns(frame):
    cols = []

    for col in frame.columns:
        try:
            numeric_series = pd.to_numeric(frame[col], errors="coerce").dropna()
            if len(numeric_series) > 0:
                cols.append(col)
        except Exception:
            pass

    return cols


def get_datetime_column(frame):
    for col in frame.columns:
        column_name = str(col).lower()
        if any(token in column_name for token in ["datetime", "date", "timestamp"]):
            return col

    for col in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[col]):
            return col

    return None


def detect_statistic(query):
    lowered = query.lower()

    for stat_name, keywords in STAT_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return stat_name

    return None


def extract_status_value(query):
    lowered = query.lower()

    for canonical, aliases in STATUS_ALIASES.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", lowered) for alias in aliases):
            return canonical

    return None


def find_status_column(frame):
    status_columns = [col for col in frame.columns if any(token in str(col).lower() for token in ["status", "state"])]

    if status_columns:
        return status_columns[0]

    text_columns = [col for col in frame.columns if col not in get_numeric_columns(frame)]

    if text_columns:
        return text_columns[0]

    return None


def apply_date_filter(frame, query):
    date_column = get_datetime_column(frame)

    if not date_column:
        return frame, None

    dt_series = pd.to_datetime(frame[date_column], errors="coerce")
    lowered = query.lower()

    if "first week" in lowered:
        non_null = dt_series.dropna()
        if non_null.empty:
            return frame, None

        start = non_null.min().normalize()
        end = start + pd.Timedelta(days=7)
        filtered = frame[(dt_series >= start) & (dt_series < end)]
        return filtered, f"the first week starting {start.date()}"

    month_match = re.search(r"\b(" + "|".join(MONTH_MAP.keys()) + r")\b", lowered)
    if not month_match:
        return frame, None

    month_name = month_match.group(1)
    month_number = MONTH_MAP[month_name]
    filtered = frame[dt_series.dt.month == month_number]
    label = month_name.title()

    year_match = re.search(r"\b(20\d{2})\b", lowered)
    if year_match:
        year = int(year_match.group(1))
        filtered = filtered[dt_series.loc[filtered.index].dt.year == year]
        label = f"{label} {year}"

    day_match = re.search(rf"\b{month_name}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", lowered)
    if day_match:
        day = int(day_match.group(1))
        filtered = filtered[dt_series.loc[filtered.index].dt.day == day]
        label = f"{label} {day}"

    return filtered, label


def apply_threshold_filter(frame, query, column):
    lowered = query.lower()
    numbers = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", lowered)]

    if "between" in lowered and len(numbers) >= 2:
        low, high = sorted(numbers[:2])
        filtered = frame[
            pd.to_numeric(frame[column], errors="coerce").between(low, high, inclusive="both")
        ]
        return filtered, f"between {low} and {high}"

    if not numbers:
        return None, None

    threshold = numbers[0]

    if any(keyword in lowered for keyword in ["below", "less than", "under"]):
        filtered = frame[pd.to_numeric(frame[column], errors="coerce") < threshold]
        return filtered, f"below {threshold}"

    if any(keyword in lowered for keyword in ["above", "exceed", "greater than", "more than", "over"]):
        filtered = frame[pd.to_numeric(frame[column], errors="coerce") > threshold]
        return filtered, f"above {threshold}"

    return None, None


def build_stat_answer(statistic, column, series):
    if statistic == "mean":
        return f"Average value in {column} is {round(series.mean(), 2)}"
    if statistic == "median":
        return f"Median of {column} is {round(series.median(), 2)}"
    if statistic == "max":
        return f"Maximum value in {column} is {series.max()}"
    if statistic == "min":
        return f"Minimum value in {column} is {series.min()}"
    if statistic == "std":
        return f"Standard deviation of {column} is {round(series.std(), 2)}"
    if statistic == "count":
        return f"Count of {column} is {series.count()}"

    return f"Matched column: {column}"


def resolve_extreme_timestamp_answer(query, frame):
    lowered_query = query.lower()
    if not any(keyword in lowered_query for keyword in ["timestamp", "time", "when"]):
        return None

    if not any(keyword in lowered_query for keyword in ["maximum", "highest", "largest", "minimum", "lowest", "smallest"]):
        return None

    filtered, label = apply_date_filter(frame, query)
    working_frame = filtered if not filtered.empty else frame

    value_column = find_query_column(query, working_frame)
    if not value_column:
        numeric_columns = get_numeric_columns(working_frame)
        if not numeric_columns:
            return None
        value_column = numeric_columns[0]

    numeric_series = pd.to_numeric(working_frame[value_column], errors="coerce")
    valid_rows = working_frame[numeric_series.notna()]
    if valid_rows.empty:
        return None

    is_max = any(keyword in lowered_query for keyword in ["maximum", "highest", "largest"])
    idx = numeric_series.idxmax() if is_max else numeric_series.idxmin()
    value = numeric_series.loc[idx]
    timestamp_column = get_datetime_column(working_frame)
    timestamp_text = ""

    if timestamp_column and timestamp_column in working_frame.columns:
        timestamp_value = working_frame.loc[idx, timestamp_column]
        if pd.notna(timestamp_value):
            timestamp_text = f" at {timestamp_value}"

    label_text = label or "the requested period"
    prefix = "Maximum" if is_max else "Minimum"

    return {
        "query": query,
        "answer": f"{prefix} value in {value_column} on {label_text} was {value}{timestamp_text}",
        "data": [valid_rows.loc[idx].fillna("").to_dict()],
    }

def process_single_query(query, frame=None):
    working_frame = frame if frame is not None else df

    if working_frame.empty:
        return {"query": query, "answer": "Please upload a dataset first"}

    try:
        ai_plan = generate_ai_plan_or_error(query, working_frame)
    except Exception as exc:
        fallback_answer = resolve_extreme_timestamp_answer(query, working_frame)
        if fallback_answer is not None:
            return fallback_answer
        return {
            "query": query,
            "answer": str(exc),
        }

    ai_result = resolve_ai_plan(ai_plan, query, working_frame)
    if ai_result is not None:
        ai_result.setdefault("query", query)
        if (ai_plan.action or "").strip().lower() == "explain":
            fallback_answer = resolve_extreme_timestamp_answer(query, working_frame)
            if fallback_answer is not None:
                return fallback_answer
        return ai_result

    fallback_answer = resolve_extreme_timestamp_answer(query, working_frame)
    if fallback_answer is not None:
        return fallback_answer

    return {
        "query": query,
        "answer": "The LLM plan could not be resolved.",
    }

@app.get("/")
def root():
    return {
        "message": "AHU AI Backend Running",
        "dataset": current_dataset,
        "session_id": active_session_id,
    }

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    try:
        upload_name = file.filename or "uploaded_file"
        filepath = os.path.join(UPLOAD_DIR, upload_name)

        with open(filepath, "wb") as f:
            f.write(await file.read())

        loaded = load_dataset(filepath)
        session_id = store_dataset(loaded, filepath, upload_name)

        return {
            "message": "Dataset uploaded successfully",
            "rows": len(loaded),
            "columns": list(loaded.columns),
            "session_id": session_id,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.post("/query")
def query_data(request: QueryRequest, x_session_id: Optional[str] = Header(default=None)):
    frame = get_session_frame(request.session_id or x_session_id)

    if frame.empty:
        return {
            "answers": [
                {
                    "answer": "Please upload a dataset first"
                }
            ]
        }

    raw_query = request.query

    split_queries = [raw_query]
    if "\n" in raw_query or "|" in raw_query or ";" in raw_query:
        split_queries = [part.strip() for part in re.split(r"\n|\||;", raw_query) if part.strip()]

    results = []

    for q in split_queries:
        q = q.strip()

        if q:
            results.append(process_single_query(q, frame))

    return {
        "answers": results
    }

@app.get("/columns")
def columns(x_session_id: Optional[str] = Header(default=None)):
    frame = get_session_frame(x_session_id)

    return {
        "columns": list(frame.columns)
    }

@app.get("/preview")
def preview(x_session_id: Optional[str] = Header(default=None)):
    frame = get_session_frame(x_session_id)

    return {
        "rows": frame.head(5).fillna("").to_dict(orient="records")
    }
