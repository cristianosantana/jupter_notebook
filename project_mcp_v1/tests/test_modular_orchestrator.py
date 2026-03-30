"""
Testes para ModularOrchestrator.

Executa:
    python -m pytest test_modular_orchestrator.py -v
"""

import pytest
from pathlib import Path
from app.orchestrator import (
    SkillLoader,
    ModelRouter,
    SkillMetadata,
    AgentType,
    ModelType,
)


class TestSkillLoader:
    """Testa carregamento e parsing de SKILLs."""

    def setup_method(self):
        """Prepara SkillLoader."""
        self.skills_dir = Path(__file__).resolve().parent / "app" / "skills"
        self.loader = SkillLoader(self.skills_dir)

    def test_load_maestro_skill(self):
        """Testa carregamento do SKILL maestro."""
        skill_text, metadata = self.loader.load_skill("maestro")

        assert skill_text
        assert isinstance(metadata, SkillMetadata)
        assert metadata.model == "opus"
        assert metadata.context_budget == 50000
        assert metadata.max_tokens == 1500
        assert metadata.role == "orchestrator"

    def test_load_analise_os_skill(self):
        """Testa carregamento do SKILL analise_os."""
        skill_text, metadata = self.loader.load_skill("analise_os")

        assert skill_text
        assert metadata.model == "sonnet"
        assert metadata.context_budget == 100000
        assert metadata.role == "analyst"
        assert metadata.agent_type == "analise_os"

    def test_load_clusterizacao_skill(self):
        """Testa carregamento do SKILL clusterizacao."""
        skill_text, metadata = self.loader.load_skill("clusterizacao")

        assert skill_text
        assert metadata.model == "opus"
        assert metadata.context_budget == 100000
        assert metadata.temperature == 0.4

    def test_load_visualizador_skill(self):
        """Testa carregamento do SKILL visualizador."""
        skill_text, metadata = self.loader.load_skill("visualizador")

        assert skill_text
        assert metadata.model == "sonnet"
        assert metadata.context_budget == 80000

    def test_load_agregador_skill(self):
        """Testa carregamento do SKILL agregador."""
        skill_text, metadata = self.loader.load_skill("agregador")

        assert skill_text
        assert metadata.model == "haiku"
        assert metadata.context_budget == 60000

    def test_load_projecoes_skill(self):
        """Testa carregamento do SKILL projecoes."""
        skill_text, metadata = self.loader.load_skill("projecoes")

        assert skill_text
        assert metadata.model == "opus"
        assert metadata.agent_type == "projecoes"

    def test_skill_caching(self):
        """Testa que SKILLs são cacheados."""
        # Primeira carga
        skill1, meta1 = self.loader.load_skill("analise_os")

        # Segunda carga (deve vir do cache)
        skill2, meta2 = self.loader.load_skill("analise_os")

        # Devem ser as mesmas instâncias (cache funciona)
        assert skill1 == skill2
        assert meta1 is meta2

    def test_yaml_parsing_with_spaces(self):
        """Testa que parser YAML ignora espaços."""
        yaml_str = """
        model: claude-sonnet-4.6
        context_budget: 100000
        max_tokens: 2000
        temperature: 0.5
        """
        metadata = SkillLoader._parse_yaml(yaml_str)

        assert metadata.context_budget == 100000
        assert metadata.max_tokens == 2000
        assert abs(metadata.temperature - 0.5) < 0.01

    def test_skill_file_not_found(self):
        """Testa erro quando SKILL não existe."""
        with pytest.raises(FileNotFoundError):
            self.loader.load_skill("agente_inexistente")

    def test_all_skills_exist(self):
        """Testa que todos os 6 SKILLs existem."""
        agent_types = ["maestro", "analise_os", "clusterizacao", "visualizador", "agregador", "projecoes"]

        for agent_type in agent_types:
            skill_text, metadata = self.loader.load_skill(agent_type)
            assert skill_text, f"SKILL {agent_type} está vazio"
            assert metadata, f"Metadata de {agent_type} não foi parseada"


