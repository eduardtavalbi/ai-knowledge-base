import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useEffect, useRef, useState } from 'react'
import {
  BrainCircuit,
  Search,
  Plus,
  FileText,
  Upload,
  Sparkles,
  Database,
  ChevronRight,
  Clock3,
  X,
  LoaderCircle,
  Trash2,
} from 'lucide-react'
import './App.css'
const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

type DocumentItem = {
  id: number
  title: string
  content: string
}

type AskSource = {
  document_id: number
  title: string
  content: string
  score: number
  chunk_id: number
  chunk_index: number
  source_page?: number | null
  source_section?: string | null
}

type AskResponse = {
  answer: string
  sources: AskSource[]
}

function App() {
  const [query, setQuery] = useState('')
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [documentsLoading, setDocumentsLoading] = useState(true)
  const [results, setResults] = useState<DocumentItem[]>([])
  const [hasSearched, setHasSearched] = useState(false)
  const [apiStatus, setApiStatus] = useState<'checking' | 'online' | 'offline'>('checking')
  const [activePage, setActivePage] = useState<'search' | 'documents'>('search')
  const [selectedDocument, setSelectedDocument] = useState<DocumentItem | null>(null)
  const [selectedDocumentLoading, setSelectedDocumentLoading] = useState(false)
  const [selectedDocumentError, setSelectedDocumentError] = useState('')
  const [editingDocument, setEditingDocument] = useState<DocumentItem | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editContent, setEditContent] = useState('')
  const [savingEdit, setSavingEdit] = useState(false)
  const [deletingDocumentId, setDeletingDocumentId] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)
  const searchRequestId = useRef(0)
  const selectedDocumentRequestId = useRef(0)
  const [aiAnswer, setAiAnswer] = useState('')
  const [answerSources, setAnswerSources] = useState<AskSource[]>([])

  useEffect(() => {
    void loadDocuments()
  }, [])

  useEffect(() => {
    if (!editingDocument && !selectedDocument) return

    function handleModalKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Escape') return

      if (editingDocument) {
        if (!savingEdit) setEditingDocument(null)
      } else {
        closeSelectedDocument()
      }
    }

    window.addEventListener('keydown', handleModalKeyDown)
    return () => window.removeEventListener('keydown', handleModalKeyDown)
  }, [editingDocument, selectedDocument, savingEdit])

  useEffect(() => {
    if (!editingDocument && !selectedDocument) return

    const dialog = window.document.querySelector<HTMLElement>(
      '.modal-overlay [role="dialog"]',
    )
    if (!dialog) return

    const previouslyFocused = window.document.activeElement as HTMLElement | null
    const focusableSelector = [
      'a[href]',
      'button:not([disabled])',
      'input:not([disabled])',
      'textarea:not([disabled])',
      'select:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
    ].join(', ')
    const getFocusableElements = () =>
      Array.from(dialog.querySelectorAll<HTMLElement>(focusableSelector))
        .filter((element) => element.getAttribute('aria-hidden') !== 'true')

    const focusableElements = getFocusableElements()
    const initialFocus = editingDocument
      ? dialog.querySelector<HTMLElement>('#edit-title')
      : focusableElements[0]
    ;(initialFocus ?? dialog).focus()

    function trapDialogFocus(event: KeyboardEvent) {
      if (event.key !== 'Tab') return

      const elements = getFocusableElements()
      if (elements.length === 0) {
        event.preventDefault()
        dialog!.focus()
        return
      }

      const first = elements[0]
      const last = elements[elements.length - 1]
      const activeElement = window.document.activeElement

      // Keep keyboard focus inside the modal even if another script or
      // browser interaction moved it outside the dialog.
      if (!dialog!.contains(activeElement)) {
        event.preventDefault()
        ;(event.shiftKey ? last : first).focus()
        return
      }

      if (event.shiftKey && activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    window.document.addEventListener('keydown', trapDialogFocus)
    return () => {
      window.document.removeEventListener('keydown', trapDialogFocus)
      if (previouslyFocused?.isConnected) previouslyFocused.focus()
    }
  }, [editingDocument, selectedDocument])

  function closeSelectedDocument() {
    selectedDocumentRequestId.current += 1
    setSelectedDocument(null)
    setSelectedDocumentLoading(false)
    setSelectedDocumentError('')
  }

  async function openDocument(document: DocumentItem) {
    const requestId = ++selectedDocumentRequestId.current
    setSelectedDocument(document)
    setSelectedDocumentLoading(true)
    setSelectedDocumentError('')

    try {
      const response = await requestApi(`${API_URL}/documents/${document.id}`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const fullDocument: DocumentItem = await response.json()
      if (requestId === selectedDocumentRequestId.current) {
        setSelectedDocument(fullDocument)
      }
    } catch (error) {
      if (requestId === selectedDocumentRequestId.current) {
        setSelectedDocumentError(
          error instanceof Error
            ? `Не удалось загрузить документ: ${error.message}`
            : 'Не удалось загрузить полный документ.',
        )
      }
    } finally {
      if (requestId === selectedDocumentRequestId.current) {
        setSelectedDocumentLoading(false)
      }
    }
  }

  async function requestApi(
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> {
    try {
      const response = await fetch(input, init)
      // An HTTP error still proves that the API is reachable; only a failed
      // network request should switch the connection indicator to offline.
      setApiStatus('online')
      return response
    } catch (error) {
      setApiStatus('offline')
      throw error
    }
  }

  async function loadDocuments() {
    setDocumentsLoading(true)
    try {
      const response = await requestApi(`${API_URL}/documents/`)

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data: DocumentItem[] = await response.json()
      setDocuments(data)
      setApiStatus('online')
    } catch (error) {
      console.error('Ошибка загрузки документов:', error)
      setMessage(
        error instanceof Error && error.message.startsWith('HTTP ')
          ? 'API доступен, но не удалось загрузить список документов.'
          : 'Не удалось загрузить список документов. Проверь подключение к API.',
      )
    } finally {
      setDocumentsLoading(false)
    }
  }

  async function searchDocuments(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!query.trim()) {
      setMessage('Введи вопрос для поиска.')
      return
    }

    const requestId = ++searchRequestId.current
    setLoading(true)
    setHasSearched(true)
    setMessage('')
    setAiAnswer('')
    setAnswerSources([])
    setResults([])

    try {
      const response = await requestApi(`${API_URL}/documents/ask`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question: query.trim(),
        }),
      })

      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`HTTP ${response.status}: ${errorText}`)
      }

      const data: AskResponse = await response.json()
      if (requestId !== searchRequestId.current) return

      setApiStatus('online')
      setAiAnswer(data.answer)
      setAnswerSources(data.sources ?? [])

      setResults(
        (data.sources ?? []).map((source) => ({
          id: source.document_id,
          title: source.title,
          content: source.content,
        })),
      )

      if (!data.answer && !data.sources?.length) {
        setMessage('Не удалось найти информацию по этому вопросу.')
      }
    } catch (error) {
      if (requestId !== searchRequestId.current) return
      console.error('Ошибка запроса к ИИ:', error)
      setMessage(
        error instanceof Error
          ? `Ошибка: ${error.message}`
          : 'Не удалось получить ответ от ИИ.',
      )
    } finally {
      if (requestId === searchRequestId.current) setLoading(false)
    }
  }
  async function uploadFile(event: React.ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget
    const file = input.files?.[0]
    if (!file) return

    const allowedExtensions = ['.pdf', '.docx', '.txt', '.md']
    const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
    const maxFileSize = 2 * 1024 * 1024

    if (!allowedExtensions.includes(extension)) {
      setMessage('Неподдерживаемый формат. Выбери PDF, DOCX, TXT или MD.')
      input.value = ''
      return
    }

    if (file.size > maxFileSize) {
      setMessage('Файл слишком большой. Максимальный размер — 2 МБ.')
      input.value = ''
      return
    }

    const formData = new FormData()
    formData.append('file', file)
    setUploading(true)
    setMessage('')

    try {
      const response = await requestApi(`${API_URL}/documents/upload`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => null)
        throw new Error(
          errorData?.detail || `Не удалось загрузить документ (HTTP ${response.status})`,
        )
      }

      const document: DocumentItem = await response.json()
      setDocuments((current) => {
        const alreadyListed = current.some((item) => item.id === document.id)
        return alreadyListed
          ? current.map((item) => item.id === document.id ? document : item)
          : [document, ...current]
      })
      setMessage(
        response.status === 200
          ? `Документ «${document.title}» уже есть в базе знаний.`
          : `Документ «${document.title}» загружен.`,
      )
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : 'Не удалось загрузить документ. Проверь подключение к API.',
      )
    } finally {
      setUploading(false)
      input.value = ''
    }
  }
  async function deleteDocument(document: DocumentItem) {
  if (deletingDocumentId !== null) return

  const confirmed = window.confirm(
    `Удалить документ «${document.title}»?`,
  )

  if (!confirmed) return

  searchRequestId.current += 1
  setLoading(false)
  setDeletingDocumentId(document.id)
  setMessage('')

  try {
    const response = await requestApi(
      `${API_URL}/documents/${document.id}`,
      { method: 'DELETE' },
    )

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    setDocuments((current) =>
      current.filter((item) => item.id !== document.id),
    )

    setResults((current) =>
      current.filter((item) => item.id !== document.id),
    )
    if (answerSources.some((source) => source.document_id === document.id)) {
      setAiAnswer('')
      setAnswerSources([])
      setResults([])
      setHasSearched(false)
    }

    setSelectedDocument((current) =>
      current?.id === document.id ? null : current,
    )

    setMessage(`Документ «${document.title}» удалён.`)
  } catch (error) {
    console.error('Ошибка удаления:', error)
    setMessage('Не удалось удалить документ. Попробуй ещё раз.')
  } finally {
    setDeletingDocumentId(null)
  }
}
  async function updateDocument() {
    if (!editingDocument) return

    if (!editTitle.trim() || !editContent.trim()) {
      setMessage('Название и содержимое не должны быть пустыми.')
      return
    }

    setSavingEdit(true)

    try {
      const response = await requestApi(
        `${API_URL}/documents/${editingDocument.id}`,
        {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            title: editTitle.trim(),
            content: editContent.trim(),
          }),
        },
      )

      if (!response.ok) {
        const errorData = await response.json().catch(() => null)

        throw new Error(
          errorData?.detail || `Ошибка сервера: ${response.status}`,
        )
      }

      const updatedDocument: DocumentItem = await response.json()

      searchRequestId.current += 1
      setLoading(false)
      setDocuments((current) =>
        current.map((item) =>
          item.id === updatedDocument.id ? updatedDocument : item,
        ),
      )

      setResults((current) =>
        current.filter((item) => item.id !== updatedDocument.id),
      )
      setAiAnswer('')
      setAnswerSources([])
      setHasSearched(false)

      setSelectedDocument(updatedDocument)
      setEditingDocument(null)
      setMessage('Документ успешно обновлён.')
    } catch (error) {
      console.error('Ошибка обновления документа:', error)
      setMessage(
        error instanceof Error
          ? `Не удалось сохранить изменения: ${error.message}`
          : 'Не удалось сохранить изменения.',
      )
    } finally {
      setSavingEdit(false)
    }
  }
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#">
          <span className="brand-icon"><BrainCircuit size={25} /></span>
          <span>Mindbase<span className="brand-dot">.</span></span>
        </a>

        <div className="workspace-label">WORKSPACE</div>

        <button
          className={`nav-item ${activePage === 'search' ? 'active' : ''}`}
          onClick={() => setActivePage('search')}
        >
          <Search size={18} />
          <span>Семантический поиск</span>
        </button>
        <button
          className={`nav-item ${activePage === 'documents' ? 'active' : ''}`}
          onClick={() => {
            setActivePage('documents')
            void loadDocuments()
          }}
        >
          <Database size={18} />
          <span>Моя база знаний</span>
          <span className="nav-count">{documents.length}</span>
        </button>


        <div className="sidebar-bottom">
          <div className="status-card">
            <span className={`status-indicator ${apiStatus}`} />
            <div>
              <strong>API подключение</strong>
              <p>{apiStatus === 'checking' ? 'Проверка…' : apiStatus === 'online' ? 'Подключено' : 'Нет соединения'}</p>
            </div>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={15} /> <span>{activePage === 'search' ? 'Поиск' : 'Моя база знаний'}</span>
          </div>
          <div className="avatar">Э</div>
        </header>

        <section className="content-wrap">
          {activePage === 'documents' && (
            <section className="results-section">
              <div className="section-heading">
                <div>
                  <h2>Моя база знаний</h2>
                  <p>Все документы, сохранённые в базе данных</p>
                </div>
                <span className="result-count">
                  {documents.length} документов
                </span>
              </div>

              <div className="results-list">
                {documents.map((document) => (
                  <article className="result-card" key={document.id}>
                    <button
                      type="button"
                      className="result-open-button"
                      onClick={() => void openDocument(document)}
                      aria-label={`Открыть документ ${document.title}`}
                    >
                      <div className="document-icon">
                        <FileText size={21} />
                      </div>
                      <div className="result-info">
                        <h3>{document.title}</h3>
                        <p>{document.content}</p>
                        <div className="result-meta">
                          <span><Database size={13} /> Документ</span>
                          <span><Clock3 size={13} /> В базе знаний</span>
                        </div>
                      </div>
                    </button>
                    <button
                      className="edit-button"
                      title="Редактировать документ"
                      aria-label={`Редактировать ${document.title}`}
                      onClick={(event) => {
                        event.stopPropagation()
                        setEditingDocument(document)
                        setEditTitle(document.title)
                        setEditContent(document.content)
                        setMessage('')
                      }}
                    >
                      <FileText size={18} />
                    </button>
                    <button
                      className="delete-button"
                      title={
                        deletingDocumentId === document.id
                          ? 'Удаление...'
                          : 'Удалить документ'
                      }
                      aria-label={`Удалить ${document.title}`}
                      disabled={deletingDocumentId !== null}
                      onClick={(event) => {
                        event.stopPropagation()
                        void deleteDocument(document)
                      }}
                    >
                      {deletingDocumentId === document.id ? (
                        <LoaderCircle className="spin" size={18} />
                      ) : (
                        <Trash2 size={18} />
                      )}
                    </button>
                  </article>
                ))}

                {documentsLoading && (
                  <div className="empty-state" role="status">
                    <LoaderCircle className="spin" size={18} /> Загрузка документов…
                  </div>
                )}
                {!documentsLoading && documents.length === 0 && (
                  <div className="empty-state">
                    {apiStatus === 'offline'
                      ? 'Не удалось подключиться к серверу. Проверь API и повтори попытку.'
                      : 'Документы пока не загружены.'}
                  </div>
                )}
              </div>
            </section>
          )}
          {activePage === 'search' && (
          <div className="hero">
            <div className="eyebrow">
              <Sparkles size={15} /> AI-POWERED KNOWLEDGE
            </div>
            <h1>Найди нужное.<br /><span>Не просто слова.</span></h1>
            <p className="hero-description">
              Ищи информацию по смыслу среди своих документов.
              Задай вопрос обычным языком.
            </p>

            <form className="search-box" onSubmit={searchDocuments}>
              <Search size={21} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Например, как создать REST API на Python?"
                aria-label="Поисковый запрос"
              />
              {query && (
                <button
                  type="button"
                  className="clear-button"
                  onClick={() => setQuery('')}
                  aria-label="Очистить поиск"
                >
                  <X size={16} />
                </button>
              )}
              <button className="search-button" type="submit" disabled={loading}>
                {loading ? <LoaderCircle className="spin" size={17} /> : 'Найти'}
              </button>
            </form>

            <div className="search-hint">
              <span>Попробуй:</span>
              {['Python', 'API', 'тренировки'].map((term) => (
                <button key={term} onClick={() => setQuery(term)}>
                  {term}
                </button>
              ))}
            </div>
          </div>
          )}
          {activePage === 'search' && aiAnswer && (
            <section className="ai-answer-card">
              <div className="ai-answer-heading">
                <Sparkles size={20} />
                <h2>Ответ Mindbase AI</h2>
              </div>

              <div className="ai-answer-text">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {aiAnswer.replace(/\\([*`_[\]()#+.!>-])/g, '$1')}
                </ReactMarkdown>
              </div>

              {answerSources.length > 0 && (
                <div className="ai-sources">
                  <h3>Источники ответа</h3>

                  {answerSources.map((source) => (
                    <article
                      className="ai-source-card"
                      key={source.chunk_id}
                    >
                      <div className="ai-source-title">
                        <FileText size={16} />
                        <strong>{source.title}</strong>
                      </div>

                      <p>{source.content}</p>

                      <div className="ai-source-meta">
                        <span>Фрагмент документа</span>
                        {source.source_page != null && (
                          <span>Страница {source.source_page}</span>
                        )}
                        {source.source_section && (
                          <span>Раздел: {source.source_section}</span>
                        )}
                        <span>
                          Релевантность: {(source.score * 100).toFixed(1)}%
                        </span>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>
          )}
          {message && <div className="message-banner">{message}</div>}
          {activePage === 'search' && (
          <section className="results-section">
            <div className="section-heading">
              <div>
                <h2>Результаты поиска</h2>
                <p>Документы, которые могут быть полезны</p>
              </div>
              <span className="result-count">{results.length} документа</span>
            </div>

            <div className="results-list">
              {results.map((document) => (
                <article className="result-card" key={document.id}>
                  <button
                    type="button"
                    className="result-open-button"
                    onClick={() => setSelectedDocument(document)}
                    aria-label={`Открыть документ ${document.title}`}
                  >
                    <div className="document-icon"><FileText size={21} /></div>
                    <div className="result-info">
                      <h3>{document.title}</h3>
                      <p>{document.content}</p>
                      <div className="result-meta">
                        <span><Database size={13} /> Документ</span>
                        <span><Clock3 size={13} /> В базе знаний</span>
                      </div>
                    </div>
                    <ChevronRight className="result-arrow" size={19} />
                  </button>
                </article>
              ))}
              {!results.length && !message && (
                <div className="empty-state">
                  {hasSearched
                    ? 'По этому запросу документы не найдены.'
                    : 'Выполни поиск, чтобы увидеть результаты.'}
                </div>
              )}
            </div>
          </section>
          )}
          {activePage === 'search' && (
          <section className="upload-section">
            <div className="upload-copy">
              <div className="upload-icon"><Upload size={20} /></div>
              <div>
                <h3>Пополнить базу знаний</h3>
                <p>Поддерживаются PDF, DOCX, TXT и Markdown · до 2 МБ.</p>
              </div>
            </div>
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.docx,.txt,.md"
              hidden
              onChange={uploadFile}
            />
            <button
              className="upload-button"
              disabled={uploading}
              onClick={() => fileInput.current?.click()}
            >
              {uploading ? (
                <><LoaderCircle className="spin" size={17} /> Загрузка…</>
              ) : (
                <><Plus size={17} /> Добавить документ</>
              )}
            </button>
          </section>
          )}

          <footer className="footer">
            <span><span className={`status-indicator ${apiStatus}`} /> Mindbase workspace</span>
            <span>Built with FastAPI &amp; vector search</span>
          </footer>
        </section>
      </main>
      {editingDocument && (
        <div
          className="modal-overlay"
          onClick={() => {
            if (!savingEdit) setEditingDocument(null)
          }}
        >
          <section
            className="document-modal edit-modal"
            role="dialog"
            tabIndex={-1}
            aria-modal="true"
            aria-labelledby="edit-document-title"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              className="modal-close"
              onClick={() => setEditingDocument(null)}
              disabled={savingEdit}
              aria-label="Закрыть редактор"
            >
              <X size={20} />
            </button>

            <h2 id="edit-document-title">Редактирование документа</h2>

            <form
              className="edit-form"
              onSubmit={(event) => {
                event.preventDefault()
                void updateDocument()
              }}
            >
              <label htmlFor="edit-title">Название</label>
              <input
                id="edit-title"
                value={editTitle}
                onChange={(event) => setEditTitle(event.target.value)}
                required
              />

              <label htmlFor="edit-content">Содержимое</label>
              <textarea
                id="edit-content"
                value={editContent}
                onChange={(event) => setEditContent(event.target.value)}
                rows={10}
                required
              />

              <div className="edit-actions">
                <button
                  type="button"
                  className="edit-cancel"
                  onClick={() => setEditingDocument(null)}
                  disabled={savingEdit}
                >
                  Отмена
                </button>

                <button
                  type="submit"
                  className="upload-button"
                  disabled={savingEdit}
                >
                  {savingEdit ? 'Сохранение…' : 'Сохранить'}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
      {selectedDocument && (
        <div
          className="modal-overlay"
          onClick={closeSelectedDocument}
        >
          <section
            className="document-modal"
            role="dialog"
            tabIndex={-1}
            aria-modal="true"
            aria-labelledby="document-modal-title"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              className="modal-close"
              onClick={closeSelectedDocument}
              aria-label="Закрыть документ"
            >
              <X size={20} />
            </button>

            <div className="document-icon">
              <FileText size={24} />
            </div>

            <h2 id="document-modal-title">{selectedDocument.title}</h2>
            {selectedDocumentLoading ? (
              <p className="document-full-content" role="status">Загрузка полного документа…</p>
            ) : selectedDocumentError ? (
              <p className="document-full-content" role="alert">{selectedDocumentError}</p>
            ) : (
              <p className="document-full-content">{selectedDocument.content}</p>
            )}
          </section>
        </div>
      )}
    </div>
  )
}

export default App
