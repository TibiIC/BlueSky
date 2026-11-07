"""The AI layer: educated guesses and explanations, never edits.

Boundaries:
- The model sees ONE record and the evidence code computed about it, never the dataset.
- It returns structured output (Pydantic schema). It cannot change a value: anything it proposes
  is tested by code against the evidence, and stays labelled as model judgement (level F).
- Every call and answer is cached in quality/out/ai_cache.json with the model and prompt hash,
  so results are auditable and repeat runs cost nothing.
- Without ANTHROPIC_API_KEY the pipeline runs exactly the same, minus these notes.

Model: Claude Haiku 5.5 (claude-haiku-5-5), the cheapest current Claude model.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from quality.evidence import MECHANISMS, TOLERANCE, explain

MODEL = 'claude-haiku-5-5'
REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / 'quality/out/ai_cache.json'
MECH_IDS = [m[0] for m in MECHANISMS]

SYSTEM = (
    "You assist a data-quality reviewer at a Nordic food company (synthetic hackathon data). "
    "You see one record and the evidence that deterministic checks computed about it. "
    "Reason only from what is given. Never invent figures, sources or thresholds. "
    "Prefer the simplest explanation. If the evidence does not support a conclusion, say so."
)


class Hypothesis(BaseModel):
    mechanism: Literal[tuple(MECH_IDS + ['legitimate', 'unknown'])] = Field(description='One mechanism id from the library, "legitimate" if the value is plausibly correct, or "unknown".')
    reasoning: str = Field(description='Two sentences at most, citing the given evidence.')
    what_would_confirm: str = Field(description='One concrete check that would confirm or refute it.')


class ReviewNote(BaseModel):
    explanation: str = Field(description='Plain English for a sustainability manager, two sentences at most.')
    verdict: Literal['likely_error', 'unclear', 'likely_legitimate'] = Field(description=(
        'Your honest call on the evidence given. likely_error: the evidence and the explanation fit well and a '
        'legitimate reading would need a coincidence. likely_legitimate: a normal business reason explains the '
        'value better. unclear: the evidence genuinely cannot separate the two. Do not default to unclear.'))
    legitimate_reason: str = Field(description='The best case that the record is correct after all, one sentence.')
    suggested_check: str = Field(description='The single most useful check a person could do next.')


class LabelChoice(BaseModel):
    code: str = Field(description='Exactly one code from the allowed list, or "none".')
    reasoning: str


def _key() -> str | None:
    if os.environ.get('ANTHROPIC_API_KEY'):
        return os.environ['ANTHROPIC_API_KEY']
    env = REPO / 'frontend/.env'
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith('ANTHROPIC_API_KEY='):
                return line.split('=', 1)[1].strip() or None
    return None


class AI:
    def __init__(self, enabled: bool = True):
        self.key = _key() if enabled else None
        self.cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
        self.calls = 0
        self.errors: list[str] = []
        self.client = None
        if self.key:
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.key)

    @property
    def available(self) -> bool:
        return self.client is not None

    def _ask(self, prompt: str, schema: type[BaseModel]) -> dict | None:
        h = hashlib.sha256(f'{MODEL}\n{json.dumps(schema.model_json_schema(), sort_keys=True)}\n{prompt}'.encode()).hexdigest()
        if h in self.cache:
            return self.cache[h]['answer']
        if not self.client:
            return None
        import anthropic
        try:
            resp = self.client.messages.parse(model=MODEL, max_tokens=2048, system=SYSTEM,
                                              messages=[{'role': 'user', 'content': prompt}], output_format=schema)
        except anthropic.RateLimitError as e:
            self.errors.append(f'rate limited: {e}')
            return None
        except anthropic.APIStatusError as e:
            self.errors.append(f'API {e.status_code}: {e.message}')
            return None
        except anthropic.APIConnectionError as e:
            self.errors.append(f'connection: {e}')
            return None
        except ValueError as e:  # pydantic ValidationError: truncated or malformed answer
            self.calls += 1
            self.errors.append(f'invalid answer: {str(e)[:120]}')
            return None
        self.calls += 1
        if resp.stop_reason == 'refusal' or resp.parsed_output is None:
            self.errors.append(f'no answer (stop_reason={resp.stop_reason})')
            return None
        answer = resp.parsed_output.model_dump()
        self.cache[h] = {'model': MODEL, 'schema': schema.__name__, 'at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'answer': answer}
        return answer

    def save(self):
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(self.cache, indent=1, ensure_ascii=False))

    # ---------------------------------------------------------------- tasks

    def hypothesize(self, f, record: dict) -> None:
        """For an anomaly no known mechanism explains: ask for the likeliest mechanism, then
        TEST it in code against the evidence value. Only a fitting mechanism becomes a proposal."""
        library = '\n'.join(f'- {m}: {d}' for m, d, _ in MECHANISMS)
        prompt = (f"Record ({f.table}, {f.record_key}):\n{json.dumps(record, default=str)}\n\n"
                  f"Evidence computed by code: {f.evidence}\nField: {f.field}, observed {f.observed}, "
                  f"value the evidence points to: {f.locator.get('reference')}\n\n"
                  f"Known error mechanisms:\n{library}\n\nWhich explanation is most likely?")
        a = self._ask(prompt, Hypothesis)
        if not a:
            return
        test = None
        if a['mechanism'] in MECH_IDS and f.locator.get('reference') and f.observed is not None:
            hyp = [h for h in explain(float(f.observed), float(f.locator['reference'])) if h.mechanism == a['mechanism']]
            if hyp:
                test = {'mechanism': a['mechanism'], 'proposed': round(hyp[0].proposed, 6), 'misfit': round(hyp[0].misfit, 4),
                        'fits': hyp[0].misfit <= TOLERANCE['E'] and a['mechanism'] != 'none'}
        f.ai = {'model': MODEL, 'task': 'hypothesis', 'answer': a, 'code_test': test}
        if test and test['fits']:
            f.status, f.action, f.proposed = 'proposed', 'correct', test['proposed']
            f.level, f.confidence = 'F', 0.5
            f.sources.append({'level': 'F', 'source': f'{MODEL} (tested by code)', 'statement':
                              f"Model suggests {a['mechanism']}; code confirms it lands {test['misfit']:.0%} from the evidence.", 'value': test['proposed']})

    def review(self, f, record: dict) -> None:
        """Plain-English note and a second opinion for a review-queue item. Changes nothing."""
        ev = '\n'.join(f"- [{s['level']}] {s['statement']}" for s in f.sources)
        prompt = (f"Finding: {f.issue_type} on {f.record_key} ({f.table}).\nRecord: {json.dumps(record, default=str)}\n"
                  f"Proposed: {f.field} {f.observed} -> {f.proposed} ({f.action}).\nEvidence (level A strongest .. E weakest):\n{ev}\n"
                  f"Estimated inventory impact if applied: {f.impact_tco2e} t CO2e.\n\n"
                  "Explain it for the reviewer, and say whether the record could be legitimate after all.")
        a = self._ask(prompt, ReviewNote)
        if a:
            f.ai = {**(f.ai or {}), 'model': MODEL, 'task': (f.ai or {}).get('task', 'review'), 'review': a}

    def map_label(self, value: str, allowed: list[str], context: str) -> dict | None:
        """Map a free-text label to one allowed code. The caller must check the code is allowed."""
        a = self._ask(f'Context: {context}\nLabel: "{value}"\nAllowed codes: {allowed}\nWhich code is it?', LabelChoice)
        if a and a['code'] not in allowed:
            a['code'] = 'none'
        return a
