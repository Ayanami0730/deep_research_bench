"""OpenAI / OpenRouter backed LLM client for DRB-GPT5.

Drop-in replacement for the original google.genai-based client. Exposes the
same surface (`AIClient`, `call_model`, `scrape_url`, `Model`, `FACT_Model`)
so the rest of the codebase (deepresearch_bench_race.py, extract.py,
deduplicate.py, validate.py, generate_criteria.py) is unchanged.

Backend selection via env `LLM_BACKEND`:

  openrouter (default):
    OPENROUTER_API_KEY (required)
    OPENROUTER_BASE_URL  (default: https://openrouter.ai/api/v1)
    RACE_MODEL           (default: openai/gpt-5.5)
    FACT_MODEL           (default: openai/gpt-5.4-mini)

  openai:
    OPENAI_API_KEY (required)
    OPENAI_BASE_URL      (default: https://api.openai.com/v1)
    RACE_MODEL           (default: gpt-5.5)
    FACT_MODEL           (default: gpt-5.4-mini)

The three stages — 'clean' (chunk cleaning), 'score' (RACE scoring), 'fact'
(FACT citation extraction) — map to different `reasoning_effort` values.
Sampling params (temperature/top_p) are intentionally unset; gpt-5.x
reasoning models reject non-default values anyway.
"""
import os
from typing import Optional, Dict, Any, Tuple, Union
import requests
import logging


logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)


# ── Backend selection ──────────────────────────────────────────────
LLM_BACKEND = os.environ.get("LLM_BACKEND", "openrouter").lower()

_BACKEND_DEFAULTS = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_env":  "OPENROUTER_API_KEY",
        "race":     "openai/gpt-5.5",
        "fact":     "openai/gpt-5.4-mini",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "key_env":  "OPENAI_API_KEY",
        "race":     "gpt-5.5",
        "fact":     "gpt-5.4-mini",
    },
}

if LLM_BACKEND not in _BACKEND_DEFAULTS:
    raise ValueError(
        f"Unknown LLM_BACKEND={LLM_BACKEND!r}; expected one of "
        f"{list(_BACKEND_DEFAULTS)}"
    )

_BACKEND = _BACKEND_DEFAULTS[LLM_BACKEND]
_BASE_URL = os.environ.get(
    "OPENROUTER_BASE_URL" if LLM_BACKEND == "openrouter" else "OPENAI_BASE_URL",
    _BACKEND["base_url"],
)
_KEY_ENV = _BACKEND["key_env"]
API_KEY = os.environ.get(_KEY_ENV, "")

# Public module-level model identifiers — kept under the same names as the
# original Gemini-era code so downstream imports don't break.
Model = os.environ.get("RACE_MODEL", _BACKEND["race"])
FACT_Model = os.environ.get("FACT_MODEL", _BACKEND["fact"])

# Jina is unchanged — citation scraping still uses it.
READ_API_KEY = os.environ.get("JINA_API_KEY", "")

# ── Generation config ─────────────────────────────────────────────
MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "64000"))
HTTP_TIMEOUT_S = int(os.environ.get("LLM_HTTP_TIMEOUT", "600"))

_STAGE_CFG = {
    "clean": {"reasoning_effort": "low"},
    "score": {"reasoning_effort": "medium"},
    "fact":  {"reasoning_effort": "low"},
}


def _resolve_stage(stage: Optional[str]) -> Dict[str, str]:
    if stage is None:
        return _STAGE_CFG["score"]
    if stage not in _STAGE_CFG:
        raise ValueError(f"Unknown stage={stage!r}; expected {list(_STAGE_CFG)}")
    return _STAGE_CFG[stage]


