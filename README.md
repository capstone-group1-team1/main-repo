# main-repo
AI Capstone Project for Group 1 Team 1

## LLM providers

FacilityGraph AI uses xAI with `grok-4.5` as its primary LLM provider. Groq
with `meta-llama/llama-4-scout-17b-16e-instruct` is used only when xAI has a
transient provider failure (HTTP 429, timeout, connection failure, or HTTP
5xx). Configuration and authentication errors do not fall back.

Set `XAI_API_KEY`, `XAI_BASE_URL`, `XAI_MODEL`, `GROQ_API_KEY`, and
`GROQ_MODEL` in a local `.env` file. Never commit `.env` or API keys.

### Validation

```bash
python -m compileall -q backend/app backend/tests
PYTHONPATH=backend pytest -q backend/tests/test_output_guard.py backend/tests/test_llm_provider_fallback.py
docker compose config --quiet
docker compose build api web
```
