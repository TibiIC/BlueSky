"""Which hosted LLM writes report text: Snowflake Cortex or Google Gemini.

LLM_PROVIDER picks one (`snowflake` or `gemini`). Unset, Snowflake is used when
SNOWFLAKE_ACCOUNT and SNOWFLAKE_PAT are set, then Gemini when GEMINI_API_KEY is.

Snowflake Cortex is called through its OpenAI-compatible Chat Completions
endpoint with a programmatic access token (PAT):
https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-rest-api
"""

import json
import os
import re

import httpx

from . import gemini

SNOWFLAKE_DEFAULT_MODEL = "claude-sonnet-4-5"
SNOWFLAKE_TIMEOUT_S = 120


class LLMUnavailable(Exception):
    """No provider configured, or the request failed. The message is safe to show to users."""


def snowflake_configured():
    return bool(os.environ.get("SNOWFLAKE_ACCOUNT", "").strip() and os.environ.get("SNOWFLAKE_PAT", "").strip())


def provider():
    """The configured provider name, or None."""
    chosen = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if chosen == "snowflake":
        return "snowflake" if snowflake_configured() else None
    if chosen == "gemini":
        return "gemini" if gemini.configured() else None
    if snowflake_configured():
        return "snowflake"
    if gemini.configured():
        return "gemini"
    return None


def model_name():
    if provider() == "snowflake":
        return os.environ.get("SNOWFLAKE_MODEL", "").strip() or SNOWFLAKE_DEFAULT_MODEL
    if provider() == "gemini":
        return gemini.model_id()
    return None


def label():
    """How the report credits the text, e.g. 'Snowflake Cortex (claude-sonnet-4-5)'."""
    names = {"snowflake": "Snowflake Cortex", "gemini": "Google Gemini"}
    p = provider()
    return f"{names[p]} ({model_name()})" if p else None


def snowflake_url():
    """Accepts an account identifier (orgname-account_name) or the full account URL."""
    account = os.environ["SNOWFLAKE_ACCOUNT"].strip()
    account = re.sub(r"^https?://", "", account).split(".snowflakecomputing.com")[0].strip("/")
    account = account.replace("_", "-").lower()  # underscores aren't valid in the hostname
    return f"https://{account}.snowflakecomputing.com/api/v2/cortex/v1/chat/completions"


def snowflake_generate(prompt, system_instruction, schema, max_output_tokens, temperature):
    body = {
        "model": model_name(),
        "messages": [{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}],
        "max_completion_tokens": max_output_tokens,
        "temperature": temperature,
        "stream": False,
    }
    if schema is not None:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "report", "schema": schema}}
    headers = {"Authorization": f"Bearer {os.environ['SNOWFLAKE_PAT'].strip()}",
               "Content-Type": "application/json", "Accept": "application/json"}
    try:
        res = httpx.post(snowflake_url(), json=body, headers=headers, timeout=SNOWFLAKE_TIMEOUT_S)
    except httpx.HTTPError:
        raise LLMUnavailable("Snowflake Cortex is unreachable. Check SNOWFLAKE_ACCOUNT.")
    if res.status_code != 200:
        try:
            detail = res.json().get("message") or res.json().get("error", {}).get("message") or ""
        except ValueError:
            detail = ""
        raise LLMUnavailable(f"Snowflake Cortex request failed (HTTP {res.status_code}). {detail[:200]}".strip())
    try:
        return res.json()["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError):
        raise LLMUnavailable("Snowflake Cortex returned an unexpected response.")


def generate(prompt, system_instruction, *, schema=None, max_output_tokens=1500, temperature=0.2):
    """Text, or JSON matching `schema` (parsed), from the configured provider. Raises LLMUnavailable."""
    p = provider()
    if p is None:
        raise LLMUnavailable("No LLM is configured. Set SNOWFLAKE_ACCOUNT and SNOWFLAKE_PAT (or GEMINI_API_KEY) in backend/.env.")
    if p == "gemini":
        try:
            return gemini.generate(prompt, system_instruction, schema=schema,
                                   max_output_tokens=max_output_tokens, temperature=temperature)
        except gemini.GeminiUnavailable as error:
            raise LLMUnavailable(str(error))
    text = snowflake_generate(prompt, system_instruction, schema, max_output_tokens, temperature).strip()
    if not text:
        raise LLMUnavailable("Snowflake Cortex returned no text.")
    if schema is None:
        return text
    try:
        return json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", text))
    except ValueError:
        raise LLMUnavailable("Snowflake Cortex returned malformed JSON.")
