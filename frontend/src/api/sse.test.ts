import { describe, expect, it } from 'vitest'
import { SSEDecoder } from './sse'

describe('SSEDecoder', () => {
  it('keeps an incomplete frame until the next network chunk', () => {
    const decoder = new SSEDecoder()
    expect(decoder.push('event: response_chunk\ndata: {"sequence":1,"te')).toEqual([])
    expect(decoder.push('xt":"第一步"}\n\n')).toEqual([
      {
        event: 'response_chunk',
        data: { sequence: 1, text: '第一步' },
      },
    ])
  })

  it('supports CRLF and multiple named events in one chunk', () => {
    const decoder = new SSEDecoder()
    expect(
      decoder.push(
        'event: generation_started\r\ndata: {"sequence":1}\r\n\r\n' +
          'event: completed\r\ndata: {"sequence":2,"response":"完成"}\r\n\r\n',
      ),
    ).toEqual([
      { event: 'generation_started', data: { sequence: 1 } },
      { event: 'completed', data: { sequence: 2, response: '完成' } },
    ])
  })
})
