import subprocess
import sys
import types
from unittest.mock import Mock

import pytest

from app.services import embeddings


def test_importing_embeddings_does_not_import_sentence_transformers():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import app.services.embeddings; "
                "assert 'sentence_transformers' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_embedding_model_is_loaded_once_on_first_use(monkeypatch):
    model = Mock()
    model.encode.side_effect = [
        types.SimpleNamespace(tolist=lambda: [0.1, 0.2]),
        types.SimpleNamespace(tolist=lambda: [[0.3, 0.4], [0.5, 0.6]]),
    ]
    constructor = Mock(return_value=model)
    fake_sentence_transformers = types.ModuleType("sentence_transformers")
    fake_sentence_transformers.SentenceTransformer = constructor

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        fake_sentence_transformers,
    )
    embeddings._get_model.cache_clear()

    try:
        assert embeddings.generate_embedding("query") == [0.1, 0.2]
        assert embeddings.generate_embeddings(["first", "second"]) == [
            [0.3, 0.4],
            [0.5, 0.6],
        ]

        constructor.assert_called_once_with(embeddings.MODEL_NAME)
        assert model.encode.call_count == 2
        model.encode.assert_any_call("query")
        model.encode.assert_any_call(
            ["first", "second"],
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
    finally:
        embeddings._get_model.cache_clear()


def test_empty_batch_does_not_load_embedding_model(monkeypatch):
    loader = Mock(side_effect=AssertionError("model should remain unloaded"))
    monkeypatch.setattr(embeddings, "_get_model", loader)

    assert embeddings.generate_embeddings([]) == []
    loader.assert_not_called()
