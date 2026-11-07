"""Export the Field studio page from its notebook into the backend.

    .venv/bin/python scripts/export_studio.py           # from notebooks/Field_Studio.ipynb
    .venv/bin/python scripts/export_studio.py --pull    # first fetch the latest version from Colab
    .venv/bin/python scripts/export_studio.py path.ipynb

--pull downloads the shared Colab notebook from Google Drive (the link must be
shared as "Anyone with the link can view") and saves it to
notebooks/Field_Studio.ipynb without outputs, so git diffs show only code changes.

Reads the DEMO_HTML string literal from the last notebook cell that defines it
(the notebook isn't executed) and writes climate_lens/static/field-studio.html.
"""

import ast
import json
import os
import sys
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK = ROOT / "notebooks" / "Field_Studio.ipynb"
OUTPUT = ROOT / "climate_lens" / "static" / "field-studio.html"

# https://colab.research.google.com/drive/1A0LzF05A8uSyTlaT8ecrI10--2yZG157
COLAB_FILE_ID = os.environ.get("STUDIO_COLAB_FILE_ID", "1A0LzF05A8uSyTlaT8ecrI10--2yZG157")


def pull(file_id=COLAB_FILE_ID):
    """Fetch the notebook from Drive and save it with outputs cleared."""
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    with urlopen(url, timeout=30) as response:
        raw = response.read()
    try:
        nb = json.loads(raw)
        nb["cells"]
    except (ValueError, KeyError, TypeError):
        raise SystemExit("Drive didn't return a notebook. Check the Colab link is shared as "
                         "'Anyone with the link can view'.")
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
    NOTEBOOK.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Pulled {NOTEBOOK.relative_to(ROOT)} from Colab")


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
    args = sys.argv[1:]
    if "--pull" in args:
        args.remove("--pull")
        pull()
    notebook = Path(args[0]) if args else NOTEBOOK
    OUTPUT.write_text(demo_html(notebook), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)} from {notebook.name}")
