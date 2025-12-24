# Info-Parser

An AI-powered assistant that converts unstructured business text into
strictly valid, schema-compliant JSON with minimal hallucinations.

---

## Live Demo

A live interactive demo is available here:

https://info-parser.streamlit.app/

The Streamlit app is a thin UI layer built on top of the same core parsing logic
implemented in `solution.py`.

---

## Problem Statement

Business teams often submit material or order requests in free-form text.
The goal of this project is to reliably convert such unstructured input into
clean, structured JSON while:

- Enforcing a fixed schema
- Preventing hallucinated data
- Handling missing or ambiguous information safely
- Always producing valid JSON output

---

## Expected Output Schema

```json
{
  "material_name": "string",
  "quantity": "number | null",
  "unit": "string | null",
  "project_name": "string | null",
  "location": "string | null",
  "urgency": "low | medium | high",
  "deadline": "ISO date (YYYY-MM-DD) | null"
}
