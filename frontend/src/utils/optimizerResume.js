import { curveRows, emptyOptimizerAsset, roundPricingInput } from './optimizerMarket.js'

/** Restore effective inputs, preserving dated references separately. */
export function researchFormState(record, family) {
  const request=record.request, market=request.market
  const percent=value=>value==null?'':roundPricingInput(value*100)
  const correlations={},manualCorrelations={}
  market.underlyings.forEach((asset,i)=>market.underlyings.slice(i+1).forEach((other,k)=>{
    correlations[`${i}-${i+k+1}`]=roundPricingInput(market.correlation[i][i+k+1])
    manualCorrelations[[asset.ticker,other.ticker].sort().join('|')]=true
  }))
  return {
    form:Object.fromEntries(['product_family','objective','model','currency','strike_date','convention','settlement_lag'].map(key=>[key,request[key]])),
    assets:market.underlyings.map(asset=>({...emptyOptimizerAsset(asset.ticker,asset.asset_type),_ticker:asset.ticker,
      vol:percent(asset.sigma),dividend:percent(asset.q),dividendCurve:curveRows(asset.dividend_curve),manual:{vol:true,dividend:true}})),
    ranges:Object.fromEntries(family.range_fields.map(field=>[field.key,Object.fromEntries(Object.entries(request.ranges[field.key]).map(([key,value])=>[key,Number((value*(field.unit==='fraction'?100:1)).toFixed(12))]))])),
    settings:Object.fromEntries(family.fixed_fields.map(field=>[field.key,request.payoff_settings[field.key]*(field.unit==='fraction'?100:1)])),
    observations:request.ranges.observation_months || [],
    constraints:{target_price:percent(request.constraints.target_price),price_tolerance:percent(request.constraints.price_tolerance)},
    economics:Object.fromEntries(Object.entries(request.economics).map(([key,value])=>[key,percent(value)])),
    solutionMinimum:percent(request.constraints[family.solved_field.minimum_key]),solutionMaximum:percent(request.constraints[family.solved_field.maximum_key]),
    targetCoupon:percent(request.constraints.target_coupon),couponTolerance:percent(request.constraints.coupon_tolerance),
    risk:{loss:percent(request.constraints.max_probability_loss),autocall:percent(request.constraints.min_probability_autocall),
      life:request.constraints.max_expected_maturity ?? '',capitalLoss:percent(request.constraints.max_expected_capital_loss)},
    rate:percent(market.rate),yieldNodes:curveRows(market.yield_curve),fundingNodes:curveRows(market.funding_curve),
    fundingMode:market.funding_curve?.length?'curve':'flat',fundingSpread:roundPricingInput(market.funding_spread*10000),
    correlations,manualCorrelations,
    automaticMarket:{...market,pricing_date:market.as_of,warnings:record.context.market_snapshot?.warnings || []},
    search:request.search,
  }
}
