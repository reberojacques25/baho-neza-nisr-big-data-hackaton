"""Git clean filter: store Jupyter notebooks without outputs (stdin -> stdout).

Notebook outputs in this project can show household-level survey rows, so the repository keeps code and markdown
only; local working copies keep their outputs. Enabled by .gitattributes plus, once per clone:

    git config filter.strip-notebook-outputs.clean "python tools/strip_notebook_outputs.py"
    git config filter.strip-notebook-outputs.smudge cat
"""
import json
import sys


def strip(nb: dict) -> dict:
    for cell in nb.get("cells", []):
        if cell.get("cell_type") == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
        cell.get("metadata", {}).pop("execution", None)
    nb.get("metadata", {}).pop("widgets", None)
    return nb


if __name__ == "__main__":
    data = json.load(sys.stdin)
    json.dump(strip(data), sys.stdout, indent=1, ensure_ascii=False)
    sys.stdout.write("\n")
