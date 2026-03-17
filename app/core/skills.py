# app/core/skills.py — Carregamento de skills a partir de SKILL.md
import os
import re
from typing import Dict, List, Optional, Tuple


SKILL_FILE = "SKILL.md"


def _parse_frontmatter(content: str) -> Tuple[Dict, str]:
    """Extrai frontmatter YAML (entre ---) e retorna (metadados, resto do conteúdo)."""
    meta = {}
    body = content
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if match:
        fm, body = match.group(1), match.group(2)
        for line in fm.split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                meta[key.strip()] = val.strip().strip("'\"").replace("\n", " ").strip()
    return meta, body.strip()


def load_skills(base_dir: str) -> List[Dict]:
    """
    Carrega todas as skills a partir de base_dir.
    Cada subpasta contendo SKILL.md vira uma skill.
    Retorna lista de dicts: id, name, description, content, body, model.
    """
    skills = []
    base = os.path.abspath(base_dir)
    if not os.path.isdir(base):
        return skills
    for entry in sorted(os.listdir(base)):
        path = os.path.join(base, entry)
        skill_file = os.path.join(path, SKILL_FILE)
        if os.path.isdir(path) and os.path.isfile(skill_file):
            with open(skill_file, "r", encoding="utf-8") as f:
                raw = f.read()
            meta, body = _parse_frontmatter(raw)
            skill_id = entry
            name = meta.get("name", skill_id)
            description = meta.get("description", "")
            skills.append({
                "id": skill_id,
                "name": name,
                "description": description,
                "model": meta.get("model"),
                "content": raw,
                "body": body,
            })
    return skills


def get_skill_by_id(skills: List[Dict], skill_id: str) -> Optional[Dict]:
    """Retorna a skill com o id dado ou None."""
    for s in skills:
        if s["id"] == skill_id:
            return s
    return None
