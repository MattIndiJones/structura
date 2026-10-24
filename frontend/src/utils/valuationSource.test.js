import { expect, it } from 'vitest'
import { valuationSourceCode,valuationSourceLabel } from './valuationSource.js'

it.each(['booking','booking+overrides','realized','realized+overrides','known_settlement'])(
  'uses effective source %s despite contradictory or empty request',source=>{
    const run={result:{market_used:{source}},diagnostics:{request:{recalibrate:'realized'}}}
    expect(valuationSourceCode(run)).toBe(source)
    if(source!=='realized') expect(valuationSourceLabel(run)).not.toBe('Marché actualisé')
  })
it('keeps old archives without effective source unknown instead of inventing current market',()=>{
  expect(valuationSourceCode({diagnostics:{request:{}}})).toBe('unknown')
  expect(valuationSourceCode({diagnostics:{request:{recalibrate:'none'}}})).toBe('unknown')
})
it('reads nested and frozen effective evidence',()=>{
  expect(valuationSourceCode({result:{mtm:{market_used:{source:'known_settlement'}}}})).toBe('known_settlement')
  expect(valuationSourceCode({diagnostics:{effective_source:'booking+overrides'}})).toBe('booking+overrides')
})
