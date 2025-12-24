import json
import re
from datetime import datetime, timedelta
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
    
    Features:
    - Structured output with strict schema compliance
    - Hallucination control through validation
    - Retry mechanism for robustness
    - Graceful error handling
    - Uses Groq's fast Llama models
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "llama-3.3-70b-versatile"):
        """
        Initialize parser with Groq API key.
        
        Args:
            api_key: Groq API key (if None, reads from GROQ_API_KEY env var)
            model: Groq model to use (default: llama-3.3-70b-versatile)
        """
        self.api_key = api_key or os.getenv('GROQ_API_KEY')
        if not self.api_key:
            raise ValueError(
                "Groq API key required. Set GROQ_API_KEY environment variable "
                "or pass api_key parameter. Get free key at: https://console.groq.com"
            )
        self.client = Groq(api_key=self.api_key)
        self.model = model
        
        # Define expected schema
        self.schema = {
            "material_name": "string",
            "quantity": "number",
            "unit": "string",
            "project_name": "string | null",
            "location": "string | null",
            "urgency": "low | medium | high",
            "deadline": "ISO date string | null"
        }
    
    def create_prompt(self, text: str) -> str:
        """
        Create a carefully structured prompt that enforces schema compliance
        and handles edge cases.
        
        Design principles:
        1. Explicit schema definition
        2. Clear null-handling rules
        3. Semantic grounding for inference (urgency, dates)
        4. Anti-hallucination instructions
        """
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        return f"""You are a construction material order parser. Extract information from the text and return ONLY valid JSON.

STRICT RULES:
1. Return ONLY the JSON object, no explanations, no markdown formatting
2. All fields must be present in output
3. Use null for missing information (never use "unknown", "N/A", or empty strings)
4. Do not invent or hallucinate information not present in the input
5. Material names should be cleaned and standardized (fix typos, expand abbreviations)
6. Dates must be in ISO format (YYYY-MM-DD) or null
7. Quantity must be a number (not a string)

SCHEMA:
{{
  "material_name": "string (name of construction material)",
  "quantity": number (numeric value only, null if not specified),
  "unit": "string (units like kg, bags, units, truckloads, tons, pieces)",
  "project_name": "string or null",
  "location": "string or null",
  "urgency": "low or medium or high",
  "deadline": "ISO date (YYYY-MM-DD) or null"
}}

URGENCY INFERENCE LOGIC:
- "high": Contains words like urgent, ASAP, immediately, today, critical, or deadline within 1-3 days
- "medium": Contains words like soon, within a week, or deadline within 7-14 days
- "low": No urgency mentioned, or deadline beyond 2 weeks, or words like later, no rush

DATE PARSING RULES (today is {current_date}):
- Specific dates like "15th March" → "2025-03-15" (assume 2025 if year not specified)
- Relative dates like "in 7 days" → calculate from today
- Month end like "April end" → last day of that month
- Vague or unclear dates → null (do not guess)

INPUT TEXT:
{text}

OUTPUT (JSON only, no markdown):"""

    def parse_text(self, text: str, max_retries: int = 3) -> Dict[str, Any]:
        """
        Parse unstructured text into structured JSON with retry logic.
        
        Args:
            text: Input text to parse
            max_retries: Number of retry attempts on failure
            
        Returns:
            Validated dictionary matching schema
        """
        for attempt in range(max_retries):
            try:
                # Call Groq LLM with low temperature for consistency
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system", 
                            "content": "You are a precise JSON generator for construction orders. Return only valid JSON, no markdown."
                        },
                        {
                            "role": "user", 
                            "content": self.create_prompt(text)
                        }
                    ],
                    temperature=0.1,  # Low temperature for deterministic output
                    max_tokens=300
                )
                
                # Extract response content
                content = response.choices[0].message.content.strip()
                
                # Clean markdown formatting if present
                content = self.clean_json_response(content)
                
                # Parse JSON
                parsed = json.loads(content)
                
                # Validate and fix any issues
                validated = self.validate_and_fix(parsed)
                
                return validated
                
            except json.JSONDecodeError as e:
                print(f"Attempt {attempt + 1}/{max_retries}: JSON decode error - {e}")
                if attempt == max_retries - 1:
                    # Last resort: try to extract JSON manually
                    return self.emergency_json_extraction(content, text)
                    
            except Exception as e:
                print(f"Attempt {attempt + 1}/{max_retries}: Error - {e}")
                if attempt == max_retries - 1:
                    return self.create_fallback_response(text)
        
        # Should not reach here, but safety fallback
        return self.create_fallback_response(text)
    
    def clean_json_response(self, content: str) -> str:
        """
        Remove markdown code blocks and other formatting from LLM response.
        
        Args:
            content: Raw LLM response
            
        Returns:
            Cleaned JSON string
        """
        # Remove markdown code blocks
        content = re.sub(r'^```json\s*', '', content, flags=re.MULTILINE)
        content = re.sub(r'^```\s*', '', content, flags=re.MULTILINE)
        content = re.sub(r'\s*```$', '', content, flags=re.MULTILINE)
        return content.strip()
    
    def validate_and_fix(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate parsed JSON and fix common issues to match schema exactly.
        
        This is the key hallucination control mechanism:
        - Enforces correct types
        - Normalizes null values
        - Removes extra fields
        - Validates date formats
        
        Args:
            data: Raw parsed dictionary from LLM
            
        Returns:
            Validated and fixed dictionary
        """
        fixed = {}
        
        # Material name - required string, null if empty
        material = data.get('material_name')
        if material and str(material).strip() and str(material).lower() not in ['null', 'none', 'n/a']:
            fixed['material_name'] = str(material).strip()
        else:
            fixed['material_name'] = None
        
        # Quantity - must be number or null
        qty = data.get('quantity')
        if qty is not None:
            try:
                # Convert to int or float
                qty_str = str(qty)
                fixed['quantity'] = float(qty_str) if '.' in qty_str else int(float(qty_str))
            except (ValueError, TypeError):
                fixed['quantity'] = None
        else:
            fixed['quantity'] = None
        
        # Unit - string or null
        unit = data.get('unit')
        if unit and str(unit).strip() and str(unit).lower() not in ['null', 'none', 'n/a']:
            fixed['unit'] = str(unit).strip()
        else:
            fixed['unit'] = None
        
        # Project name - string or null
        proj = data.get('project_name')
        if proj and str(proj).strip() and str(proj).lower() not in ['null', 'none', 'n/a']:
            fixed['project_name'] = str(proj).strip()
        else:
            fixed['project_name'] = None
        
        # Location - string or null
        loc = data.get('location')
        if loc and str(loc).strip() and str(loc).lower() not in ['null', 'none', 'n/a']:
            fixed['location'] = str(loc).strip()
        else:
            fixed['location'] = None
        
        # Urgency - must be exactly "low", "medium", or "high"
        urgency = str(data.get('urgency', 'low')).lower().strip()
        if urgency in ['low', 'medium', 'high']:
            fixed['urgency'] = urgency
        else:
            fixed['urgency'] = 'low'  # Default fallback
        
        # Deadline - ISO date string or null
        deadline = data.get('deadline')
        fixed['deadline'] = self.validate_date(deadline)
        
        return fixed
    
    def validate_date(self, date_str: Any) -> Optional[str]:
        """
        Validate and normalize date to ISO format (YYYY-MM-DD).
        
        Args:
            date_str: Date string in any format
            
        Returns:
            ISO formatted date string or None
        """
        if not date_str:
            return None
            
        # Check for null-like values
        if str(date_str).lower() in ['null', 'none', 'n/a', '']:
            return None
        
        try:
            date_str = str(date_str).strip()
            # Try parsing ISO format
            parsed = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return parsed.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            return None
    
    def emergency_json_extraction(self, content: str, original_text: str) -> Dict[str, Any]:
        """
        Last resort: extract JSON from malformed response using regex.
        
        Args:
            content: Malformed response
            original_text: Original input text
            
        Returns:
            Best-effort parsed dictionary
        """
        try:
            # Try to find JSON object in response
            match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
            if match:
                json_str = match.group(0)
                parsed = json.loads(json_str)
                return self.validate_and_fix(parsed)
        except Exception as e:
            print(f"Emergency extraction failed: {e}")
        
        return self.create_fallback_response(original_text)
    
    def create_fallback_response(self, text: str) -> Dict[str, Any]:
        """
        Create a minimal valid response when all parsing attempts fail.
        
        Args:
            text: Original input text
            
        Returns:
            Valid dictionary with mostly null values
        """
        return {
            "material_name": f"Parse failed: {text[:50]}...",
            "quantity": None,
            "unit": None,
            "project_name": None,
            "location": None,
            "urgency": "low",
            "deadline": None
        }
    
    def process_batch(self, input_file: str, output_file: str) -> List[Dict[str, Any]]:
        """
        Process multiple inputs from file and save results.
        
        Args:
            input_file: Path to text file with one input per line
            output_file: Path to save JSON results
            
        Returns:
            List of results with inputs and outputs
        """
        results = []
        
        # Read inputs
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                inputs = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            print(f"ERROR: Input file '{input_file}' not found")
            return results
        
        print(f"Processing {len(inputs)} inputs from {input_file}...\n")
        print(f"Using Groq model: {self.model}\n")
        
        # Process each input
        for idx, text in enumerate(inputs, 1):
            print(f"[{idx}/{len(inputs)}] Processing: {text[:70]}...")
            
            try:
                result = self.parse_text(text)
                results.append({
                    "input": text,
                    "output": result
                })
                
                # Show preview
                mat = result['material_name'] or 'N/A'
                qty = result['quantity'] or 'N/A'
                urg = result['urgency']
                print(f"  ✓ {mat}, Qty: {qty}, Urgency: {urg}\n")
                
            except Exception as e:
                print(f"  ✗ Error: {e}\n")
                results.append({
                    "input": text,
                    "output": self.create_fallback_response(text)
                })
        
        # Save results
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"\n✓ Results saved to {output_file}")
        except Exception as e:
            print(f"\n✗ Error saving results: {e}")
        
        return results


def main():
    """
    Main execution function.
    
    Processes test_inputs.txt and generates outputs.json using Groq API
    """
    print("=" * 70)
    print("Powerplay AI Engineering Intern Assignment")
    print("Material Request Parser - Core Solution")
    print("Powered by Groq API (Llama 3.3)")
    print("=" * 70)
    print()
    
    # Check for API key
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        print("ERROR: GROQ_API_KEY environment variable not set")
        print("Get your free API key at: https://console.groq.com")
        print("Set it with: export GROQ_API_KEY='your-key-here'")
        return
    
    # Initialize parser with Groq
    try:
        # Using Llama 3.3 70B - best balance of speed and quality
        parser = MaterialRequestParser(api_key, model="llama-3.3-70b-versatile")
    except Exception as e:
        print(f"ERROR: Failed to initialize parser - {e}")
        return
    
    # Process batch
    input_file = 'test_inputs.txt'
    output_file = 'outputs.json'
    
    results = parser.process_batch(input_file, output_file)
    
    # Summary
    print("\n" + "=" * 70)
    print(f"Processing complete!")
    print(f"Total inputs: {len(results)}")
    print(f"Results saved to: {output_file}")
    print(f"Model used: llama-3.3-70b-versatile (Groq)")
    print("=" * 70)


if __name__ == "__main__":
    main()
