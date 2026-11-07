"""Export the Field studio page from its notebook into the backend.

    .venv/bin/python scripts/export_studio.py [notebook]

Reads the DEMO_HTML string literal from the last notebook cell that defines it
(the notebook isn't executed) and writes climate_lens/static/field-studio.html.
"""

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK = ROOT / "notebooks" / "Field_Studio.ipynb"
OUTPUT = ROOT / "climate_lens" / "static" / "field-studio.html"


def demo_html(notebook):
    html = None
    for cell in json.loads(notebook.read_text(encoding="utf-8"))["cells"]:
        if cell["cell_type"] != "code":
            continue
        for node in ast.parse("".join(cell["source"])).body:
            if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "DEMO_HTML" for t in node.targets):
                html = ast.literal_eval(node.value)
    if html is None:
        raise SystemExit(f"No DEMO_HTML assignment found in {notebook}")
    return html


if __name__ == "__main__":
    notebook = Path(sys.argv[1]) if len(sys.argv) > 1 else NOTEBOOK
    OUTPUT.write_text(demo_html(notebook), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} from {notebook.name}")
