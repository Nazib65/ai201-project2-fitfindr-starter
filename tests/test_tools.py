from tools import search_listings, create_fit_card

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0

def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []

def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)

def test_fit_card_empty_outfit():
    # Empty outfit must return an error-message string, not crash, not empty.
    result = create_fit_card("", {"title": "x", "price": 10, "platform": "depop"})
    assert isinstance(result, str)
    assert result != ""
