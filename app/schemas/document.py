from pydantic import BaseModel, Field, field_validator


MAX_DOCUMENT_CONTENT_BYTES = 2 * 1024 * 1024


class DocumentContentInput(BaseModel):
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def validate_content_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_DOCUMENT_CONTENT_BYTES:
            raise ValueError("Document content must not exceed 2 MB")
        return value


class DocumentCreate(DocumentContentInput):
    title: str = Field(min_length=1, max_length=255)


class DocumentResponse(BaseModel):
    id: int
    title: str
    content: str


class SearchResultResponse(BaseModel):
    id: int
    title: str
    content: str
    score: float


class DocumentUpdate(DocumentContentInput):
    title: str = Field(min_length=1, max_length=255)


class ChunkSearchResult(BaseModel):
    document_id: int
    title: str
    chunk_id: int
    chunk_index: int
    content: str
    source_page: int | None = None
    source_section: str | None = None
    score: float


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)


class AskResponse(BaseModel):
    answer: str
    sources: list[ChunkSearchResult]
