import { afterEach, describe, expect, it, vi } from 'vitest'
import { rangeCount, searchSize, rankedCandidates, runOptimizer } from './productOptimizer.js'

afterEach(() => vi.unstubAllGlobals())
describe('Product Optimizer', () => {
  it('counts decimal endpoints and rejects reversed or zero-step ranges', () => {
    expect(rangeCount({minimum:.5,maximum:.7,step:.05})).toBe(5)
    expect(rangeCount({minimum:2,maximum:1,step:1})).toBeNull()
    expect(rangeCount({minimum:1,maximum:2,step:0})).toBeNull()
    expect(searchSize({maturity_months:{minimum:12,maximum:36,step:12},protection_barrier:{minimum:50,maximum:60,step:5},autocall_trigger:{minimum:100,maximum:100,step:5},observation_months:[3,6]})).toBe(18)
  })
  it('never recommends a rejected candidate', () => {
    expect(rankedCandidates({candidates:[{rank:1,constraint_status:'REJECTED'},{rank:2,constraint_status:'PASS'}]})).toEqual([{rank:2,constraint_status:'PASS'}])
  })
  it('handles fragmented UTF-8 streams and requires a final result', async () => {
    vi.stubGlobal('localStorage', {getItem:()=> 'token'})
    const bytes=new TextEncoder().encode('{"type":"progress","message":"évaluation"}\n{"type":"result","result":{}}\n')
    vi.stubGlobal('fetch',vi.fn(async()=>new Response(new ReadableStream({start(controller){controller.enqueue(bytes.slice(0,33));controller.enqueue(bytes.slice(33));controller.close()}}))))
    const events=[]
    await runOptimizer({},undefined,e=>events.push(e))
    expect(events.map(e=>e.type)).toEqual(['progress','result'])
    expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer token')
    vi.stubGlobal('fetch',vi.fn(async()=>new Response('{"type":"progress"}\n')))
    await expect(runOptimizer({},undefined,()=>{})).rejects.toThrow('avant le résultat final')
  })
})
