from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.runtime import AttentionPolicy, ContextState, CognitivePhase


def test_context_state_defaults_and_blocks() -> None:
    st = ContextState(token_budget=128)
    assert st.current_phase == "idle"
    assert st.cognitive_phase == CognitivePhase.IDLE
    assert st.active_policy == AttentionPolicy.BALANCED
    assert st.token_budget == 128
    b = ContextBlock("hi", ContextRole.USER, ContextSource.USER_INPUT)
    st.active_blocks.append(b)
    assert len(st.active_blocks) == 1
