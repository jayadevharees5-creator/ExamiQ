import os
import json
import time
import re
from typing import Dict, Any, List, Optional
from groq import Groq, APIConnectionError, RateLimitError, APIStatusError
from config import Config

class GroqClientWrapper:
    """
    Production-ready Groq API wrapper with structured JSON output,
    automatic retries, backoff handling, and robust JSON repair.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = (api_key or Config.GROQ_API_KEY or "").strip()
        self.model = model or Config.DEFAULT_GROQ_MODEL
        self._client: Optional[Groq] = None
        if self.api_key:
            try:
                self._client = Groq(api_key=self.api_key)
            except Exception:
                self._client = None

    def is_configured(self) -> bool:
        return bool(self.api_key and len(self.api_key) > 5)

    def validate_connection(self) -> Dict[str, Any]:
        """
        Tests whether the API key and model work with a minimal prompt.
        """
        if not self.is_configured():
            return {
                "valid": False,
                "message": "Groq API key is missing. Please provide your key in .env or the Settings panel."
            }
        try:
            client = self.get_client()
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that outputs JSON."},
                    {"role": "user", "content": "Generate a JSON object with key status and value ok."}
                ],
                max_tokens=100,
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            return {"valid": True, "message": f"Connected to Groq ({self.model}) successfully!"}
        except APIStatusError as e:
            if "invalid_api_key" in str(e).lower() or e.status_code == 401:
                return {"valid": False, "message": "Invalid Groq API Key. Please verify your credentials."}
            return {"valid": False, "message": f"Groq API error: {e.message if hasattr(e, 'message') else str(e)}"}
        except Exception as e:
            return {"valid": False, "message": f"Connection error: {str(e)}"}

    def get_client(self) -> Groq:
        if not self.is_configured():
            raise ValueError("Groq API Key is not set. Please set GROQ_API_KEY.")
        if self._client is None:
            self._client = Groq(api_key=self.api_key)
        return self._client

    @staticmethod
    def clean_json_string(text: str) -> str:
        """
        Strips markdown code fences, stray formatting, or leading/trailing commentary.
        """
        text = text.strip()
        # Remove ```json and ``` fences
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*```$', '', text)
        
        # Find first '{' or '[' and last '}' or ']'
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            return text[first_brace:last_brace + 1]
        
        return text.strip()

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 3000,
        retries: int = 1
    ) -> Dict[str, Any]:
        """
        Calls Groq chat completion with JSON mode. Strategy:
          1. Try json_object mode on primary model (fast path).
          2. If json_object fails (400), retry in plain text mode.
          3. Only try a fallback model on rate-limit (429).
        This avoids the old 4-combination loop that doubled latency.
        """
        client = self.get_client()
        last_error = None
        start_time = time.time()

        candidates = [self.model, "openai/gpt-oss-120b", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"]
        models_to_try = []
        for m in candidates:
            if m and m not in models_to_try:
                models_to_try.append(m)
        tried_models = set()

        for current_model in models_to_try:
            if current_model in tried_models:
                continue
            tried_models.add(current_model)

            # Fast path: json_object mode first, then text mode fallback
            modes = [{"type": "json_object"}, None]
            for mode in modes:
                for attempt in range(retries + 1):
                    try:
                        kwargs = {
                            "model": current_model,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt}
                            ],
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                        }
                        if mode is not None:
                            kwargs["response_format"] = mode

                        response = client.chat.completions.create(**kwargs)
                        raw_content = response.choices[0].message.content or "{}"
                        cleaned = self.clean_json_string(raw_content)
                        parsed_json = json.loads(cleaned)
                        elapsed = round(time.time() - start_time, 2)
                        mode_label = "json_mode" if mode else "text_mode"
                        print(f"[Groq] OK in {elapsed}s ({mode_label}, model={current_model}, max_tok={max_tokens})")
                        return {"success": True, "data": parsed_json, "raw": raw_content}

                    except RateLimitError as rle:
                        last_error = f"Rate limit on {current_model}: {str(rle)}"
                        print(f"[Groq] Rate-limit {current_model}, switching to fallback...")
                        # Jump to next model immediately (skip remaining modes/retries)
                        break
                    except json.JSONDecodeError as jde:
                        last_error = f"Invalid JSON from model: {str(jde)}"
                        if attempt < retries:
                            time.sleep(0.3)
                    except APIStatusError as ase:
                        err_str = str(ase)
                        last_error = f"Groq API {ase.status_code}: {ase.message if hasattr(ase, 'message') else err_str}"
                        if ase.status_code == 400 and ("json_validate_failed" in err_str or "failed_generation" in err_str):
                            print(f"[Groq] json_object failed on {current_model}, falling back to text mode...")
                            break  # Try text mode (next mode iteration)
                        if ase.status_code in (429, 500, 502, 503):
                            print(f"[Groq] {ase.status_code} on {current_model}, trying fallback...")
                            break
                        # Non-retryable error — return immediately
                        return {"success": False, "error": last_error, "data": None}
                    except Exception as e:
                        last_error = f"Unexpected error: {str(e)}"
                        if attempt < retries:
                            time.sleep(0.3)
                else:
                    # All retries for this mode exhausted without break — try next mode
                    continue
                # If we broke out of the retry loop (rate-limit/status), check if it's rate-limit to skip to next model
                if "Rate limit" in (last_error or "") or "429" in (last_error or ""):
                    break  # Break mode loop → try next model

        return {"success": False, "error": last_error, "data": None}

