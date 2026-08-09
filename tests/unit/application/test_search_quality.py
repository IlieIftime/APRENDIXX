from aprendix.application.search_quality import GOLDEN_QUERIES


def test_search_benchmark_covers_fifty_cross_domain_queries():
    assert len(GOLDEN_QUERIES) == 50
    assert len({item.query for item in GOLDEN_QUERIES}) == 50
    slugs = {slug for item in GOLDEN_QUERIES for slug in item.relevant_slugs}
    assert {
        "modulo-paridade", "binary-search", "transaction-atomic", "semantic-html",
        "chain-rule", "neuron", "agent-loop", "medical-metrics",
    }.issubset(slugs)
