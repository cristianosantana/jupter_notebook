"""
Contrato D17 mínimo: # Objetivo primário e ## Regras não negociáveis
em app/skills/*.md e app/prompts/**/*.md (except não aplicável).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "app" / "skills"
PROMPTS = ROOT / "app" / "prompts"

REQUIRED_H1 = "# Objetivo primário"
REQUIRED_H2 = "## Regras não negociáveis"


def _check_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            text = parts[2]
    assert REQUIRED_H1 in text, f"{path}: falta {REQUIRED_H1!r}"
    assert REQUIRED_H2 in text, f"{path}: falta {REQUIRED_H2!r}"


def test_skills_contract():
    for f in sorted(SKILLS.glob("*.md")):
        _check_file(f)


def test_prompts_contract():
    for f in sorted(PROMPTS.rglob("*.md")):
        _check_file(f)
