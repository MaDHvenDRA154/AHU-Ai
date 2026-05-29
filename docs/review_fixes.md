# Review Fixes

## Summary
The dashboard was updated to handle the issues called out in the review report:

- Excel uploads now run in the correct Python environment with `openpyxl` available.
- The backend now parses datetime values and cleans bad temperature readings on upload.
- Query handling now supports categorical status queries, threshold queries, date-based queries, and clearer record counts.
- Dataset state is now scoped by session ID instead of relying only on a single global frame.
- The frontend now stores and reuses the active session ID and shows the selected / active file more clearly.

## What Changed

### 1. Query understanding
The backend query engine was expanded so it can handle more of the review cases directly:

- `RUNNING` / `STOP` status queries
- `above`, `below`, `exceed`, `greater than`, `less than`, and `between` filters
- date filters like `April 15th` and `first week`
- `total number of records`
- percentage-style running vs stopped queries

### 2. Data cleanup
On upload, the backend now:

- parses datetime-like columns into real datetimes
- converts temperature columns to numeric values
- masks impossible near-zero temperature readings so they do not distort statistics

### 3. Session safety
Instead of relying on one shared global dataframe only, uploaded datasets are stored by session ID. The frontend now preserves that session ID and sends it back with follow-up queries.

### 4. Frontend state
The upload area now shows:

- the file currently selected
- the file currently loaded as the active dataset

The result cards also render returned row data when the backend includes it.

## Validation
Verified with the real AHU workbook:

- upload succeeds through the frontend proxy
- `How many times was the AHU in RUNNING status?` returns the expected filtered count
- `What is the average supply air temp when the unit is RUNNING?` returns a numeric result
- `When did return air temp exceed 30 degrees?` returns filtered rows
- `What was the return air temperature on April 15th?` returns date-filtered rows
- `What percentage of time was the AHU running vs stopped?` returns a percentage
- `What is the total number of records?` returns the full record count

## AI Layer
The backend now includes an optional LLM-based planner that can interpret a natural-language query into a safe structured operation before execution.

It is enabled when one of these environment variable sets is configured:

- OpenAI-compatible: `OPENAI_API_KEY`, optional `OPENAI_MODEL`, optional `OPENAI_BASE_URL`
- Anthropic-compatible: `ANTHROPIC_API_KEY`, optional `ANTHROPIC_MODEL`, optional `ANTHROPIC_BASE_URL`

If no AI credentials are configured, the app falls back to the deterministic rule-based parser so the project still runs locally without extra setup.
