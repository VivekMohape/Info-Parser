import json
import re
from datetime import datetime
from typing import Optional, Dict, Any, List
import os

try:
    from groq import Groq
except ImportError:
    print("ERROR: Groq library not installed")
    print("Install with: pip install groq")
    exit(1)


class MaterialRequestParser:
    """
    LLM-based parser for converting unstructured construction material
    requests into structured JSON format using Groq API.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "llama-3.3-70b-versatile"):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("Groq API key not found")

        self.client = Groq(api_key=self.api_key)
        self.model = model

    # ---------------- PROMPT ----------------
    def create_prompt(self, text: str) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        return f"""
You are a construction material order parser.
Return ONLY valid JSON. No markdown. No extra text.

Schema:
{{
  "material_name": string,
  "quantity": number,
  "unit": string,
  "project_name": string | null,
  "location": string | null,
  "urgency": "low" | "medium" | "high",
  "deadline": string | null
}}

Rules:
- Use null for missing values
- Dates must be YYYY-MM-DD
- Do not hallucinate

Today: {today}

Text:
{text}
"""

    # ---------------- PARSER ----------------
    def parse_text(self, text: str, max_retries: int = 3) -> Dict[str, Any]:
        last_error = None

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "Return ONLY valid JSON. No markdown. No explanations."
                        },
                        {
                            "role": "user",
                            "content": self.create_prompt(text)
                        }
                    ],
                    temperature=0.1,
                    max_tokens=300
                )

                raw = response.choices[0].message.content.strip()
                json_str = self.clean_json_response(raw)

                parsed = json.loads(json_str)
                return self.validate_and_fix(parsed)

            except Exception as e:
                last_error = str(e)
                print(f"Attempt {attempt + 1} failed: {e}")

        print("All attempts failed")
        return self.create_fallback_response(text)

    # ---------------- JSON CLEANER (FIXED) ----------------
    def clean_json_response(self, content: str) -> str:
        """
        Safely extract the FIRST valid JSON object from LLM output.
        Fixes 'Extra data' JSON errors.
        """

        # Remove markdown fences
        content = re.sub(r"```json", "", content, flags=re.IGNORECASE)
        content = re.sub(r"```", "", content)
        content = content.strip()

        # ✅ Proper JSON extraction
        decoder = json.JSONDecoder()
        try:
            obj, _ = decoder.raw_decode(content)
            return json.dumps(obj)
        except json.JSONDecodeError:
            pass

        # Fallback regex extraction
        match = re.search(r"\{[\s\S]*?\}", content)
        if match:
            return match.group(0)

        raise ValueError("No valid JSON found in response")

    # ---------------- VALIDATION ----------------
    def validate_and_fix(self, data: Dict[str, Any]) -> Dict[str, Any]:
        def clean(val):
            if val in [None, "", "null", "None", "N/A"]:
                return None
            return str(val).strip()

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

    def validate_date(self, value) -> Optional[str]:
        if not value:
            return None
        try:
            d = datetime.fromisoformat(str(value).replace("Z", ""))
            return d.strftime("%Y-%m-%d")
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

    # ---------------- BATCH ----------------
    def process_batch(self, input_file: str, output_file: str) -> List[Dict[str, Any]]:
        results = []

        with open(input_file, "r", encoding="utf-8") as f:
            inputs = [l.strip() for l in f if l.strip()]

        for text in inputs:
            result = self.parse_text(text)
            results.append({"input": text, "output": result})

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        return results


def main():
    parser = MaterialRequestParser(model="llama-3.3-70b-versatile")
    parser.process_batch("test_inputs.txt", "outputs.json")


if __name__ == "__main__":
    main()
