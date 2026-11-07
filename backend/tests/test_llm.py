"""Run with: .venv/bin/python -m unittest discover tests"""

import json
import os
import unittest
from unittest import mock

import httpx

from climate_lens import llm

ENV = {"SNOWFLAKE_ACCOUNT": "myorg-my_account", "SNOWFLAKE_PAT": "pat-secret"}
SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}


def reply(status=200, content='{"a": "ok"}', body=None):
    return httpx.Response(status, json=body if body is not None else {"choices": [{"message": {"content": content}}]},
                          request=httpx.Request("POST", "https://x"))


@mock.patch.dict(os.environ, ENV, clear=False)
class Snowflake(unittest.TestCase):
    def setUp(self):
        for var in ("LLM_PROVIDER", "GEMINI_API_KEY", "SNOWFLAKE_MODEL"):
            os.environ.pop(var, None)

    def test_provider_and_label(self):
        self.assertEqual(llm.provider(), "snowflake")
        self.assertEqual(llm.label(), "Snowflake Cortex (claude-sonnet-4-5)")

    def test_url_from_identifier_or_full_url(self):
        self.assertEqual(llm.snowflake_url(), "https://myorg-my-account.snowflakecomputing.com/api/v2/cortex/v1/chat/completions")
        with mock.patch.dict(os.environ, {"SNOWFLAKE_ACCOUNT": "https://MyOrg-Acct.snowflakecomputing.com/"}):
            self.assertEqual(llm.snowflake_url(), "https://myorg-acct.snowflakecomputing.com/api/v2/cortex/v1/chat/completions")

    def test_request_shape_and_json_reply(self):
        with mock.patch.object(httpx, "post", return_value=reply()) as post:
            self.assertEqual(llm.generate("prompt", "system", schema=SCHEMA), {"a": "ok"})
        body, headers = post.call_args.kwargs["json"], post.call_args.kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer pat-secret")
        self.assertEqual([m["role"] for m in body["messages"]], ["system", "user"])
        self.assertEqual(body["response_format"]["json_schema"]["schema"], SCHEMA)
        self.assertFalse(body["stream"])

    def test_fenced_json_is_accepted(self):
        with mock.patch.object(httpx, "post", return_value=reply(content='```json\n{"a": "x"}\n```')):
            self.assertEqual(llm.generate("p", "s", schema=SCHEMA), {"a": "x"})

    def test_http_error_message(self):
        with mock.patch.object(httpx, "post", return_value=reply(403, body={"message": "Role lacks CORTEX_USER"})):
            with self.assertRaisesRegex(llm.LLMUnavailable, r"HTTP 403\)\. Role lacks CORTEX_USER"):
                llm.generate("p", "s")

    def test_unreachable(self):
        with mock.patch.object(httpx, "post", side_effect=httpx.ConnectError("no route")):
            with self.assertRaisesRegex(llm.LLMUnavailable, "unreachable"):
                llm.generate("p", "s")


class Choice(unittest.TestCase):
    def test_none_configured(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(llm.provider())
            with self.assertRaisesRegex(llm.LLMUnavailable, "No LLM is configured"):
                llm.generate("p", "s")

    def test_snowflake_preferred_over_gemini(self):
        with mock.patch.dict(os.environ, {**ENV, "GEMINI_API_KEY": "g"}, clear=True):
            self.assertEqual(llm.provider(), "snowflake")
        with mock.patch.dict(os.environ, {**ENV, "GEMINI_API_KEY": "g", "LLM_PROVIDER": "gemini"}, clear=True):
            self.assertEqual(llm.provider(), "gemini")


if __name__ == "__main__":
    unittest.main()