class TestModelRouter:
    """Testa roteamento de modelos."""

    def test_maestro_uses_haiku(self):
        """Maestro deve usar Haiku (rápido, barato)."""
        model = ModelRouter.get_model("maestro")
        assert model == "haiku"

    def test_analise_os_uses_sonnet(self):
        """analise_os deve usar Sonnet (balanceado)."""
        model = ModelRouter.get_model("analise_os")
        assert model == "sonnet"

    def test_clusterizacao_uses_opus(self):
        """clusterizacao deve usar Opus (complexo, ML)."""
        model = ModelRouter.get_model("clusterizacao")
        assert model == "opus"

    def test_visualizador_uses_sonnet(self):
        """visualizador deve usar Sonnet."""
        model = ModelRouter.get_model("visualizador")
        assert model == "sonnet"

    def test_agregador_uses_haiku(self):
        """agregador deve usar Haiku (síntese rápida)."""
        model = ModelRouter.get_model("agregador")
        assert model == "haiku"

    def test_projecoes_uses_opus(self):
        """projecoes deve usar Opus (complexo, forecasting)."""
        model = ModelRouter.get_model("projecoes")
        assert model == "opus"

    def test_all_agents_routed(self):
        """Testa que todos os agentes têm roteamento definido."""
        agent_types = ["maestro", "analise_os", "clusterizacao", "visualizador", "agregador", "projecoes"]
        valid_models = {"haiku", "sonnet", "opus"}

        for agent_type in agent_types:
            model = ModelRouter.get_model(agent_type)
            assert model in valid_models, f"Modelo inválido para {agent_type}: {model}"

    def test_unknown_agent_defaults_to_sonnet(self):
        """Agente desconhecido deve defaultar para Sonnet."""
        model = ModelRouter.get_model("agente_inexistente")
        assert model == "sonnet"


class TestSkillMetadata:
    """Testa classe SkillMetadata."""

    def test_metadata_creation(self):
        """Testa criação de SkillMetadata."""
        metadata = SkillMetadata(
            model="sonnet",
            context_budget=100000,
            max_tokens=2000,
            temperature=0.5,
            role="analyst",
            agent_type="analise_os"
        )

        assert metadata.model == "sonnet"
        assert metadata.context_budget == 100000
        assert metadata.max_tokens == 2000
        assert abs(metadata.temperature - 0.5) < 0.01
        assert metadata.role == "analyst"
        assert metadata.agent_type == "analise_os"

    def test_metadata_defaults(self):
        """Testa valores padrão de SkillMetadata."""
        metadata = SkillMetadata(
            model="opus",
            context_budget=100000,
            max_tokens=1000,
            temperature=0.3,
            role="orchestrator"
        )

        assert metadata.agent_type is None


