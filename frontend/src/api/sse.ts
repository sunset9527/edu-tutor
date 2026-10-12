export interface SSEEvent<T = Record<string, unknown>> {
  event: string
  data: T
}

export class SSEDecoder {
  private buffer = ''

  push(chunk: string): SSEEvent[] {
    this.buffer += chunk.replace(/\r\n/g, '\n')
    const frames = this.buffer.split('\n\n')
    this.buffer = frames.pop() ?? ''
    return frames.map(parseFrame).filter((item): item is SSEEvent => item !== null)
  }

  finish(): SSEEvent[] {
    const tail = this.buffer.trim()
    this.buffer = ''
    return tail ? [parseFrame(tail)].filter((item): item is SSEEvent => item !== null) : []
  }
}

function parseFrame(frame: string): SSEEvent | null {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of frame.split('\n')) {
    if (line.startsWith(':')) continue
    if (line.startsWith('event:')) event = line.slice(6).trim()
    if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
  }
  if (!dataLines.length) return null
  return { event, data: JSON.parse(dataLines.join('\n')) }
}

export async function streamChat(
  body: { student_id: number; message: string; session_id?: number },
  onEvent: (event: SSEEvent) => void,
  fetcher: typeof fetch = fetch,
): Promise<number> {
  const token = localStorage.getItem('edututor_token')
  const response = await fetcher('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail || `对话请求失败（${response.status}）`)
  }
  if (!response.body) throw new Error('浏览器未提供流式响应体')

  const decoder = new SSEDecoder()
  const textDecoder = new TextDecoder()
  const reader = response.body.getReader()
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    for (const event of decoder.push(textDecoder.decode(value, { stream: true }))) {
      onEvent(event)
    }
  }
  for (const event of decoder.push(textDecoder.decode())) onEvent(event)
  for (const event of decoder.finish()) onEvent(event)

  const sessionId = Number(response.headers.get('X-Session-Id'))
  if (!Number.isFinite(sessionId)) throw new Error('响应缺少有效会话编号')
  return sessionId
}
