
import { useState } from 'react'
import axios from 'axios'

const API_BASE_URL =
  import.meta.env.VITE_API_URL || 'https://ahu-ai.onrender.com'

axios.defaults.baseURL = API_BASE_URL

function App() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [uploadMessage, setUploadMessage] = useState('')
  const [error, setError] = useState('')
  const [selectedFileName, setSelectedFileName] = useState('')
  const [activeDatasetName, setActiveDatasetName] = useState('')
  const [sessionId, setSessionId] = useState(() => localStorage.getItem('ahu_session_id') || '')

  const getRequestConfig = () => {
    const storedSessionId = sessionId || localStorage.getItem('ahu_session_id') || ''

    return storedSessionId
      ? {
          headers: {
            'X-Session-Id': storedSessionId,
          },
        }
      : {}
  }

  const handleSubmit = async (e) => {
    e.preventDefault()

    if (!query.trim()) {
      setError('Please enter a query')
      return
    }

    setError('')
    setLoading(true)

    // split user input into separate queries so we always show all outputs
    const queries = query.split(/,|\n|\|/).map((q) => q.trim()).filter(Boolean)

    try {
      if (queries.length <= 1) {
        const response = await axios.post('/query', { query }, getRequestConfig())
        const d = response.data
        if (Array.isArray(d)) setResults(d)
        else if (d && d.answers) setResults(d.answers)
        else if (d && d.answer) setResults([{ query, answer: d.answer }])
        else setResults([])
      } else {
        // send each query separately and aggregate results
        const promises = queries.map((q) => axios.post('/query', { query: q }, getRequestConfig()))
        const responses = await Promise.all(promises)
        const all = []
        for (let i = 0; i < responses.length; i++) {
          const d = responses[i].data
          if (Array.isArray(d)) all.push(...d)
          else if (d && d.answers) all.push(...d.answers)
          else if (d && d.answer) all.push({ query: queries[i], answer: d.answer })
        }
        setResults(all)
      }
    } catch (err) {
      const msg = err?.response?.data || err.message || 'Backend connection failed'
      setError(typeof msg === 'string' ? msg : JSON.stringify(msg))
    }

    setLoading(false)
  }

  const handleFileUpload = async (event) => {
    const file = event.target.files[0]

    if (!file) return

    // clear previous upload messages when a new file is selected
    setUploadMessage('')
    setError('')
    setSelectedFileName(file.name)

    const formData = new FormData()
    formData.append('file', file)

    setLoading(true)

    try {
      const response = await axios.post(
        '/upload',
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data'
          }
        }
      )

      if (response.data?.session_id) {
        localStorage.setItem('ahu_session_id', response.data.session_id)
        setSessionId(response.data.session_id)
      }

      setActiveDatasetName(file.name)

      setUploadMessage(
        `Uploaded successfully: ${response.data.rows} rows loaded`
      )
    } catch (err) {
      // show useful error info for debugging with HTTP status and detail when available
      const resp = err?.response
      let msg = 'Upload failed'
      if (resp) {
        msg += resp.status ? ` (${resp.status})` : ''
        const data = resp.data
        if (data) {
          if (typeof data === 'string') msg += `: ${data}`
          else if (data.detail) msg += `: ${data.detail}`
          else msg += `: ${JSON.stringify(data)}`
        }
      } else if (err?.message) {
        msg += `: ${err.message}`
      }

      setUploadMessage(msg)
    }

    setLoading(false)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-950 to-slate-900 text-white p-8">
      <div className="max-w-5xl mx-auto">

        <div className="bg-white/5 border border-white/10 backdrop-blur-xl rounded-3xl p-8 shadow-2xl">

          <h1 className="text-5xl font-bold mb-2">
            AHU AI Dashboard
          </h1>

          <p className="text-slate-300 mb-8">
            Upload datasets and query them using natural language.
          </p>

          <div className="mb-6">
            <label className="block mb-2 text-cyan-300">
              Upload Excel / CSV Dataset
            </label>

            <input
              type="file"
              accept=".xlsx,.xls,.csv"
              onChange={handleFileUpload}
              className="w-full rounded-xl bg-black/30 p-3 border border-white/10"
            />

            <div className="mt-2 text-sm text-slate-300 space-y-1">
              <p>Selected file: {selectedFileName || 'No file selected'}</p>
              <p>Active dataset: {activeDatasetName || 'No dataset uploaded yet'}</p>
            </div>

            {uploadMessage && (
              (() => {
                const isError = uploadMessage.toLowerCase().includes('failed') || uploadMessage.toLowerCase().includes('not found')
                return (
                  <p className={`mt-3 ${isError ? 'text-red-400' : 'text-green-400'}`}>
                    {uploadMessage}
                  </p>
                )
              })()
            )}
          </div>

          <form onSubmit={handleSubmit}>
            <textarea
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Example: median return air temperature, mode run status, std dev supply air temp"
              className="w-full h-40 rounded-2xl bg-black/30 border border-white/10 p-5 text-white outline-none"
            />

            <button
              type="submit"
              className="mt-5 w-full rounded-2xl bg-gradient-to-r from-cyan-500 to-blue-600 py-4 text-lg font-semibold hover:scale-[1.02] transition"
            >
              {loading ? 'Processing...' : 'Run Query'}
            </button>
          </form>

          {error && (
            <div className="mt-4 text-red-400">
              {error}
            </div>
          )}

          <div className="mt-6">
            <h2 className="text-xl font-semibold mb-2">Output</h2>
            <div className="rounded-2xl bg-black/30 border border-white/10 p-4 min-h-[120px]">
              {results.length === 0 ? (
                <p className="text-slate-400">No results yet. Run a query.</p>
              ) : (
                <div className="space-y-4">
                  {results.map((item, idx) => (
                    <div key={idx} className="p-3 bg-white/3 rounded-lg">
                      <div className="text-cyan-300 text-sm">Query</div>
                      <div className="mb-2">{item.query || ''}</div>
                      <div className="text-green-400 font-semibold">{item.answer}</div>
                      {Array.isArray(item.data) && item.data.length > 0 && (
                        <pre className="mt-3 overflow-x-auto rounded-xl bg-black/40 p-3 text-xs text-slate-200 whitespace-pre-wrap">
                          {JSON.stringify(item.data, null, 2)}
                        </pre>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          

        </div>
      </div>
    </div>
  )
}

export default App
