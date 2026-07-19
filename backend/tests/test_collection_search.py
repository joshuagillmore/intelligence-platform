from unittest.mock import patch
from intel_platform.collection.search import web_search


def test_web_search_returns_results():
    mock_results = [
        {"href": "https://example.com/1", "title": "Result 1", "body": "Snippet 1"},
        {"href": "https://example.com/2", "title": "Result 2", "body": "Snippet 2"},
    ]
    with patch("intel_platform.collection.search.DDGS") as MockDDGS:
        instance = MockDDGS.return_value.__enter__.return_value
        instance.text.return_value = mock_results
        results = web_search("test query", max_results=5)

    assert len(results) == 2
    assert results[0]["url"] == "https://example.com/1"
    assert results[0]["title"] == "Result 1"
    assert results[0]["snippet"] == "Snippet 1"


def test_web_search_max_results_clamped():
    with patch("intel_platform.collection.search.DDGS") as MockDDGS:
        instance = MockDDGS.return_value.__enter__.return_value
        instance.text.return_value = []
        web_search("test", max_results=50)
        instance.text.assert_called_once()
        call_kwargs = instance.text.call_args
        assert call_kwargs[1].get("max_results", call_kwargs[0][1] if len(call_kwargs[0]) > 1 else 20) <= 20


def test_web_search_handles_exception():
    with patch("intel_platform.collection.search.DDGS") as MockDDGS:
        instance = MockDDGS.return_value.__enter__.return_value
        instance.text.side_effect = Exception("Network error")
        results = web_search("test query")

    assert results == []
