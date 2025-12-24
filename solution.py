import json
import re
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

try:
    from groq import Groq
except ImportError:
    raise ImportError("Install Groq: pip install groq")


class MaterialRequestParser:
    """
    Robust LLM-based parser for construction material requests.
    Guaranteed to never throw `Extra data` JSON errors.
    """

    def __init__(self, api_key: Optional[str] = None,
                 model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not set")

        self.client = Groq(api_key=self.api_key)
        self.model = model

    # ---------------- PROMPT ----------------
    def create_prompt(self, text: str) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        return f"""
You are a construction material order parser.

Return ONLY a valid JSON object.
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
- Use null if information is missing
- Dates must be YYYY-MM-DD
- Do not hallucinate

Today is {today}

Input:
{text}
"""

    # ---------------- MAIN PARSER ----------------
    def parse_text(self, text: str, max_retries: int = 3) -> Dict[str, Any]:
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "Return ONLY valid JSON. Do not add text."
                        },
                        {
                            "role": "user",
                            "content": self.create_prompt(text)
                        }
                    ],
                    temperature=0.1,
                    max_tokens=300
                )

                raw_output = response.choices[0].message.content
                parsed_dict = self.extract_json_object(raw_output)

                return self.validate_and_fix(parsed_dict)

            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {e}")

        return self.create_fallback_response(text)

    # ---------------- JSON EXTRACTION (CRITICAL FIX) ----------------
    def extract_json_object(self, content: str) -> Dict[str, Any]:
        """
        Extracts the FIRST valid JSON object and returns a dict.
        This permanently fixes `Extra data` errors.
        """

        # Remove markdown fences if present
        content = re.sub(r"```json", "", content, flags=re.IGNORECASE)
        content = re.sub(r"```", "", content)
        content = content.strip()

        decoder = json.JSONDecoder()

        try:
            obj, _ = decoder.raw_decode(content)
            return obj
        except json.JSONDecodeError:
            pass

        # Regex fallback (last resort)
        match = re.search(r"\{[\s\S]*?\}", content)
        if match:
            return json.loads(match.group(0))

        raise ValueError("No valid JSON found")

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
        except Exception:
            result["quantity"] = None

        result["unit"] = clean(data.get("unit"))
        result["project_name"] = clean(data.get("project_name"))
        result["location"] = clean(data.get("location"))

        urgency = str(data.get("urgency", "low")).lower()
        result["urgency"] = urgency if urgency in ["low", "medium", "high"] else "low"

        result["deadline"] = self.validate_date(data.get("deadline"))

        return result

    def validate_date(self, value: Any) -> Optional[str]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", ""))
            return parsed.strftime("%Y-%m-%d")
        except Exception:
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

    # ---------------- BATCH ----------------
    def process_batch(self, input_file: str, output_file: str) -> List[Dict[str, Any]]:
        results = []

        with open(input_file, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]

        for text in lines:
            result = self.parse_text(text)
            results.append({
                "input": text,
                "output": result
            })

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        return results


# ---------------- ENTRY ----------------
def main():
    print("Material Request Parser (Groq)")
    parser = MaterialRequestParser()
    parser.process_batch("test_inputs.txt", "outputs.json")
    print("Done. Results saved to outputs.json")


if __name__ == "__main__":
    main()
