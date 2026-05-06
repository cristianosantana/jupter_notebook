import yaml

from orion_mcp_v2.config.settings import Settings
from orion_mcp_v2.skill.loader import load_all_skills, skills_dir


def test_skills():
    reg = load_all_skills()
    assert reg.get("faturamento_analyzer")
    assert reg.get("session_intent_analyzer")


def test_skill_yaml_prompts_under_config_cap():
    cap = Settings().skill_system_prompt_max_chars
    for path in skills_dir().glob("*.yaml"):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(raw, dict)
        sp = raw.get("system_prompt") or ""
        assert len(sp) <= cap, f"{path.name} excede skill_system_prompt_max_chars ({cap})"
