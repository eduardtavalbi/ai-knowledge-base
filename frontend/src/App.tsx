import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useCallback, useEffect, useRef, useState } from 'react'
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
  Download,
  AlertTriangle,
} from 'lucide-react'
import './App.css'
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Capture one-time action tokens, then remove them from the address bar before
// the app performs any network requests or loads user-triggered resources.
const initialAuthParams = new URLSearchParams(window.location.search)
const initialResetToken = initialAuthParams.get('reset') || ''
const initialVerificationToken = initialAuthParams.get('verify')
if (initialAuthParams.has('reset') || initialAuthParams.has('verify')) {
  initialAuthParams.delete('reset')
  initialAuthParams.delete('verify')
  const remainingQuery = initialAuthParams.toString()
  window.history.replaceState(
    {},
    '',
    `${window.location.pathname}${remainingQuery ? `?${remainingQuery}` : ''}${window.location.hash}`,
  )
}

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
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const [authMode, setAuthMode] = useState<'login' | 'register' | 'forgot' | 'reset'>(
    initialResetToken ? 'reset' : 'login',
  )
  const [authNotice, setAuthNotice] = useState('')
  const [resetToken, setResetToken] = useState(initialResetToken)
  const verificationToken = useRef(initialVerificationToken)
  const [authEmail, setAuthEmail] = useState('')
  const [authPassword, setAuthPassword] = useState('')
  const [authError, setAuthError] = useState('')
  const [authLoading, setAuthLoading] = useState(false)
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
  const [accountDeleteOpen, setAccountDeleteOpen] = useState(false)
  const [accountDeletePassword, setAccountDeletePassword] = useState('')
  const [accountDeleteConfirmation, setAccountDeleteConfirmation] = useState('')
  const [accountDeleting, setAccountDeleting] = useState(false)
  const [deletingDocumentId, setDeletingDocumentId] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)
  const searchRequestId = useRef(0)
  const apiRequestId = useRef(0)
  const documentsRequestId = useRef(0)
  const selectedDocumentRequestId = useRef(0)
  const selectedDocumentRequestDocumentId = useRef<number | null>(null)
  const [aiAnswer, setAiAnswer] = useState('')
  const [answerSources, setAnswerSources] = useState<AskSource[]>([])

  useEffect(() => {
    const token = verificationToken.current
    if (!token) return
    let active = true
    void fetch(`${API_URL}/auth/verify-email`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    }).then(async (response) => {
      if (!active) return
      if (response.ok) {
        setAuthNotice('Email подтверждён. Теперь можно войти в аккаунт.')
        setAuthMode('login')
      } else {
        const data = await response.json().catch(() => null)
        setAuthError(data?.detail || 'Ссылка подтверждения недействительна или устарела.')
      }
      window.history.replaceState({}, '', window.location.pathname)
    }).catch(() => {
      if (active) setAuthError('Не удалось подтвердить email. Проверь подключение к серверу.')
    })
    return () => { active = false }
  }, [])


  useEffect(() => {
    if (!editingDocument && !selectedDocument && !accountDeleteOpen) return

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
  }, [editingDocument, selectedDocument, accountDeleteOpen])

  const closeSelectedDocument = useCallback(() => {
    selectedDocumentRequestId.current += 1
    selectedDocumentRequestDocumentId.current = null
    setSelectedDocument(null)
    setSelectedDocumentLoading(false)
    setSelectedDocumentError('')
  }, [])


  useEffect(() => {
    if (!editingDocument && !selectedDocument && !accountDeleteOpen) return

    function handleModalKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Escape') return

      if (accountDeleteOpen) {
        if (!accountDeleting) setAccountDeleteOpen(false)
      } else if (editingDocument) {
        if (!savingEdit) setEditingDocument(null)
      } else {
        closeSelectedDocument()
      }
    }

    window.addEventListener('keydown', handleModalKeyDown)
    return () => window.removeEventListener('keydown', handleModalKeyDown)
  }, [editingDocument, selectedDocument, savingEdit, closeSelectedDocument, accountDeleteOpen, accountDeleting])

  async function openDocument(document: DocumentItem) {
    const requestId = ++selectedDocumentRequestId.current
    selectedDocumentRequestDocumentId.current = document.id
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

  const refreshPromise = useRef<Promise<string | null> | null>(null)

  const refreshAccessToken = useCallback((): Promise<string | null> => {
    // React StrictMode and parallel 401 responses can trigger refresh together.
    // Share one request so the same single-use refresh token is never raced.
    if (refreshPromise.current) return refreshPromise.current

    const pending = (async (): Promise<string | null> => {
      try {
        let response = await fetch(`${API_URL}/auth/refresh`, {
          method: 'POST',
          credentials: 'include',
        })
        // Another tab may have rotated the shared cookie just before this
        // request arrived. Retry once with the browser's newly stored cookie.
        if (response.status === 409) {
          await new Promise((resolve) => window.setTimeout(resolve, 100))
          response = await fetch(`${API_URL}/auth/refresh`, {
            method: 'POST',
            credentials: 'include',
          })
        }
        if (!response.ok) return null
        const data: { access_token: string } = await response.json()
        return data.access_token
      } catch {
        return null
      }
    })()

    refreshPromise.current = pending
    void pending.finally(() => {
      if (refreshPromise.current === pending) refreshPromise.current = null
    })
    return pending
  }, [])

  useEffect(() => {
    let active = true
    void refreshAccessToken().then((token) => {
      if (active && token) {
        setAccessToken(token)
        setApiStatus('online')
      }
    })
    return () => { active = false }
  }, [refreshAccessToken])

  async function requestApi(
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> {
    const requestId = ++apiRequestId.current
    try {
      const send = (token: string | null) => {
        const headers = new Headers(init?.headers)
        if (token) headers.set('Authorization', `Bearer ${token}`)
        return fetch(input, { ...init, headers, credentials: 'include' })
      }
      let response = await send(accessToken)
      if (response.status === 401 && accessToken) {
        const renewedToken = await refreshAccessToken()
        if (renewedToken) {
          setAccessToken(renewedToken)
          response = await send(renewedToken)
        } else {
          logout(false)
          return response
        }
      }
      if (requestId === apiRequestId.current) setApiStatus('online')
      return response
    } catch (error) {
      if (requestId === apiRequestId.current) setApiStatus('offline')
      throw error
    }
  }

  async function loadDocuments() {
    const requestId = ++documentsRequestId.current
    setDocumentsLoading(true)
    try {
      const response = await requestApi(`${API_URL}/documents/`)

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data: DocumentItem[] = await response.json()
      if (requestId === documentsRequestId.current) {
        setDocuments(data)
      }
    } catch (error) {
      if (requestId !== documentsRequestId.current) return
      console.error('Ошибка загрузки документов:', error)
      setMessage(
        error instanceof Error && error.message.startsWith('HTTP ')
          ? 'API доступен, но не удалось загрузить список документов.'
          : 'Не удалось загрузить список документов. Проверь подключение к API.',
      )
    } finally {
      if (requestId === documentsRequestId.current) {
        setDocumentsLoading(false)
      }
    }
  }

  useEffect(() => {
    if (!accessToken) return
    const timeoutId = window.setTimeout(() => {
      void loadDocuments()
    }, 0)
    return () => window.clearTimeout(timeoutId)
  }, [accessToken])

  async function submitAuth(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setAuthLoading(true)
    setAuthError('')
    setAuthNotice('')
    try {
      if (authMode === 'forgot') {
        const response = await fetch(`${API_URL}/auth/forgot-password`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: authEmail }),
        })
        if (!response.ok) {
          const data = await response.json().catch(() => null)
          throw new Error(data?.detail || 'Не удалось отправить письмо.')
        }
        setAuthNotice('Если аккаунт с таким email существует, на него отправлена ссылка для сброса пароля.')
        setAuthMode('login')
        return
      }

      if (authMode === 'reset') {
        const response = await fetch(`${API_URL}/auth/reset-password`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: resetToken, new_password: authPassword }),
        })
        if (!response.ok) {
          const data = await response.json().catch(() => null)
          throw new Error(data?.detail || 'Ссылка сброса пароля недействительна или устарела.')
        }
        setAuthPassword('')
        setResetToken('')
        setAuthMode('login')
        setAuthNotice('Пароль изменён. Войдите с новым паролем.')
        window.history.replaceState({}, '', window.location.pathname)
        return
      }

      if (authMode === 'register') {
        const registration = await fetch(`${API_URL}/auth/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: authEmail, password: authPassword }),
        })
        if (!registration.ok) {
          const data = await registration.json().catch(() => null)
          throw new Error(data?.detail || 'Не удалось создать аккаунт.')
        }
        const account: { email_verified: boolean } = await registration.json()
        if (!account.email_verified) {
          setAuthPassword('')
          setAuthMode('login')
          setAuthNotice('Аккаунт создан. Проверьте почту и перейдите по ссылке подтверждения перед входом.')
          return
        }
      }

      const body = new URLSearchParams({
        username: authEmail,
        password: authPassword,
      })
      const response = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
        credentials: 'include',
      })
      if (!response.ok) {
        const data = await response.json().catch(() => null)
        throw new Error(data?.detail || 'Неверный email или пароль.')
      }
      const data: { access_token: string } = await response.json()
      setAccessToken(data.access_token)
      setAuthPassword('')
      setApiStatus('online')
    } catch (error) {
      setAuthError(
        error instanceof Error
          ? error.message
          : 'Не удалось выполнить запрос. Проверь подключение к серверу.',
      )
    } finally {
      setAuthLoading(false)
    }
  }

  async function resendVerification() {
    setAuthLoading(true)
    setAuthError('')
    setAuthNotice('')
    try {
      const response = await fetch(`${API_URL}/auth/resend-verification`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: authEmail }),
      })
      if (!response.ok) {
        const data = await response.json().catch(() => null)
        throw new Error(data?.detail || 'Не удалось отправить письмо.')
      }
      setAuthNotice('Если аккаунту требуется подтверждение, письмо будет отправлено.')
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : 'Не удалось отправить письмо.')
    } finally {
      setAuthLoading(false)
    }
  }

  function logout(revokeServerSession = true) {
    if (revokeServerSession && accessToken) {
      void fetch(`${API_URL}/auth/logout`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${accessToken}` },
        credentials: 'include',
      }).catch(() => undefined)
    }
    searchRequestId.current += 1
    documentsRequestId.current += 1
    selectedDocumentRequestId.current += 1
    setAccessToken(null)
    setDocuments([])
    setResults([])
    setAiAnswer('')
    setAnswerSources([])
    setSelectedDocument(null)
    setEditingDocument(null)
    setHasSearched(false)
    setMessage('')
    setApiStatus('checking')
  }

  async function downloadAccountExport() {
    try {
      const response = await requestApi(`${API_URL}/auth/me/export`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const link = window.document.createElement('a')
      link.href = url
      link.download = 'mindbase-account-export.json'
      window.document.body.appendChild(link)
      link.click()
      link.remove()
      // Let the browser start consuming the blob before releasing its object URL.
      window.setTimeout(() => window.URL.revokeObjectURL(url), 1000)
      setMessage('Экспорт данных подготовлен и скачан.')
    } catch (error) {
      setMessage(error instanceof Error ? `Не удалось экспортировать данные: ${error.message}` : 'Не удалось экспортировать данные.')
    }
  }

  async function deleteAccount() {
    if (accountDeleteConfirmation !== 'DELETE') {
      setMessage('Для удаления введи DELETE без кавычек.')
      return
    }
    setAccountDeleting(true)
    try {
      const response = await requestApi(`${API_URL}/auth/me`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_password: accountDeletePassword,
          confirmation: accountDeleteConfirmation,
        }),
      })
      if (!response.ok) {
        const data = await response.json().catch(() => null)
        throw new Error(data?.detail || `HTTP ${response.status}`)
      }
      setAccountDeleteOpen(false)
      setAccountDeletePassword('')
      setAccountDeleteConfirmation('')
      logout(false)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Не удалось удалить аккаунт.')
    } finally {
      setAccountDeleting(false)
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

      const sources = data.sources ?? []
      setAiAnswer(data.answer)
      setAnswerSources(sources)

      // Several retrieved chunks can belong to the same document. Keep every
      // chunk in the citation list, but show each document only once.
      const uniqueDocuments = new Map<number, DocumentItem>()
      for (const source of sources) {
        if (!uniqueDocuments.has(source.document_id)) {
          uniqueDocuments.set(source.document_id, {
            id: source.document_id,
            title: source.title,
            content: source.content,
          })
        }
      }
      setResults([...uniqueDocuments.values()])

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
      documentsRequestId.current += 1
      setDocumentsLoading(false)
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

    documentsRequestId.current += 1
    setDocumentsLoading(false)
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

    if (selectedDocumentRequestDocumentId.current === document.id) {
      closeSelectedDocument()
    }

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
      if (selectedDocumentRequestDocumentId.current === updatedDocument.id) {
        selectedDocumentRequestId.current += 1
        selectedDocumentRequestDocumentId.current = null
        setSelectedDocumentLoading(false)
        setSelectedDocumentError('')
      }
      documentsRequestId.current += 1
      setDocumentsLoading(false)
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
  if (!accessToken) {
    const isEmailOnly = authMode === 'forgot'
    const isPasswordOnly = authMode === 'reset'
    const heading = authMode === 'login'
      ? 'С возвращением'
      : authMode === 'register'
        ? 'Создать аккаунт'
        : authMode === 'forgot'
          ? 'Восстановить пароль'
          : 'Новый пароль'
    const description = authMode === 'login'
      ? 'Войдите, чтобы открыть свою приватную базу знаний.'
      : authMode === 'register'
        ? 'Создайте аккаунт и начните собирать собственную базу знаний.'
        : authMode === 'forgot'
          ? 'Укажите email, и мы отправим ссылку для восстановления доступа.'
          : 'Введите новый пароль для своего аккаунта.'
    return (
      <main className="auth-screen">
        <section className="auth-card">
          <div className="auth-brand">
            <span className="brand-icon"><BrainCircuit size={25} /></span>
            <span>Mindbase<span className="brand-dot">.</span></span>
          </div>
          <p className="auth-eyebrow">PERSONAL KNOWLEDGE WORKSPACE</p>
          <h1>{heading}</h1>
          <p className="auth-description">{description}</p>
          <form className="auth-form" onSubmit={submitAuth}>
            {!isPasswordOnly && (
              <>
                <label htmlFor="auth-email">Email</label>
                <input
                  id="auth-email"
                  type="email"
                  autoComplete="email"
                  value={authEmail}
                  onChange={(event) => setAuthEmail(event.target.value)}
                  required
                />
              </>
            )}
            {!isEmailOnly && (
              <>
                <label htmlFor="auth-password">Пароль</label>
                <input
                  id="auth-password"
                  type="password"
                  autoComplete={authMode === 'login' ? 'current-password' : 'new-password'}
                  minLength={12}
                  value={authPassword}
                  onChange={(event) => setAuthPassword(event.target.value)}
                  required
                />
              </>
            )}
            {authNotice && <p className="auth-notice" role="status">{authNotice}</p>}
            {authError && <p className="auth-error" role="alert">{authError}</p>}
            <button className="auth-submit" type="submit" disabled={authLoading}>
              {authLoading
                ? 'Подождите…'
                : authMode === 'login'
                  ? 'Войти'
                  : authMode === 'register'
                    ? 'Создать аккаунт'
                    : authMode === 'forgot'
                      ? 'Отправить ссылку'
                      : 'Сменить пароль'}
            </button>
          </form>
          {authMode === 'login' && (
            <>
              <button className="auth-switch" type="button" onClick={() => { setAuthMode('forgot'); setAuthError(''); setAuthNotice('') }}>
                Забыли пароль?
              </button>
              <button className="auth-switch" type="button" onClick={() => void resendVerification()} disabled={authLoading}>
                Не пришло письмо подтверждения?
              </button>
            </>
          )}
          {(authMode === 'login' || authMode === 'register') && (
            <button
              className="auth-switch"
              type="button"
              onClick={() => {
                setAuthMode((mode) => mode === 'login' ? 'register' : 'login')
                setAuthError('')
                setAuthNotice('')
              }}
            >
              {authMode === 'login'
                ? 'Нет аккаунта? Зарегистрироваться'
                : 'Уже есть аккаунт? Войти'}
            </button>
          )}
          {(authMode === 'forgot' || authMode === 'reset') && (
            <button className="auth-switch" type="button" onClick={() => { setAuthMode('login'); setAuthError(''); setAuthNotice('') }}>
              Вернуться ко входу
            </button>
          )}
          {authMode === 'register' && (
            <p className="auth-password-hint">Пароль должен содержать не менее 12 символов.</p>
          )}
        </section>
      </main>
    )
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
          aria-current={activePage === 'search' ? 'page' : undefined}
          onClick={() => setActivePage('search')}
        >
          <Search size={18} />
          <span>Семантический поиск</span>
        </button>
        <button
          className={`nav-item ${activePage === 'documents' ? 'active' : ''}`}
          aria-current={activePage === 'documents' ? 'page' : undefined}
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
          <div className="status-card" role="status" aria-live="polite">
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
          <div className="topbar-actions">
            <button className="account-export-button" type="button" onClick={() => void downloadAccountExport()}>
              <Download size={15} /> Экспорт данных
            </button>
            <button className="account-delete-button" type="button" onClick={() => { setAccountDeleteOpen(true); setMessage('') }}>
              Удалить аккаунт
            </button>
            <button className="logout-button" type="button" onClick={() => logout()}>Выйти</button>
          </div>
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
              <button
                className="search-button"
                type="submit"
                disabled={loading}
                aria-label={loading ? 'Выполняется поиск' : 'Найти'}
              >
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
                          Относительная оценка ранжирования: {(source.score * 100).toFixed(1)}%
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

            <div className="results-list" aria-busy={loading}>
              {loading && (
                <div className="empty-state" role="status">
                  <LoaderCircle className="spin" size={18} /> Ищу информацию в базе знаний…
                </div>
              )}
              {results.map((document) => (
                <article className="result-card" key={document.id}>
                  <button
                    type="button"
                    className="result-open-button"
                    onClick={() => void openDocument(document)}
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
              {!loading && !results.length && !message && (
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
      {accountDeleteOpen && (
        <div
          className="modal-overlay"
          onClick={() => { if (!accountDeleting) setAccountDeleteOpen(false) }}
        >
          <section
            className="document-modal account-delete-modal"
            role="dialog"
            tabIndex={-1}
            aria-modal="true"
            aria-labelledby="account-delete-title"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              className="modal-close"
              type="button"
              onClick={() => setAccountDeleteOpen(false)}
              disabled={accountDeleting}
              aria-label="Закрыть"
            >
              <X size={20} />
            </button>
            <div className="account-delete-heading">
              <AlertTriangle size={22} />
              <h2 id="account-delete-title">Удаление аккаунта</h2>
            </div>
            <p className="account-delete-warning">
              Это действие необратимо. Аккаунт, документы, фрагменты базы знаний,
              сессии и ссылки восстановления будут удалены.
            </p>
            <form
              className="account-delete-form"
              onSubmit={(event) => { event.preventDefault(); void deleteAccount() }}
            >
              <label htmlFor="account-delete-password">Текущий пароль</label>
              <input
                id="account-delete-password"
                type="password"
                autoComplete="current-password"
                value={accountDeletePassword}
                onChange={(event) => setAccountDeletePassword(event.target.value)}
                required
              />
              <label htmlFor="account-delete-confirmation">Введи DELETE для подтверждения</label>
              <input
                id="account-delete-confirmation"
                value={accountDeleteConfirmation}
                onChange={(event) => setAccountDeleteConfirmation(event.target.value)}
                autoComplete="off"
                required
              />
              <div className="edit-actions">
                <button
                  type="button"
                  className="edit-cancel"
                  onClick={() => setAccountDeleteOpen(false)}
                  disabled={accountDeleting}
                >
                  Отмена
                </button>
                <button
                  type="submit"
                  className="account-delete-confirm"
                  disabled={accountDeleting || !accountDeletePassword || accountDeleteConfirmation !== 'DELETE'}
                >
                  {accountDeleting ? 'Удаление…' : 'Удалить аккаунт навсегда'}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
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
