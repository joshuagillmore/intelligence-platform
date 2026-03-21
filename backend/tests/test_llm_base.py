from intel_platform.llm.base import LLMProvider, LLMResponse


def test_llm_response_model():
    r = LLMResponse(content="Hello", model="test", input_tokens=10, output_tokens=5)
    assert r.total_tokens == 15


def test_llm_provider_is_abstract():
    try:
        LLMProvider()
        assert False, "Should not instantiate abstract class"
    except TypeError:
        pass
