import streamlit as st
import json
import re
from datetime import datetime
from typing import Optional, Dict, Any
import os

# Import Groq
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    st.error("❌ Groq library not installed. Run: pip install groq")
    st.stop()


class MaterialRequestParser:
    """Streamlit-optimized parser with Groq API support"""
    
    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self.client = Groq(api_key=api_key)
        self.model = model
    
    def create_prompt(self, text: str) -> str:
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        return f"""You are a construction material order parser. Extract information and return ONLY valid JSON.

STRICT RULES:
1. Return ONLY the JSON object, no explanations or markdown
2. All fields must be present in output
3. Use null for missing information (not "unknown", "N/A", or empty string)
4. Do not invent or hallucinate information
5. Material names should be cleaned but recognizable (fix typos, expand abbreviations)
6. Dates must be ISO format (YYYY-MM-DD) or null

SCHEMA:
{{
  "material_name": "string (name of material)",
  "quantity": number (numeric value only),
  "unit": "string (units like kg, bags, units, truckloads, tons)",
  "project_name": "string or null",
  "location": "string or null",
  "urgency": "low or medium or high",
  "deadline": "ISO date (YYYY-MM-DD) or null"
}}

URGENCY LOGIC:
- "high": urgent, ASAP, immediately, today, within 1-3 days
- "medium": within 1 week, soon, within 7-14 days  
- "low": later, no rush, beyond 2 weeks, or no urgency mentioned

DATE PARSING (today is {current_date}):
- "15th March" → "2025-03-15"
- "in 7 days" → calculate from today
- "April end" → "2025-04-30"
- Unclear dates → null

INPUT TEXT:
{text}

OUTPUT (JSON only):"""

    def parse_text(self, text: str) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Parse text and return (result, error)"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a precise JSON generator. Return only valid JSON."},
                    {"role": "user", "content": self.create_prompt(text)}
                ],
                temperature=0.1,
                max_tokens=300
            )
            
            content = response.choices[0].message.content.strip()
            content = self.clean_json_response(content)
            parsed = json.loads(content)
            validated = self.validate_and_fix(parsed)
            
            return validated, None
            
        except json.JSONDecodeError as e:
            return None, f"JSON parsing failed: {str(e)}"
        except Exception as e:
            return None, f"Error: {str(e)}"
    
    def clean_json_response(self, content: str) -> str:
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'^```\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        return content.strip()
    
    def validate_and_fix(self, data: Dict[str, Any]) -> Dict[str, Any]:
        fixed = {}
        
        # Material name
        material = data.get('material_name')
        if material and str(material).strip() and str(material).lower() not in ['null', 'none', 'n/a']:
            fixed['material_name'] = str(material).strip()
        else:
            fixed['material_name'] = None
        
        # Quantity
        qty = data.get('quantity')
        if qty is not None:
            try:
                qty_str = str(qty)
                fixed['quantity'] = float(qty_str) if '.' in qty_str else int(float(qty_str))
            except:
                fixed['quantity'] = None
        else:
            fixed['quantity'] = None
        
        # Unit
        unit = data.get('unit')
        if unit and str(unit).strip() and str(unit).lower() not in ['null', 'none', 'n/a']:
            fixed['unit'] = str(unit).strip()
        else:
            fixed['unit'] = None
        
        # Project name
        proj = data.get('project_name')
        if proj and str(proj).strip() and str(proj).lower() not in ['null', 'none', 'n/a']:
            fixed['project_name'] = str(proj).strip()
        else:
            fixed['project_name'] = None
        
        # Location
        loc = data.get('location')
        if loc and str(loc).strip() and str(loc).lower() not in ['null', 'none', 'n/a']:
            fixed['location'] = str(loc).strip()
        else:
            fixed['location'] = None
        
        # Urgency
        urgency = str(data.get('urgency', 'low')).lower().strip()
        fixed['urgency'] = urgency if urgency in ['low', 'medium', 'high'] else 'low'
        
        # Deadline
        deadline = data.get('deadline')
        fixed['deadline'] = self.validate_date(deadline)
        
        return fixed
    
    def validate_date(self, date_str: Any) -> Optional[str]:
        if not date_str or str(date_str).lower() in ['null', 'none', 'n/a', '']:
            return None
        try:
            date_str = str(date_str).strip()
            parsed = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return parsed.strftime('%Y-%m-%d')
        except:
            return None


