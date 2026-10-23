
import { useRef, useState } from 'react'
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
} from 'lucide-react'
import './App.css'

type DocumentItem = {
  id: number
  title: string
  content: string
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
  const [documents, setDocuments] = useState(demoDocuments)
  const [results, setResults] = useState<DocumentItem[]>(demoDocuments)
  const [selectedDocument, setSelectedDocument] = useState<DocumentItem | null>(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)

  
  async function searchDocuments(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (!query.trim()) {
      setMessage('Введи запрос для поиска.')
      return
    }

    setLoading(true)
    setMessage('')

    try {
      const response = await fetch(
        `http://localhost:8000/documents/search?q=${encodeURIComponent(query)}&limit=10`,
      )

      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`HTTP ${response.status}: ${errorText}`)
      }

      const data: DocumentItem[] = await response.json()
      setResults(data)
      setMessage(data.length ? '' : 'По твоему запросу ничего не найдено.')
    } catch (error) {
      console.error('Ошибка поиска:', error)
      setMessage(
        error instanceof Error
          ? `Ошибка поиска: ${error.message}`
          : 'Произошла неизвестная ошибка.',
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
      const response = await fetch('http://localhost:8000/documents/upload', {
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

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#">
          <span className="brand-icon"><BrainCircuit size={25} /></span>
          <span>Mindbase<span className="brand-dot">.</span></span>
        </a>

        <div className="workspace-label">WORKSPACE</div>

        <button className="nav-item active">
          <Search size={18} />
          <span>Семантический поиск</span>
        </button>
        <button className="nav-item">
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

          {message && <div className="message-banner">{message}</div>}

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

          <footer className="footer">
            <span><span className="status-indicator" /> Mindbase workspace</span>
            <span>Built with FastAPI &amp; vector search</span>
          </footer>
        </section>
      </main>
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
