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
  Settings,
  ChevronRight,
  Clock3,
  X,
  LoaderCircle,
  Trash2,
} from 'lucide-react'
import './App.css'

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
}

type AskResponse = {
  answer: string
  sources: AskSource[]
}

const demoDocuments: DocumentItem[] = [
  {
    id: 1,
    title: 'Изучение Python',
    content:
      'Python используется для разработки API, автоматизации задач и создания приложений.',
  },
  {
    id: 2,
    title: 'Python Learning Guide',
    content:
      'Python is a programming language used for backend development, automation, and artificial intelligence.',
  },
  {
    id: 3,
    title: 'План тренировок',
    content:
      'Регулярные силовые тренировки помогают развивать мышцы и увеличивать силу.',
  },
]

function App() {
  const [query, setQuery] = useState('')
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [results, setResults] = useState<DocumentItem[]>(demoDocuments)
  const [activePage, setActivePage] = useState<'search' | 'documents'>('search')
  const [selectedDocument, setSelectedDocument] = useState<DocumentItem | null>(null)
  const [editingDocument, setEditingDocument] = useState<DocumentItem | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editContent, setEditContent] = useState('')
  const [savingEdit, setSavingEdit] = useState(false)
  const [deletingDocumentId, setDeletingDocumentId] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)
  const [aiAnswer, setAiAnswer] = useState('')
  const [answerSources, setAnswerSources] = useState<AskSource[]>([])

  useEffect(() => {
    void loadDocuments()
  }, [])

  async function loadDocuments() {
    try {
      const response = await fetch('http://127.0.0.1:8000/documents/')

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data: DocumentItem[] = await response.json()
      setDocuments(data)
    } catch (error) {
      console.error('Ошибка загрузки документов:', error)
      setMessage('Не удалось загрузить список документов.')
    }
  }

  async function searchDocuments(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!query.trim()) {
      setMessage('Введи вопрос для поиска.')
      return
    }

    setLoading(true)
    setMessage('')
    setAiAnswer('')
    setAnswerSources([])
    setResults([])

    try {
      const response = await fetch('http://127.0.0.1:8000/documents/ask', {
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
      console.error('Ошибка запроса к ИИ:', error)
      setMessage(
        error instanceof Error
          ? `Ошибка: ${error.message}`
          : 'Не удалось получить ответ от ИИ.',
      )
    } finally {
      setLoading(false)
    }
  }
  async function uploadFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await fetch('http://127.0.0.1:8000/documents/upload', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        throw new Error('Не удалось загрузить документ')
      }

      const document: DocumentItem = await response.json()
      setDocuments((current) => [document, ...current])
      setMessage(`Документ «${document.title}» загружен.`)
    } catch {
      setMessage('Ошибка загрузки. Проверь API и формат файла.')
    } finally {
      event.target.value = ''
    }
  }
  async function deleteDocument(document: DocumentItem) {
  if (deletingDocumentId !== null) return

  const confirmed = window.confirm(
    `Удалить документ «${document.title}»?`,
  )

  if (!confirmed) return

  setDeletingDocumentId(document.id)
  setMessage('')

  try {
    const response = await fetch(
      `http://127.0.0.1:8000/documents/${document.id}`,
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
      const response = await fetch(
        `http://127.0.0.1:8000/${editingDocument.id}`,
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
        throw new Error(`HTTP ${response.status}`)
      }

      const updatedDocument: DocumentItem = await response.json()

      setDocuments((current) =>
        current.map((item) =>
          item.id === updatedDocument.id ? updatedDocument : item,
        ),
      )

      setResults((current) =>
        current.map((item) =>
          item.id === updatedDocument.id ? updatedDocument : item,
        ),
      )

      if (query.trim()) {
        try {
          const searchResponse = await fetch(
            `http://127.0.0.1:8000/documents/search?q=${encodeURIComponent(query)}&limit=10`,
          )

          if (searchResponse.ok) {
            const freshResults: DocumentItem[] = await searchResponse.json()
            setResults(freshResults)
          }
        } catch (error) {
          console.error('Ошибка обновления результатов поиска:', error)
        }
      }

      setSelectedDocument(updatedDocument)
      setEditingDocument(null)
      setMessage('Документ успешно обновлён.')
    } catch (error) {
      console.error('Ошибка обновления документа:', error)
      setMessage('Не удалось сохранить изменения.')
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

        <div className="sidebar-divider" />

        <div className="workspace-label">COLLECTIONS</div>
        <button className="nav-item">
          <FileText size={18} />
          <span>Все документы</span>
        </button>

        <div className="sidebar-bottom">
          <div className="status-card">
            <span className="status-indicator" />
            <div>
              <strong>API подключение</strong>
              <p>Локальный сервер</p>
            </div>
          </div>
          <button className="nav-item">
            <Settings size={18} />
            <span>Настройки</span>
          </button>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={15} /> <span>Поиск</span>
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
                  <article
                    className="result-card"
                    key={document.id}
                    onClick={() => setSelectedDocument(document)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        setSelectedDocument(document)
                      }
                    }}
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

                {documents.length === 0 && (
                  <div className="empty-state">
                    Документы пока не загружены.
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

                      <span>
                        Фрагмент документа · релевантность:{' '}
                        {(source.score * 100).toFixed(1)}%
                      </span>
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
                <article
                  className="result-card"
                  key={document.id}
                  onClick={() => setSelectedDocument(document)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      setSelectedDocument(document)
                    }
                  }}
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
                </article>
              ))}
              {!results.length && !message && (
                <div className="empty-state">Выполни поиск, чтобы увидеть результаты.</div>
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
                <p>Загрузи документ, чтобы он стал доступен для поиска.</p>
              </div>
            </div>
            <input
              ref={fileInput}
              type="file"
              accept=".txt,.md"
              hidden
              onChange={uploadFile}
            />
            <button
              className="upload-button"
              onClick={() => fileInput.current?.click()}
            >
              <Plus size={17} /> Добавить документ
            </button>
          </section>
          )}

          <footer className="footer">
            <span><span className="status-indicator" /> Mindbase workspace</span>
            <span>Built with FastAPI &amp; vector search</span>
          </footer>
        </section>
      </main>
      {editingDocument && (
        <div
          className="modal-overlay"
          onClick={() => setEditingDocument(null)}
        >
          <section
            className="document-modal edit-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="edit-document-title"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              className="modal-close"
              onClick={() => setEditingDocument(null)}
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
          onClick={() => setSelectedDocument(null)}
        >
          <section
            className="document-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="document-modal-title"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              className="modal-close"
              onClick={() => setSelectedDocument(null)}
              aria-label="Закрыть документ"
            >
              <X size={20} />
            </button>

            <div className="document-icon">
              <FileText size={24} />
            </div>

            <h2 id="document-modal-title">{selectedDocument.title}</h2>
            <p className="document-full-content">
              {selectedDocument.content}
            </p>
          </section>
        </div>
      )}
    </div>
  )
}

export default App
