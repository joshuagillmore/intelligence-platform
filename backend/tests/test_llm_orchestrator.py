import pytest
from intel_platform.llm.orchestrator import LLMOrchestrator
from intel_platform.llm.base import LLMProvider, LLMResponse


class MockProvider(LLMProvider):
    def __init__(self, response_text="Mock response"):
        self._response_text = response_text
    async def generate(self, messages, system="", temperature=0.3, max_tokens=4096):
        return LLMResponse(content=self._response_text, model="mock", input_tokens=10, output_tokens=5)
    async def stream(self, messages, system="", temperature=0.3, max_tokens=4096):
        for word in self._response_text.split():
            yield word + " "
    def name(self):
        return "mock"


@pytest.mark.asyncio
async def test_orchestrator_generate():
    orch = LLMOrchestrator(default_provider=MockProvider("Test output"))
    result = await orch.generate(messages=[{"role": "user", "content": "Hello"}])
    assert result.content == "Test output"


@pytest.mark.asyncio
async def test_orchestrator_tracks_usage():
    orch = LLMOrchestrator(default_provider=MockProvider())
    await orch.generate(messages=[{"role": "user", "content": "Hello"}])
    assert orch.total_tokens_used > 0


@pytest.mark.asyncio
async def test_orchestrator_with_skill():
    orch = LLMOrchestrator(default_provider=MockProvider())
    result = await orch.generate(messages=[{"role": "user", "content": "Assess this entity"}], skill_name="threat_assessment")
    assert result.content == "Mock response"


@pytest.mark.asyncio
async def test_orchestrator_token_budget():
    orch = LLMOrchestrator(default_provider=MockProvider(), token_budget=20)
    await orch.generate(messages=[{"role": "user", "content": "Hello"}])
    await orch.generate(messages=[{"role": "user", "content": "Hello"}])
    assert orch.total_tokens_used == 30


def test_orchestrator_register_provider():
    orch = LLMOrchestrator(default_provider=MockProvider())
    orch.register_provider("custom", MockProvider("Custom"))
    assert "custom" in orch.providers
