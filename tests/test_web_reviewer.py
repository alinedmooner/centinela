"""The website's live reviewer uses the same instructions and schema as the library."""

import runpy
from pathlib import Path

from centinela.detectors.llm import INSTRUCTIONS

GENERATOR = Path(__file__).resolve().parent.parent / "web" / "cloudflare" / "generate_reviewer.py"


def test_the_web_reviewer_matches_the_library():
    module = runpy.run_path(str(GENERATOR))
    actual = module["DESTINATION"].read_text(encoding="utf-8")
    assert actual == module["content"](), (
        "web/cloudflare/src/reviewer.js is out of date: "
        "uv run python web/cloudflare/generate_reviewer.py"
    )


def test_the_only_placeholder_of_the_instructions_is_the_marker():
    # The Worker replaces {marker} with replaceAll; Python uses format. They must agree.
    assert INSTRUCTIONS.format(marker="x") == INSTRUCTIONS.replace("{marker}", "x")
