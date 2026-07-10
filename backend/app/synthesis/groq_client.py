"""
groq_client.py — the single thin LLM gateway.

Every generation call in the answer path goes through generate(). Primary
provider is Groq (openai/gpt-oss-120b). If Groq is rate-limited or otherwise
unavailable, and a Gemini key is configured, we transparently fall back to
Gemini (gemini-2.5-flash via the new google-genai SDK). Swapping or extending
providers later means changing THIS file only.
"""

from __future__ import annotations

from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_gemini_client, get_groq_client, get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


class LLMUnavailable(Exception):
    pass


def _is_rate_limit(exc: Exception) -> bool:
    """Detect Groq rate-limit / quota exhaustion. Groq raises a
    RateLimitError (HTTP 429); we also match on status/text defensively so a
    provider-side wording change doesn't silently disable the fallback."""
    name = exc.__class__.__name__.lower()
    if "ratelimit" in name:
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status == 429:
        return True
    text = str(exc).lower()
    return "rate limit" in text or "quota" in text or "429" in text


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10),
       reraise=True)
def _call_groq(system: str, user: str, temperature: float) -> str:
    resp = get_groq_client().chat.completions.create(
        model=get_settings().groq_model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=temperature,
        max_tokens=800,
    )
    usage = resp.usage
    log.info("LLM call (groq): prompt=%s completion=%s tokens",
             usage.prompt_tokens, usage.completion_tokens)
    return resp.choices[0].message.content or ""


def _call_gemini(system: str, user: str, temperature: float) -> str:
    """Fallback via the new google-genai SDK. Gemini has no separate 'system'
    role in generate_content, so we pass it as system_instruction."""
    client = get_gemini_client()
    if client is None:
        raise LLMUnavailable("Gemini fallback not configured (no GEMINI_API_KEY)")
    from google.genai import types

    resp = client.models.generate_content(
        model=get_settings().gemini_model,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=800,
        ),
    )
    log.info("LLM call (gemini fallback): model=%s", get_settings().gemini_model)
    return resp.text or ""


def generate(system: str, user: str, temperature: float = 0.1) -> str:
    """Primary → Groq. On rate-limit/quota (or any Groq failure) fall back to
    Gemini when configured. If both fail, raise LLMUnavailable."""
    try:
        return _call_groq(system, user, temperature)
    except Exception as groq_exc:
        rate_limited = _is_rate_limit(groq_exc)
        gemini = get_gemini_client()
        if gemini is not None:
            reason = "rate limit" if rate_limited else "error"
            log.warning("Groq %s (%s) — falling back to Gemini",
                        reason, groq_exc.__class__.__name__)
            try:
                return _call_gemini(system, user, temperature)
            except Exception as gem_exc:
                raise LLMUnavailable(
                    f"Groq failed ({groq_exc}); Gemini fallback also failed "
                    f"({gem_exc})") from gem_exc
        raise LLMUnavailable(str(groq_exc)) from groq_exc
