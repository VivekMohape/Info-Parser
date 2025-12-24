import streamlit as st
import json
import re
from datetime import datetime
from typing import Optional, Dict, Any

# -------------------- GROQ IMPORT --------------------
try:
    from groq import Groq
except ImportError:
    st.error("❌ Groq library not installed. Run: pip install groq")
    st.stop()


# ==================== PARSER CLASS ====================
class MaterialRequestParser:
    """Material order parser using Groq LLM"""

    def __init__(self, api_key: str, model: str):
        self.client = Groq(api_key=api_key)
        self.model = model

    def create_prompt(self, text: str) -> str:
        today = datetime.now().strftime("%Y-%m-%d")

        return f"""
You are a construction material order parser.
Return ONLY valid JSON. No markdown. No explanations.

Rules:
- All fields must exist
- Use null for missing values
- Do not hallucinate
- Dates must be ISO (YYYY-MM-DD)

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

Urgency:
- high: asap, urgent, today, 1-3 days
- medium: within 1-2 weeks
- low: no urgency

Today is {today}

Text:
{text}
"""

    def parse_text(self, text: str):
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Return ONLY valid JSON. No markdown. No commentary."
                    },
                    {
                        "role": "user",
                        "content": self.create_prompt(text)
                    }
                ],
                temperature=0.1,
                max_tokens=300
            )

            content = response.choices[0].message.content.strip()
            content = self.clean_json_response(content)

            parsed = json.loads(content)
            return self.validate_and_fix(parsed), None

        except Exception as e:
            return None, str(e)

    # ---------------- JSON CLEANER ----------------
    def clean_json_response(self, content: str) -> str:
        # Remove markdown fences
        content = re.sub(r"^```json\s*", "", content)
        content = re.sub(r"^```\s*", "", content)
        content = re.sub(r"\s*```$", "", content)

        content = content.strip()

        # Remove trailing commas
        content = re.sub(r",\s*([}\]])", r"\1", content)

        # Extract JSON object
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            content = match.group(0)

        # Fix quotes
        if content.count('"') % 2 != 0:
            content += '"'

        # Fix braces
        open_braces = content.count("{")
        close_braces = content.count("}")
        if open_braces > close_braces:
            content += "}" * (open_braces - close_braces)

        return content

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


# ==================== STREAMLIT UI ====================
def main():
    st.set_page_config(
        page_title="Material Order Parser",
        page_icon="🏗️",
        layout="wide"
    )

    st.title("🏗️ Construction Material Order Parser")
    st.markdown("AI-powered conversion of unstructured text to structured JSON")
    st.markdown("---")

    # ---------------- SIDEBAR ----------------
    with st.sidebar:
        st.header("⚙️ Configuration")

        models = {
            "Llama 3.3 70B (Best)": "llama-3.3-70b-versatile",
            "Llama 3.1 8B (Fast)": "llama-3.1-8b-instant",
            "Mixtral 8x7B": "mixtral-8x7b-32768",
            "Gemma 2 9B": "gemma2-9b-it"
        }

        model_name = st.selectbox("Model", list(models.keys()))
        model = models[model_name]

        api_key = st.text_input("Groq API Key", type="password")

        st.markdown("---")
        st.markdown("### 📌 Example")
        if st.button("Load Example"):
            st.session_state.text = "Need 350 bags of Ultratech cement for Mumbai site urgently in 7 days"

    # ---------------- MAIN ----------------
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📝 Input")
        text = st.text_area(
            "Enter material request",
            value=st.session_state.get("text", ""),
            height=220
        )

        if st.button("🚀 Parse"):
            if not api_key:
                st.error("Please enter Groq API key")
            elif not text.strip():
                st.warning("Enter some text")
            else:
                with st.spinner("Parsing..."):
                    parser = MaterialRequestParser(api_key, model)
                    result, error = parser.parse_text(text)

                    if error:
                        st.error(error)
                    else:
                        st.session_state.result = result
                        st.success("Parsed successfully")

    with col2:
        st.subheader("📤 Output")

        if "result" in st.session_state:
            st.json(st.session_state.result)

            st.download_button(
                "⬇️ Download JSON",
                json.dumps(st.session_state.result, indent=2),
                "material_order.json",
                "application/json"
            )
        else:
            st.info("Parsed output will appear here")


# ==================== ENTRY ====================
if __name__ == "__main__":
    main()
