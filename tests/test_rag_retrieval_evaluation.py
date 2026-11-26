import pytest
from sqlalchemy.orm import configure_mappers

from scripts.evaluate_rag_retrieval import (
    calculate_no_answer_metrics,
    calculate_ranking_metrics,
    load_dataset,
)


def test_bilingual_retrieval_dataset_has_valid_ground_truth():
    dataset = load_dataset()

    assert len(dataset["documents"]) == 14
    assert len(dataset["queries"]) == 17
    assert {query["language"] for query in dataset["queries"]} == {"ru", "en"}
    assert sum(query.get("answerable", True) for query in dataset["queries"]) == 14
    assert sum(not query.get("answerable", True) for query in dataset["queries"]) == 3
    titles = {document["title"] for document in dataset["documents"]}
    assert all(
        set(query.get("expected_titles", [])) <= titles
        for query in dataset["queries"]
    )


def test_evaluation_import_registers_all_orm_relationship_models():
    # The benchmark constructs a User directly; all string-based SQLAlchemy
    # relationships must be registered before mapper configuration occurs.
    configure_mappers()


def test_no_answer_metrics_report_context_retrieval_rate():
    metrics = calculate_no_answer_metrics([False, True, False])

    assert metrics == {
        "no_answer_queries": 3,
        "no_answer_retrievals": 1,
        "no_answer_retrieval_rate_at_5": 0.3333,
    }


def test_no_answer_metrics_handle_empty_no_answer_set():
    assert calculate_no_answer_metrics([]) == {
        "no_answer_queries": 0,
        "no_answer_retrievals": 0,
        "no_answer_retrieval_rate_at_5": None,
    }


def test_ranking_metrics_calculate_recall_and_mrr_at_k():
    metrics = calculate_ranking_metrics([1, 2, None, 5, 7], k=5)

    assert metrics == {
        "queries": 5,
        "recall_at_5": 0.6,
        "mrr_at_5": 0.34,
        "misses": 2,
    }


@pytest.mark.parametrize(
    "ranks,k",
    [
        ([], 5),
        ([1, 2], 0),
    ],
)
def test_ranking_metrics_reject_invalid_input(ranks, k):
    with pytest.raises(ValueError):
        calculate_ranking_metrics(ranks, k=k)
