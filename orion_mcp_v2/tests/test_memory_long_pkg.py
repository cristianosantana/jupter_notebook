def test_memory_long_package_importable():
    import orion_mcp_v2.memory_long as ml

    assert "Memória longa" in (ml.__doc__ or "")