class AIClient:
    """OpenAI-compat chat-completions client.

    `generate` has two call shapes:

      1) Simple (back-compat):
            text = client.generate(user_prompt, system_prompt="")
         Returns the assistant's content string.

      2) Metadata-aware (used by the v2 ArticleCleaner):
            text, stop_reason = client.generate(
                user_prompt, system_prompt="",
                return_metadata=True, stage="clean",
            )
         `stop_reason` is the upstream `finish_reason` ("stop" / "length" /
         "content_filter" / ...); the cleaning module reads "length" to
         trigger recursive chunking.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or API_KEY
        if not self.api_key:
            raise ValueError(
                f"API key not provided! Set env {_KEY_ENV} for backend "
                f"{LLM_BACKEND}."
            )
        self.model = model or Model
        self.base_url = _BASE_URL.rstrip("/")

    def _headers(self) -> Dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if LLM_BACKEND == "openrouter":
            h["HTTP-Referer"] = os.environ.get(
                "OPENROUTER_REFERER", "https://github.com/Ayanami0730/deep_research_bench"
            )
            h["X-Title"] = os.environ.get("OPENROUTER_TITLE", "DRB-GPT5")
        return h

    def _build_messages(self, user_prompt: str, system_prompt: str):
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        return messages

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        resp = requests.post(url, headers=self._headers(), json=payload,
                             timeout=HTTP_TIMEOUT_S)
        if resp.status_code != 200:
            raise Exception(
                f"{LLM_BACKEND} chat/completions {resp.status_code}: "
                f"{resp.text[:500]}"
            )
        return resp.json()

    def generate(
        self,
        user_prompt: str,
        system_prompt: str = "",
        model: Optional[str] = None,
        return_metadata: bool = False,
        stage: Optional[str] = None,
    ) -> Union[str, Tuple[str, str]]:
        model_to_use = model or self.model
        stage_cfg = _resolve_stage(stage)

        payload = {
            "model": model_to_use,
            "messages": self._build_messages(user_prompt, system_prompt),
            "max_completion_tokens": MAX_OUTPUT_TOKENS,
            "reasoning_effort": stage_cfg["reasoning_effort"],
        }

        try:
            data = self._post(payload)
        except Exception as e:
            raise Exception(f"Failed to generate content: {e}")

        try:
            choice = data["choices"][0]
            content = choice["message"]["content"] or ""
            stop_reason = choice.get("finish_reason", "stop")
        except (KeyError, IndexError, TypeError) as e:
            raise Exception(f"Malformed response from {LLM_BACKEND}: {data!r} ({e})")

        if return_metadata:
            return content, stop_reason
        return content


# ── FACT pipeline helper ──────────────────────────────────────────
def call_model(user_prompt: str) -> str:
    """Default LLM call for the FACT pipeline (extract / dedup / validate).
    Uses the cheap FACT_Model with low reasoning effort.
    """
    client = AIClient(model=FACT_Model)
    return client.generate(user_prompt, stage="fact")


# ── Jina scraping (unchanged from upstream) ──────────────────────
class WebScrapingJinaTool:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("JINA_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Jina API key not provided! Please set JINA_API_KEY environment variable."
            )

    def __call__(self, url: str) -> Dict[str, Any]:
        try:
            jina_url = f'https://r.jina.ai/{url}'
            headers = {
                "Accept": "application/json",
                'Authorization': self.api_key,
                'X-Timeout': "60000",
                "X-With-Generated-Alt": "true",
            }
            response = requests.get(jina_url, headers=headers)

            if response.status_code != 200:
                raise Exception(f"Jina AI Reader Failed for {url}: {response.status_code}")

            response_dict = response.json()

            return {
                'url': response_dict['data']['url'],
                'title': response_dict['data']['title'],
                'description': response_dict['data']['description'],
                'content': response_dict['data']['content'],
                'publish_time': response_dict['data'].get('publishedTime', 'unknown')
            }

        except Exception as e:
            logger.error(str(e))
            return {
                'url': url,
                'content': '',
                'error': str(e)
            }


# Lazy-init Jina tool: only instantiate when JINA_API_KEY is actually needed.
# Lets users run the RACE pipeline without setting JINA_API_KEY.
_jina_tool: Optional[WebScrapingJinaTool] = None


def scrape_url(url: str) -> Dict[str, Any]:
    global _jina_tool
    if _jina_tool is None:
        _jina_tool = WebScrapingJinaTool()
    return _jina_tool(url)


if __name__ == "__main__":
    print(f"Backend: {LLM_BACKEND}")
    print(f"Base URL: {_BASE_URL}")
    print(f"RACE Model: {Model}")
    print(f"FACT Model: {FACT_Model}")
    print(f"Key env: {_KEY_ENV} (set={bool(API_KEY)})")