def main():
    st.set_page_config(
        page_title="Powerplay Material Parser",
        page_icon="🏗️",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Custom CSS
    st.markdown("""
        <style>
        .big-font {
            font-size: 20px !important;
            font-weight: bold;
        }
        .stMetric {
            background-color: #f0f2f6;
            padding: 10px;
            border-radius: 5px;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.title("🏗️ Construction Material Order Parser")
    st.markdown("**AI-powered conversion of unstructured text to structured JSON**")
    st.markdown("*Powerplay AI Engineering Intern Assignment - Interactive Demo*")
    st.markdown("---")
    
    # Sidebar Configuration
    with st.sidebar:
        st.header(" Configuration")
        
        st.info(" **Powered by Groq API**\n\nFast inference with Llama models")
        
        # Model selection - Groq models only
        model_options = {
            "Llama 3.3 70B Versatile (Best)": "llama-3.3-70b-versatile",
            "Llama 3.3 70B Specdec": "llama-3.3-70b-specdec",
            "Llama 3.1 70B Versatile": "llama-3.1-70b-versatile",
            "Llama 3.1 8B Instant (Fastest)": "llama-3.1-8b-instant",
            "Mixtral 8x7B": "mixtral-8x7b-32768",
            "Gemma 2 9B": "gemma2-9b-it"
        }
        
        selected_model_name = st.selectbox(
            "Select Model:",
            list(model_options.keys()),
            index=0,
            help="Llama 3.3 70B recommended for best quality"
        )
        selected_model = model_options[selected_model_name]
        
        # API Key input
        # Try to get from Streamlit secrets first
        default_key = ""
        try:
            if "GROQ_API_KEY" in st.secrets:
                default_key = st.secrets["GROQ_API_KEY"]
        except:
            pass
        
        if default_key:
            st.success("✅ Using Groq API key from secrets")
            api_key = default_key
        else:
            api_key = st.text_input(
                "Groq API Key:",
                type="password",
                help="Get your free key from console.groq.com"
            )
            
            if not api_key:
                st.warning("⚠️ Please enter your Groq API key")
                st.info(" **Get free API key:**\n\n1. Visit console.groq.com\n2. Sign up\n3. Go to API Keys\n4. Create new key")
        
        st.markdown("---")
        
        # Example inputs
        st.markdown("###  Quick Examples")
        example_texts = [
            "Need 350 bags of Ultratech Cement 50kg for Mumbai-West urgently in 7 days",
            "Order 12 truckloads of river sand for Bangalore Metro Phase 2 by April end",
            "get me 500 bags cement asap for highway project",
            "tmr bars 16mm 500 pieces project phoenix towers urgent delivery in 1 week",
            "Steel bars 25mm 120 units for Project Phoenix, required before 15th March",
            "Get me M-sand 10 truck ASAP for dlf project in gurgaon!!!",
            "need rebar 10mm urgently"
        ]
        
        if st.button("📝 Load Random Example", use_container_width=True):
            import random
            st.session_state.input_text = random.choice(example_texts)
            st.rerun()
        
        st.markdown("---")
        
        # Model info
        st.markdown("### ℹ️ Model Info")
        model_info = {
            "llama-3.3-70b-versatile": "⭐ Best quality\n~0.5s response",
            "llama-3.3-70b-specdec": "Fast with speculative decoding",
            "llama-3.1-70b-versatile": "Previous gen, still excellent",
            "llama-3.1-8b-instant": "⚡ Fastest\n~0.2s response",
            "mixtral-8x7b-32768": "Large context window",
            "gemma2-9b-it": "Google's Gemma model"
        }
        
        st.info(f"**{selected_model_name}**\n\n{model_info.get(selected_model, 'Groq model')}")
        
        st.markdown("---")
        
        # Stats
        st.markdown("### 📈 About")
        st.success("""
        **Features:**
        - 🚀 Groq inference (5x faster)
        - 🎯 Multiple Llama models
        - 📦 Batch processing
        - 💾 JSON export
        - ✅ Free API tier
        """)
    
    # Main Content Area
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("📝 Input")
        
        # Input method tabs
        tab1, tab2 = st.tabs(["Single Text", "Batch Upload"])
        
        with tab1:
            input_text = st.text_area(
                "Enter material order text:",
                value=st.session_state.get('input_text', ''),
                height=250,
                placeholder="Example: Need 350 bags of cement for Mumbai site urgently in 7 days...",
                key="text_input"
            )
            
            col_btn1, col_btn2 = st.columns([3, 1])
            
            with col_btn1:
                parse_button = st.button("🚀 Parse Order", type="primary", use_container_width=True)
            
            with col_btn2:
                if st.button("🗑️ Clear", use_container_width=True):
                    st.session_state.input_text = ""
                    st.session_state.pop('result', None)
                    st.rerun()
            
            if parse_button:
                if not api_key:
                    st.error("⚠️ Please enter Groq API key in sidebar")
                elif not input_text.strip():
                    st.warning("⚠️ Please enter some text to parse")
                else:
                    with st.spinner(f"Processing with {selected_model_name}..."):
                        try:
                            parser = MaterialRequestParser(api_key, selected_model)
                            result, error = parser.parse_text(input_text)
                            
                            if error:
                                st.error(f"❌ {error}")
                            else:
                                st.session_state.result = result
                                st.session_state.input_for_result = input_text
                                st.success("✅ Parsing complete!")
                                
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")
        
        with tab2:
            uploaded_file = st.file_uploader(
                "Upload text file (one order per line):",
                type=['txt'],
                help="Upload a .txt file with one material order per line"
            )
            
            if uploaded_file:
                st.info(f"📄 File: {uploaded_file.name}")
                
            if uploaded_file and st.button("🚀 Parse Batch", type="primary"):
                if not api_key:
                    st.error("⚠️ Please enter Groq API key in sidebar")
                else:
                    try:
                        lines = uploaded_file.read().decode('utf-8').splitlines()
                        lines = [l.strip() for l in lines if l.strip()]
                        
                        st.info(f"📊 Processing {len(lines)} orders with {selected_model_name}...")
                        
                        parser = MaterialRequestParser(api_key, selected_model)
                        results = []
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        for idx, line in enumerate(lines):
                            status_text.text(f"Processing {idx+1}/{len(lines)}: {line[:50]}...")
                            result, error = parser.parse_text(line)
                            
                            results.append({
                                "input": line,
                                "output": result if result else {"error": error}
                            })
                            
                            progress_bar.progress((idx + 1) / len(lines))
                        
                        st.session_state.batch_results = results
                        status_text.empty()
                        progress_bar.empty()
                        st.success(f"✅ Processed {len(lines)} orders!")
                        
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
    
    with col2:
        st.subheader("📤 Output")
        
        # Display single result
        if 'result' in st.session_state:
            result = st.session_state.result
            
            # Material Info Card
            with st.container():
                st.markdown("### 🔧 Material")
                if result['material_name']:
                    st.success(f"**{result['material_name']}**")
                else:
                    st.warning("*Not specified*")
            
            # Quantity & Unit
            col_q1, col_q2 = st.columns(2)
            with col_q1:
                st.markdown("### 📦 Quantity")
                if result['quantity'] is not None:
                    st.metric("Amount", f"{result['quantity']:,}")
                else:
                    st.metric("Amount", "N/A")
            
            with col_q2:
                st.markdown("### 📏 Unit")
                st.metric("Unit", result['unit'] or "N/A")
            
            # Project & Location
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                st.markdown("### 🏗️ Project")
                st.info(result['project_name'] or "*Not specified*")
            
            with col_p2:
                st.markdown("### 📍 Location")
                st.info(result['location'] or "*Not specified*")
            
            # Urgency & Deadline
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                st.markdown("### ⚡ Urgency")
                urgency_colors = {
                    "high": ("🔴", "error"),
                    "medium": ("🟡", "warning"),
                    "low": ("🟢", "success")
                }
                icon, color = urgency_colors.get(result['urgency'], ("⚪", "info"))
                if color == "error":
                    st.error(f"{icon} **{result['urgency'].upper()}**")
                elif color == "warning":
                    st.warning(f"{icon} **{result['urgency'].upper()}**")
                else:
                    st.success(f"{icon} **{result['urgency'].upper()}**")
            
            with col_u2:
                st.markdown("### 📅 Deadline")
                if result['deadline']:
                    st.info(f"**{result['deadline']}**")
                else:
                    st.info("*Not specified*")
            
            st.markdown("---")
            
            # Raw JSON
            with st.expander("📋 View Raw JSON", expanded=False):
                st.json(result)
            
            # Download
            json_str = json.dumps(result, indent=2)
            st.download_button(
                label="⬇️ Download JSON",
                data=json_str,
                file_name="material_order.json",
                mime="application/json",
                use_container_width=True
            )
        
        # Display batch results
        elif 'batch_results' in st.session_state:
            results = st.session_state.batch_results
            
            st.markdown(f"### 📊 Batch Results ({len(results)} orders)")
            
            # Summary statistics
            successful = sum(1 for r in results if 'error' not in r['output'])
            st.metric("Successfully Parsed", f"{successful}/{len(results)}")
            
            # Show results
            with st.expander("📋 View All Results", expanded=True):
                st.json(results)
            
            # Download
            json_str = json.dumps(results, indent=2)
            st.download_button(
                label="⬇️ Download All Results",
                data=json_str,
                file_name="batch_results.json",
                mime="application/json",
                use_container_width=True
            )
            
            # Clear batch
            if st.button("🗑️ Clear Batch Results"):
                st.session_state.pop('batch_results', None)
                st.rerun()
        
        else:
            st.info("👈 Enter text or upload a file to see results here")
            
            # Show example output
            with st.expander("💡 Example Output", expanded=True):
                example_output = {
                    "material_name": "Ultratech Cement 50kg",
                    "quantity": 350,
                    "unit": "bags",
                    "project_name": None,
                    "location": "Mumbai-West",
                    "urgency": "high",
                    "deadline": "2025-12-31"
                }
                st.json(example_output)
    
    # Footer
    st.markdown("---")
    st.markdown("""
        <div style='text-align: center; color: #666; padding: 20px;'>
            <p><b>Built for Powerplay AI Engineering Intern Assignment</b></p>
            <p>🚀 Powered by Groq API | 🦙 Multiple Llama Models | ⚡ Lightning Fast Inference</p>
            <p>Features: Real-time parsing • Batch processing • 6+ model options • JSON export</p>
        </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
