import json
import re
import os
from datetime import datetime
from typing import Optional, Dict, Any, List, Union

try:
    from groq import Groq
except ImportError:
    raise ImportError("Install Groq: pip install groq")


class MaterialRequestParser:
    """
    Auto-detecting LLM-based parser.
    Supports:
    - Single request → JSON object
    - Multiple requests → JSON array
    """

    def __init__(self, api_key: Optional[str] = None,
                 model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not set")

        self.client = Groq(api_key=self.api_key)
        self.model = model

    # ---------------- AUTO-DETECTION ----------------
    def split_requests(self, text: str) -> List[str]:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return lines

    def is_batch_input(self, text: str) -> bool:
        return len(self.split_requests(text)) > 1

    # ---------------- PROMPTS ----------------
    def create_single_prompt(self, text: str) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        return f"""
You are a construction material order parser.

Return ONLY one valid JSON object.
No markdown. No explanation. No extra text.

Schema:
{{
  "material_name": string,
  "quantity": number | null,
  "unit": string | null,
  "project_name": string | null,
  "location": string | null,
  "urgency": "low" | "medium" | "high",
  "deadline": string | null
}}

Rules:
- Use null if missing
- Dates must be YYYY-MM-DD
- Do not hallucinate

Today: {today}

Input:
{text}
"""

    def create_batch_prompt(self, requests: List[str]) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        numbered = "\n".join(f"{i+1}. {r}" for i, r in enumerate(requests))

        return f"""
You are a construction material order parser.

Return a VALID JSON ARRAY.
Each array element corresponds EXACTLY to one input line.
Array length must be {len(requests)}.

No markdown. No explanation. No extra text.

Schema for EACH element:
{{
  "material_name": string,
  "quantity": number | null,
  "unit": string | null,
  "project_name": string | null,
  "location": string | null,
  "urgency": "low" | "medium" | "high",
  "deadline": string | null
}}

Rules:
- Preserve input order
- Use null if missing
- Dates must be YYYY-MM-DD
- Do not hallucinate

Today: {today}

Inputs:
{numbered}
"""

    # ---------------- PUBLIC ENTRY ----------------
    def parse(self, text: str) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        if self.is_batch_input(text):
            return self.parse_batch_text(text)
        return self.parse_single_text(text)

    # ---------------- SINGLE ----------------
    def parse_single_text(self, text: str) -> Dict[str, Any]:
        raw = self.call_llm(self.create_single_prompt(text))
        obj = self.extract_json(raw)
        return self.validate_and_fix(obj)

    # ---------------- BATCH ----------------
    def parse_batch_text(self, text: str) -> List[Dict[str, Any]]:
        requests = self.split_requests(text)
        raw = self.call_llm(self.create_batch_prompt(requests))
        arr = self.extract_json(raw, expect_array=True)

        results = []
        for i, item in enumerate(arr):
            try:
                results.append(self.validate_and_fix(item))
            except Exception:
                results.append(self.create_fallback_response(requests[i]))

        return results

    # ---------------- LLM CALL ----------------
    def call_llm(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Return ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=800
        )
        return response.choices[0].message.content.strip()

    # ---------------- JSON EXTRACTION (BULLETPROOF) ----------------
    def extract_json(self, content: str, expect_array: bool = False):
        content = re.sub(r"```json", "", content, flags=re.IGNORECASE)
        content = re.sub(r"```", "", content).strip()

        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(content)

        if expect_array and not isinstance(obj, list):
            raise ValueError("Expected JSON array but got object")

        if not expect_array and not isinstance(obj, dict):
            raise ValueError("Expected JSON object but got array")

        return obj

    # ---------------- VALIDATION ----------------
    def validate_and_fix(self, data: Dict[str, Any]) -> Dict[str, Any]:
        def clean(v):
            if v in [None, "", "null", "None", "N/A"]:
                return None
            return str(v).strip()

        result = {}

        result["material_name"] = clean(data.get("material_name"))

        try:
            q = data.get("quantity")
            result["quantity"] = int(float(q)) if q is not None else None
        except:
            result["quantity"] = None

        result["unit"] = clean(data.get("unit"))
        result["project_name"] = clean(data.get("project_name"))
        result["location"] = clean(data.get("location"))

        urgency = str(data.get("urgency", "low")).lower()
        result["urgency"] = urgency if urgency in ["low", "medium", "high"] else "low"

        result["deadline"] = self.validate_date(data.get("deadline"))

        return result

    def validate_date(self, value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value)).strftime("%Y-%m-%d")
        except:
            return None

    # ---------------- FALLBACK ----------------
    def create_fallback_response(self, text: str) -> Dict[str, Any]:
        return {
            "material_name": f"Parse failed: {text[:40]}...",
            "quantity": None,
            "unit": None,
            "project_name": None,
            "location": None,
            "urgency": "low",
            "deadline": None
        }


# ---------------- EXAMPLE USAGE ----------------
def main():
    parser = MaterialRequestParser()

    text = """Create 25mm steel bars, 120 units for Project Phoenix, required before 15th March
Need 350 bags of Ultratech Cement 50kg for the site Mumbai-West urgently in 7 days
Order 12 truckloads of river sand for Bangalore Metro Phase 2 by April end
get me 500 bags cement asap for highway project
need rebar 10mm urgently"""

    result = parser.parse(text)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
