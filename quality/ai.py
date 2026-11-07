"""One plain-English sentence per flagged number, written by Claude Haiku 5.5.

The model only explains. It sees one item and the facts the method computed about it, and returns
one sentence. It never changes a number or a status. Answers are cached in quality/out/ai_cache.json
(keyed by model, schema and prompt), so a re-run costs nothing. Without ANTHROPIC_API_KEY
(environment or frontend/.env) the pipeline runs the same, minus the sentences.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

MODEL = 'claude-haiku-5-5'
REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / 'quality/out/ai_cache.json'

SYSTEM = (
    'You explain data-curation findings to a sustainability manager at a Nordic food company. '
    'Write exactly one plain-English sentence of at most 25 words. If it was fixed automatically: say what '
    'went wrong and what it was fixed to. If a person decides: say what probably went wrong and the one thing '
    'to check. Use only the facts given, including the stated likely cause and applied value; never invent '
    'numbers, causes or sources. No jargon.'
)

# The known cause behind each typo, per kind of record, so the model does not have to guess it.
UNIT_CAUSE = {'energy': 'kWh typed into the MWh column', 'refrigerants': 'grams typed as kilograms',
              'fuel': 'litres and cubic metres mixed up', 'waste': 'kilograms and tonnes mixed up',
              'pcf': 'footprint given per tonne instead of per kilogram', 'commuting': 'metres typed as kilometres',
              'purchases': 'kilograms and tonnes mixed up', 'purchases_price': 'kilograms and tonnes mixed up'}


def cause(it) -> str:
    d = it.default
    if d in ('div1000', 'mul1000'):
        return UNIT_CAUSE.get(it.series, 'a unit mix-up (a factor of 1,000)')
    if d.startswith(('div1', 'mul1')):
        return 'a misplaced decimal point'
    if d == 'sek':
        return 'a Swedish-krona amount booked as euros'
    return {'gas': 'the wrong gas code for this system', 'goo': 'the internal log disagrees with the national registry',
            'soil': 'the farmer\'s soil answer disagrees with the soil map', 'missing': 'a missing monthly reading'}.get(
        it.series, 'no known typo explains it; the value may be real or a different mistake')


class Note(BaseModel):
    sentence: str = Field(description='One sentence, at most 30 words.')


def _key() -> str | None:
    if os.environ.get('ANTHROPIC_API_KEY'):
        return os.environ['ANTHROPIC_API_KEY']
    env = REPO / 'frontend/.env'
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith('ANTHROPIC_API_KEY='):
                return line.split('=', 1)[1].strip() or None
    return None


def facts(it, label: str) -> str:
    opts = '; '.join(f"{o['label']} ({o['tco2e']:+,.0f} t CO2e)" for o in it.options)
    applied = next((o for o in it.options if o['id'] == it.default), None)
    status = 'fixed automatically' if it.status == 'fixed' else 'a person decides; our best guess is applied meanwhile'
    lines = [f'Record: {label}, {it.context} ({it.record_key}, {it.year}).',
             f'Recorded: {it.recorded} {it.unit}. Expected: {it.expected} {it.unit}, from {it.expected_from}.',
             f'What the method found: {it.explanation}',
             f'Likely cause: {cause(it)}.',
             f"Applied now: {applied['label']} -> {applied['value']} {it.unit}." if applied else '',
             f'Status: {status}.',
             f'Options: {opts}.']
    return '\n'.join(x for x in lines if x)


class AI:
    def __init__(self, enabled: bool = True):
        key = _key() if enabled else None
        self.cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
        self.calls, self.errors, self.client = 0, [], None
        if key:
            import anthropic
            self.client = anthropic.Anthropic(api_key=key)

    @property
    def available(self) -> bool:
        return self.client is not None

    def sentence(self, prompt: str) -> str | None:
        h = hashlib.sha256(f'{MODEL}\n{SYSTEM}\n{json.dumps(Note.model_json_schema(), sort_keys=True)}\n{prompt}'.encode()).hexdigest()
        if h in self.cache:
            return self.cache[h]['sentence']
        if not self.client:
            return None
        import anthropic
        try:
            resp = self.client.messages.parse(model=MODEL, max_tokens=1500, system=SYSTEM,
                                              messages=[{'role': 'user', 'content': prompt}], output_format=Note)
        except anthropic.RateLimitError as e:
            self.errors.append(f'rate limited: {e}')
            return None
        except anthropic.APIStatusError as e:
            self.errors.append(f'API {e.status_code}: {e.message}')
            return None
        except anthropic.APIConnectionError as e:
            self.errors.append(f'connection: {e}')
            return None
        except ValueError as e:  # truncated or malformed answer
            self.errors.append(f'invalid answer: {str(e)[:120]}')
            return None
        self.calls += 1
        if resp.stop_reason == 'refusal' or resp.parsed_output is None:
            self.errors.append(f'no answer (stop_reason={resp.stop_reason})')
            return None
        s = resp.parsed_output.sentence.strip()
        self.cache[h] = {'model': MODEL, 'at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'sentence': s}
        return s

    def explain(self, items, labels: dict, limit: int = 250, workers: int = 8):
        """Adds it.ai = {model, sentence} to the items with the most tonnes at stake (requests in parallel)."""
        from concurrent.futures import ThreadPoolExecutor
        todo = sorted(items, key=lambda i: -i.at_stake)[:limit]
        prompts = [facts(it, labels.get(it.series, {}).get('label', it.series)) for it in todo]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            answers = list(pool.map(self.sentence, prompts))
        for it, s in zip(todo, answers):
            if s:
                it.ai = {'model': MODEL, 'sentence': s}

    def save(self):
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(self.cache, indent=1, ensure_ascii=False))
