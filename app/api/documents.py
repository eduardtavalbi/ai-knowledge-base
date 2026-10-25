from app.services.embeddings import generate_embedding
from app.services.search import search_documents
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File



from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from google.genai.errors import ServerError, ClientError

from app.db.session import get_db
from app.models.document import  Document
from app.models.document_chunk import DocumentChunk
from app.schemas.document import (DocumentCreate, DocumentResponse,
                                  DocumentUpdate, SearchResultResponse,
                                  ChunkSearchResult, AskRequest, AskResponse)
from app.services.chunk_storage import save_document_chunks
from app.services.llm import generate_answer
from app.services.search import search_document_chunks

router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)

@router.get("/", response_model=list[DocumentResponse])
async def get_documents(
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Document)
    )

    documents = result.scalars().all()

    return documents

@router.get("/search", response_model=list[SearchResultResponse])
async def search_documents_endpoint(
    q: str,
    db: AsyncSession = Depends(get_db),
    limit: int = 5,
):
    if not q.strip():
        raise HTTPException(
            status_code=400,
            detail="Search query cannot be empty",
        )

    if limit < 1 or limit > 20:
        raise HTTPException(
            status_code=400,
            detail="Limit must be between 1 and 20",
        )

    documents = await search_documents(
        query=q,
        db=db,
        limit=limit,
    )

    return documents


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_documents(
    document_id: int,
    db: AsyncSession = Depends(get_db)
):
    document = await db.get(Document, document_id)

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    return document


@router.delete("/{document_id}")
async def delete_documents(
    document_id: int,
    db: AsyncSession = Depends(get_db)
):
    document = await db.get(Document, document_id)

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found"
        )

    await db.delete(document)
    await db.commit()

    return {"message":"Document deleted successfully"}



@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: int,
    document_data: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
):
    document = await db.get(Document, document_id)

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    document.title = document_data.title
    document.content = document_data.content
    document.embedding = generate_embedding(document_data.content)

    await db.execute(
        delete(DocumentChunk).where(
            DocumentChunk.document_id == document_id
        )
    )

    await db.flush()
    await save_document_chunks(document, db)

    await db.commit()
    await db.refresh(document)

    return document




@router.post("/upload", response_model=DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is reqiered"
        )

    if not file.filename.lower().endswith((".txt",".md")):
        raise HTTPException(
            status_code=400,
            detail="Only .txt and .md files are supported"
        )
    max_size = 2 * 1024 * 1024
    content_bytes = await file.read(max_size + 1)

    if len(content_bytes) > max_size:
        raise HTTPException(
            status_code=413,
            detail="File is too large. Maximum size is 2 MB",
        )


    try:
        content = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="File must use UTF-8 encoding"
        )

    if not content.strip():
        raise HTTPException(
            status_code=400,
            detail="File cannot be empty"
        )

    new_document = Document(
        title = file.filename,
        content = content,
        embedding=generate_embedding(content)
    )

    db.add(new_document)
    await db.flush()

    await save_document_chunks(new_document, db)

    await db.commit()
    await db.refresh(new_document)

    return new_document

@router.post("/", response_model=DocumentResponse, status_code=201)
async def create_document(
    document: DocumentCreate,
    db: AsyncSession = Depends(get_db),
):
    new_document = Document(
        title=document.title,
        content=document.content,
        embedding=generate_embedding(document.content),
    )

    db.add(new_document)
    await db.flush()

    await save_document_chunks(new_document, db)

    await db.commit()
    await db.refresh(new_document)

    return new_document


@router.get("/search/chunks", response_model=list[ChunkSearchResult])
async def search_document_chunks_endpoint(
    q: str,
    db: AsyncSession = Depends(get_db),
    limit: int = 5,
):
    if not q.strip():
        raise HTTPException(
            status_code=400,
            detail="Search query cannot be empty",
        )

    if limit < 1 or limit > 20:
        raise HTTPException(
            status_code=400,
            detail="Limit must be between 1 and 20",
        )

    return await search_document_chunks(
        query=q,
        db=db,
        limit=limit,
    )

@router.post("/ask", response_model=AskResponse)
async def ask_question(
    request: AskRequest,
    db: AsyncSession = Depends(get_db),
):
    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty",
        )

    chunks = await search_document_chunks(
        query=question,
        db=db,
        limit=request.limit,
    )

    if not chunks:
        return AskResponse(
            answer="В базе знаний не найдено достаточно релевантной информации для ответа.",
            sources=[],
        )

    context = "\n\n".join(
        f"Документ: {chunk['title']}\n"
        f"Фрагмент: {chunk['content']}"
        for chunk in chunks
    )

    
    try:
        answer = await generate_answer(
            question=question,
            context=context,
        )
    except ClientError as exc:
        if exc.code == 429:
            raise HTTPException(
                status_code=429,
                detail=(
                    "Исчерпан лимит запросов Gemini API. "
                    "Попробуйте после восстановления квоты."
                ),
            ) from exc

        raise HTTPException(
            status_code=502,
            detail="AI service rejected the request.",
        ) from exc

    except ServerError as exc:
        print(f"Gemini ServerError: {exc!r}")
        raise HTTPException(
            status_code=503,
            detail="AI service is temporarily unavailable. Please try again later.",
        ) from exc

    return AskResponse(
        answer=answer,
        sources=chunks,
    )