from orion_mcp.core.prompts.skill_model import Skill, load_skill_yaml


def test_load_skill_yaml() -> None:
    text = """
name: demo
prompt: |
  Olá
metadata:
  k: 1
"""
    s = load_skill_yaml(text)
    assert isinstance(s, Skill)
    assert s.name == "demo"
    assert "Olá" in s.prompt
