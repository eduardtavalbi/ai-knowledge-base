from pydantic import BaseModel, Field

class DocumentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)

class DocumentResponse(BaseModel):
    id: int
    title: str
    content: str

class SearchResultResponse(BaseModel):
    id: int
    title: str
    content: str
    score: float

class DocumentUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)


class ChunkSearchResult(BaseModel):
    document_id: int
    title: str
    chunk_id: int
    chunk_index: int
    content: str
    score: float

class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)


class AskResponse(BaseModel):
    answer: str
    sources: list[ChunkSearchResult]