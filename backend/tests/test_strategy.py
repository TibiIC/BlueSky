"""Run with: .venv/bin/python -m unittest discover tests"""

import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from climate_lens import llm, strategy
from climate_lens.app import app

client = TestClient(app)

MINI_PAGE = (
    '<details id="aiSettings"><summary>Gemini settings</summary></details>'
    "<p>Sends this farm’s screening metrics, crop and mission to Google without its farm ID or coordinates. "
    "Financial and trial results are optional. Use an API key from your Gemini project.</p><script>\n"
    "let selection=null, scopeName='', showUploadRisk=false;\n"
    "submit=async()=>{const config=geminiConfig;try{\n"
    "  const response=await fetch('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',{});\n"
    " }catch{out.textContent='Gemini could not connect. Use the built-in roadmap.'}finally{}};\n"
    "\ndraw();\n</script>"
)


class Patch(unittest.TestCase):
    def test_mini_page(self):
        html = strategy.patch(MINI_PAGE)
        self.assertIn('<details id="aiSettings" hidden>', html)
        self.assertNotIn("generativelanguage", html)
        self.assertIn("fetch(RECOMMEND_URL", html)
        self.assertIn("Snowflake Cortex", html)
        self.assertLess(html.index("const GLOBE="), html.rindex("draw();"))

    def test_changed_page_fails_loudly(self):
        with self.assertRaisesRegex(ValueError, "Strategy page changed"):
            strategy.patch(MINI_PAGE.replace("const config=geminiConfig;", ""))

    @unittest.skipUnless(strategy.PAGE.exists(), "strategy page not present (it isn't in git)")
    def test_real_page_patches_and_serves(self):
        res = client.get("/strategy")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("generativelanguage.googleapis.com", res.text)


class Recommend(unittest.TestCase):
    def test_uses_llm_and_server_side_instructions(self):
        with mock.patch.object(llm, "generate", return_value="Conclusion\nTrial.") as generate, \
             mock.patch.object(llm, "label", return_value="Snowflake Cortex (test)"):
            res = client.post("/strategy/recommend", json={"context": {"mission": "Review fertilizer use", "globeScenario": {"year": 2040}}})
        self.assertEqual(res.json(), {"text": "Conclusion\nTrial.", "writer": "Snowflake Cortex (test)"})
        prompt, instructions = generate.call_args.args
        self.assertIn('"globeScenario"', prompt)
        self.assertIs(instructions, strategy.INSTRUCTIONS)

    def test_llm_down_is_503(self):
        with mock.patch.object(llm, "generate", side_effect=llm.LLMUnavailable("No LLM is configured.")):
            res = client.post("/strategy/recommend", json={"context": {}})
        self.assertEqual((res.status_code, res.json()["detail"]), (503, "No LLM is configured."))

    def test_oversized_context_rejected(self):
        self.assertEqual(client.post("/strategy/recommend", json={"context": {"x": "a" * 40_000}}).status_code, 413)


if __name__ == "__main__":
    unittest.main()
