from groq import Groq
import json
import os
import time
import logging
import re
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment from a .env file if present
load_dotenv()

# Load GROQ API key from environment (supports .env via python-dotenv).
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    logger.warning("GROQ_API_KEY not set in environment; Groq client may fail")

client = Groq(api_key=GROQ_API_KEY, timeout=1200)  # 20 minute timeout for long calls


def _extract_groq_text(response):
    """Extract text content from common Groq completion shapes.

    Returns (text_or_none, method_description)
    """
    try:
        # common shape from the snippet: completion.choices[0].message.content
        choices = getattr(response, "choices", None)
        if choices and len(choices) > 0:
            first = choices[0]
            # message may be a dict or object
            msg = getattr(first, "message", None) or (first.get("message") if isinstance(first, dict) else None)
            if msg:
                content = None
                # Try object attribute then dict
                content = getattr(msg, "content", None) if not isinstance(msg, dict) else msg.get("content")
                if content:
                    return content, "choices[0].message.content"
            # fallback: choice.text or choice.content
            for attr in ("text", "content"):
                val = getattr(first, attr, None) if not isinstance(first, dict) else first.get(attr)
                if val:
                    return val, f"choices[0].{attr}"
    except Exception:
        pass

    try:
        # last resort
        s = str(response)
        return s, "str(response)"
    except Exception:
        return None, "no-extract"


def get_groq_ai_output_from_text(system_prompt: str, user_prompt: str, text_input: str, model: str = "openai/gpt-oss-20b", temperature: float = 0, return_json: bool = False, output_dir: str = None, max_attempts: int = 3, delay: int = 20):
    """Call Groq chat completions with text input and return text or parsed JSON.

    Mirrors behavior of the existing `get_ai_output_from_text` but uses Groq's client.
    - `return_json=True` attempts to decode JSON from model output, writes debug files
      to `output_dir` on parse failures.
    - Retries on errors with linear backoff.
    """
    messages = []
    # build messages similar to the snippet: system then user/message pieces
    if system_prompt is not None:
        messages.append({"role": "system", "content": system_prompt})
    if text_input is not None:
        # put the long text as an assistant/user piece so model can reference it
        messages.append({"role": "user", "content": text_input})
    messages.append({"role": "user", "content": user_prompt})

    for attempt in range(1, max_attempts + 1):
        try:
            logger.info("Groq model call %s attempt %d", model, attempt)
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_completion_tokens=50000,
                top_p=1,
                reasoning_effort="medium",
            )
        
            resp_text, method = _extract_groq_text(completion)
            logger.info("Groq response extracted using %s present=%s", method, resp_text is not None)

            if return_json:
                if resp_text is None:
                    raise RuntimeError("No text in Groq response to parse as JSON")
                # strip common fences
                cleaned = re.sub(r"```json\s*|```", "", resp_text).strip()
                try:
                    parsed = json.loads(cleaned)
                    return parsed
                except Exception as parse_err:
                    logger.exception("Failed to parse JSON from Groq response: %s", parse_err)
                    if output_dir:
                        try:
                            os.makedirs(output_dir, exist_ok=True)
                            raw_path = os.path.join(output_dir, f"groq_response_raw_attempt{attempt}.txt")
                            with open(raw_path, "w", encoding="utf-8") as rf:
                                rf.write(resp_text or "")
                            summary_path = os.path.join(output_dir, f"groq_response_summary_attempt{attempt}.txt")
                            with open(summary_path, "w", encoding="utf-8") as sf:
                                sf.write("--- parse_error ---\n")
                                sf.write(repr(parse_err) + "\n\n")
                                sf.write("--- extraction_method ---\n")
                                sf.write(str(method) + "\n\n")
                                sf.write("--- cleaned (repr) ---\n")
                                sf.write(repr(cleaned) + "\n\n")
                                sf.write("--- resp_text preview ---\n")
                                sf.write((resp_text[:2000] + "...[truncated]") if resp_text and len(resp_text) > 2000 else (resp_text or ""))
                        except Exception:
                            logger.exception("Failed writing Groq parse debug files")
                    raise RuntimeError("Failed to parse JSON from Groq response; raw and summary written to output_dir if provided") from parse_err

            # not JSON: return textual content
            return resp_text

        except Exception as e:
            logger.warning("Groq model call attempt %d failed: %s", attempt, e, exc_info=True)
            if attempt == max_attempts:
                logger.error("All Groq attempts failed")
                raise
            backoff = min(delay * attempt, 90)
            logger.info("Sleeping %s seconds before retry", backoff)
            time.sleep(backoff)


if __name__ == "__main__":
    # simple CLI quick test when run directly
    logging.basicConfig(level=logging.INFO)
    sp = "You are a helpful assistant."
    up = "Say hello and return JSON: {\"greeting\": \"hello\" }"
    try:
        out = get_groq_ai_output_from_text(sp, up, "", return_json=True, output_dir=".")
        print(json.dumps(out, indent=2, ensure_ascii=False))
    except Exception as e:
        print("Error:", e)
