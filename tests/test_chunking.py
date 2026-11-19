import pytest

from app.services.chunking import split_text


def test_empty_text_returns_empty_list():
    assert split_text("   \n\t ") == []


def test_short_text_returns_one_chunk():
    assert split_text("Hello world") == ["Hello world"]


def test_long_text_is_split_with_overlap():
    text = "a" * 1200

    chunks = split_text(text, chunk_size=500, overlap=100)

    assert [len(chunk) for chunk in chunks] == [500, 500, 400]
    assert chunks[0][-100:] == chunks[1][:100]
    assert chunks[1][-100:] == chunks[2][:100]


def test_single_line_whitespace_is_normalized():
    assert split_text("Hello\nworld\t!") == ["Hello world !"]


def test_paragraph_boundaries_are_preserved_when_possible():
    text = "## Heading\nA short paragraph.\n\nSecond paragraph."

    chunks = split_text(text, chunk_size=100, overlap=10)

    assert chunks == ["## Heading A short paragraph.\n\nSecond paragraph."]


def test_paragraphs_are_split_into_bounded_chunks_with_overlap():
    first = "First paragraph. " * 5
    second = "Second paragraph. " * 5

    chunks = split_text(f"{first}\n\n{second}", chunk_size=100, overlap=20)

    assert all(len(chunk) <= 100 for chunk in chunks)
    assert len(chunks) >= 2
    assert "First paragraph." in chunks[0]
    assert "Second paragraph." in chunks[-1]


def test_oversized_paragraph_preserves_all_text_and_overlap():
    text = "0123456789" * 120

    chunks = split_text(text, chunk_size=500, overlap=100)

    assert [len(chunk) for chunk in chunks] == [500, 500, 400]
    assert chunks[0][-100:] == chunks[1][:100]
    assert chunks[1][-100:] == chunks[2][:100]


@pytest.mark.parametrize(
    ("chunk_size", "overlap"),
    [
        (0, 0),
        (-1, 0),
        (100, -1),
        (100, 100),
        (100, 101),
    ],
)
def test_invalid_parameters_raise_value_error(chunk_size, overlap):
    with pytest.raises(ValueError):
        split_text("some text", chunk_size, overlap)


def test_long_text_chunks_cover_entire_text():
    text = "0123456789" * 120
    chunks = split_text(text, chunk_size=500, overlap=100)

    assert chunks[0] == text[:500]
    assert chunks[1] == text[400:900]
    assert chunks[-1] == text[-400:]