class TestArchitectureIntegration:
    """Testes de integração da arquitetura modular."""

    def setup_method(self):
        """Setup para testes de integração."""
        self.skills_dir = Path(__file__).resolve().parent / "app" / "skills"
        self.loader = SkillLoader(self.skills_dir)

    def test_skill_model_consistency(self):
        """Testa que modelo do SKILL bate com ModelRouter."""
        agent_model_pairs = [
            ("maestro", "haiku"),
            ("analise_os", "sonnet"),
            ("clusterizacao", "opus"),
            ("visualizador", "sonnet"),
            ("agregador", "haiku"),
            ("projecoes", "opus"),
        ]

        for agent_type, expected_model in agent_model_pairs:
            skill_text, metadata = self.loader.load_skill(agent_type)
            routed_model = ModelRouter.get_model(agent_type)

            # Ambos devem concordar
            assert metadata.model == expected_model, f"{agent_type}: SKILL diz {metadata.model}"
            assert routed_model == expected_model, f"{agent_type}: Router diz {routed_model}"

    def test_all_skills_have_context_budget(self):
        """Testa que todos SKILLs têm context_budget definido."""
        agent_types = ["maestro", "analise_os", "clusterizacao", "visualizador", "agregador", "projecoes"]

        for agent_type in agent_types:
            skill_text, metadata = self.loader.load_skill(agent_type)
            assert metadata.context_budget > 0, f"{agent_type} context_budget <= 0"
            assert metadata.context_budget <= 200000, f"{agent_type} context_budget > 200k"

    def test_all_skills_have_valid_temperature(self):
        """Testa que temperatura está entre 0 e 2."""
        agent_types = ["maestro", "analise_os", "clusterizacao", "visualizador", "agregador", "projecoes"]

        for agent_type in agent_types:
            skill_text, metadata = self.loader.load_skill(agent_type)
            assert 0 <= metadata.temperature <= 2, f"{agent_type} temperatura inválida: {metadata.temperature}"

    def test_hierarchical_context_budgets(self):
        """Testa que Maestro tem menos contexto que agentes especializados."""
        maestro_skill, maestro_meta = self.loader.load_skill("maestro")
        analise_skill, analise_meta = self.loader.load_skill("analise_os")

        # Maestro deve ter menos contexto (mais leve)
        assert maestro_meta.context_budget < analise_meta.context_budget
        # Maestro < 50k é bom (rápido)
        assert maestro_meta.context_budget == 50000

    def test_agent_type_assignments(self):
        """Testa que agent_type está correto em cada SKILL."""
        expected_assignments = {
            "analise_os": "analise_os",
            "clusterizacao": "clusterizacao",
            "visualizador": "visualizador",
            "agregador": "agregador",
            "projecoes": "projecoes",
        }

        for filename, expected_agent_type in expected_assignments.items():
            skill_text, metadata = self.loader.load_skill(filename)
            assert metadata.agent_type == expected_agent_type, \
                f"{filename}: esperado {expected_agent_type}, got {metadata.agent_type}"


class TestPerformanceCharacteristics:
    """Testa características de performance da arquitetura."""

    def setup_method(self):
        """Setup para testes de performance."""
        self.skills_dir = Path(__file__).resolve().parent / "app" / "skills"
        self.loader = SkillLoader(self.skills_dir)

    def test_skill_caching_efficiency(self):
        """Testa que caching melhora performance."""
        import time

        # Primeira carga (carrega do disco)
        start = time.time()
        self.loader.load_skill("analise_os")
        first_load_time = time.time() - start

        # Segunda carga (cache)
        start = time.time()
        self.loader.load_skill("analise_os")
        cached_load_time = time.time() - start

        # Cache deve ser muito mais rápido
        assert cached_load_time < first_load_time / 10

    def test_maestro_smaller_than_analise_os(self):
        """Testa que Maestro é mais leve que analise_os."""
        maestro_skill, maestro_meta = self.loader.load_skill("maestro")
        analise_skill, analise_meta = self.loader.load_skill("analise_os")

        assert len(maestro_skill) < len(analise_skill)
        assert maestro_meta.max_tokens < analise_meta.max_tokens


# ======================== FIXTURES ========================

@pytest.fixture
def skills_dir():
    """Fixture que fornece diretório de SKILLs."""
    return Path(__file__).resolve().parent / "app" / "skills"


@pytest.fixture
def skill_loader(skills_dir):
    """Fixture que fornece SkillLoader inicializado."""
    return SkillLoader(skills_dir)


# ======================== INTEGRATION TESTS ========================

class TestModularOrchestratorSetup:
    """Testes de setup do ModularOrchestrator (sem MCP client real)."""

    def test_imports_work(self):
        """Testa que todos os imports funcionam."""
        from app.modular_orchestrator import (
            ModularOrchestrator,
            SkillLoader,
            ModelRouter,
            SkillMetadata,
            AgentType,
            ModelType,
        )
        assert ModularOrchestrator
        assert SkillLoader
        assert ModelRouter
        assert SkillMetadata

    def test_agent_type_enum_values(self):
        """Testa que AgentType tem todos os valores esperados."""
        valid_agents = {"maestro", "analise_os", "clusterizacao", "visualizador", "agregador", "projecoes"}
        # Note: Não podemos testar literal types diretamente em runtime,
        # mas podemos testar que os valores usados em ModelRouter são válidos
        for agent in valid_agents:
            model = ModelRouter.get_model(agent)  # type: ignore
            assert model is not None


# ======================== RUN TESTS ========================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
