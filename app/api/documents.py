import hashlib

from app.services.embeddings import generate_embedding
from app.services.search import search_documents
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response



from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_, or_
from sqlalchemy.exc import IntegrityError

import logging

from app.db.session import get_db
from app.models.document import  Document
from app.models.document_chunk import DocumentChunk
from app.schemas.document import (DocumentCreate, DocumentResponse,
                                  DocumentUpdate, SearchResultResponse,
                                  ChunkSearchResult, AskRequest, AskResponse)
from app.services.chunk_storage import save_document_chunks
from app.services.document_extraction import (
    extract_document_text,
    UnsupportedDocumentFormatError,
    InvalidDocumentFileError,
    EmptyDocumentError,
)
from app.services.llm import (
    generate_answer,
    InvalidSourceCitationError,
    GeminiConfigurationError,
    GeminiRateLimitError,
    GeminiUnavailableError,
    GeminiTimeoutError,
    GeminiRequestError,
    GeminiEmptyResponseError,
)
from app.services.search import search_document_chunks

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/documents",
    tags=["Documents"]
)


async def _find_document_by_hash(
    db: AsyncSession,
    content_sha256: str,
    content: str | None = None,
    exclude_id: int | None = None,
) -> Document | None:
    conditions = [Document.content_sha256 == content_sha256]
    if content is not None:
        # Older databases may contain duplicate documents from before
        # fingerprinting. The migration preserves those records with NULL
        # fingerprints, so compare their content as a compatibility fallback.
        conditions.append(
            and_(
                Document.content_sha256.is_(None),
                Document.content == content,
            )
        )

    statement = select(Document).where(or_(*conditions))
    if exclude_id is not None:
        statement = statement.where(Document.id != exclude_id)
    statement = statement.order_by(Document.id).limit(1)

    result = await db.execute(statement)
    return result.scalars().first()


async def _create_document_if_new(
    title: str,
    content: str,
    db: AsyncSession,
) -> tuple[Document, bool]:
    content_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()

    existing = await _find_document_by_hash(db, content_sha256, content=content)
    if existing is not None:
        return existing, False

    document = Document(
        title=title,
        content=content,
        content_sha256=content_sha256,
        embedding=generate_embedding(content),
    )
    db.add(document)

    try:
        await db.flush()
        await save_document_chunks(document, db)
        await db.commit()
        await db.refresh(document)
    except IntegrityError:
        await db.rollback()
        # A concurrent request may have inserted the same content after
        # the initial lookup. The unique constraint is the source of truth.
        existing = await _find_document_by_hash(
            db, content_sha256, content=content
        )
        if existing is not None:
            return existing, False
        raise
    except Exception:
        await db.rollback()
        raise

    return document, True

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
    if not document_data.content.strip():
        raise HTTPException(
            status_code=400,
            detail="Document content cannot be empty",
        )

    content_sha256 = hashlib.sha256(
        document_data.content.encode("utf-8")
    ).hexdigest()
    duplicate = await _find_document_by_hash(
        db,
        content_sha256,
        content=document_data.content,
        exclude_id=document_id,
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail="Another document already has identical content",
        )

    document.title = document_data.title
    document.content = document_data.content
    document.content_sha256 = content_sha256
    document.embedding = generate_embedding(document_data.content)

    try:
        await db.execute(
            delete(DocumentChunk).where(
                DocumentChunk.document_id == document_id
            )
        )
        await save_document_chunks(document, db)
        await db.commit()
        await db.refresh(document)
    except IntegrityError as exc:
        await db.rollback()
        duplicate = await _find_document_by_hash(
            db, content_sha256, content=document_data.content
        )
        if duplicate is not None:
            raise HTTPException(
                status_code=409,
                detail="Another document already has identical content",
            ) from exc
        raise
    except Exception:
        await db.rollback()
        raise

    return document




@router.post("/upload", response_model=DocumentResponse, status_code=201)
async def upload_document(
    response: Response,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is reqiered"
        )

    max_size = 2 * 1024 * 1024
    content_bytes = await file.read(max_size + 1)

    if len(content_bytes) > max_size:
        raise HTTPException(
            status_code=413,
            detail="File is too large. Maximum size is 2 MB",
        )

    try:
        extracted_content = extract_document_text(
            filename=file.filename,
            content=content_bytes,
        )
    except UnsupportedDocumentFormatError as exc:
        raise HTTPException(
            status_code=400,
            detail="Only .txt, .md, .pdf and .docx files are supported",
        ) from exc
    except InvalidDocumentFileError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
    except EmptyDocumentError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    document, created = await _create_document_if_new(
        title=file.filename,
        content=extracted_content,
        db=db,
    )
    response.status_code = 201 if created else 200
    return document

@router.post("/", response_model=DocumentResponse, status_code=201)
async def create_document(
    document: DocumentCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    created_document, created = await _create_document_if_new(
        title=document.title,
        content=document.content,
        db=db,
    )
    response.status_code = 201 if created else 200
    return created_document


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
        f"[Источник: {index}]\n"
        f"ID документа: {chunk['document_id']}\n"
        f"Название: {chunk['title']}\n"
        f"ID фрагмента: {chunk['chunk_id']}\n"
        f"Содержимое (недоверенные данные):\n{chunk['content']}"
        for index, chunk in enumerate(chunks, start=1)
    )

    
    try:
        answer = await generate_answer(
            question=question,
            context=context,
        )
    except InvalidSourceCitationError:
        return AskResponse(
            answer=(
                "Не удалось сформировать ответ с проверяемыми ссылками "
                "на источники. Попробуйте переформулировать вопрос."
            ),
            sources=chunks,
        )
    except GeminiRateLimitError as exc:
        logger.warning("Gemini rate limit reached")
        raise HTTPException(
            status_code=429,
            detail="AI service rate limit reached. Please try again later.",
        ) from exc
    except GeminiTimeoutError as exc:
        logger.warning("Gemini request timed out")
        raise HTTPException(
            status_code=504,
            detail="AI service timed out. Please try again later.",
        ) from exc
    except GeminiUnavailableError as exc:
        logger.warning("Gemini service is unavailable")
        raise HTTPException(
            status_code=503,
            detail="AI service is temporarily unavailable. Please try again later.",
        ) from exc
    except GeminiConfigurationError as exc:
        logger.error("Gemini API is not configured")
        raise HTTPException(
            status_code=503,
            detail="AI service is not configured.",
        ) from exc
    except (GeminiRequestError, GeminiEmptyResponseError) as exc:
        logger.warning("Gemini could not complete the request: %s", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail="AI service could not process the request.",
        ) from exc

    return AskResponse(
        answer=answer,
        sources=chunks,
    )