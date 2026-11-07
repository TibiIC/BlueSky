<script lang="ts">
 import {onMount} from 'svelte';
 type Member={place:string;model:string;period:string;mean_temp_c:number;mean_annual_precip_mm:number};
 type Evidence={climate:{members:Member[];notice:string;source:string};benchmark:{results:{place:string;days:number;bias_mm:number;rmse_mm:number;series:{date:string;model_soil_mm:number;era5_land_soil_mm:number}[]}[];notice:string;source:string};supply:{prices:{item:string;contract_price_eur_t:string;replacement_import_premium_frac:string}[];shipments_2025_by_mode:{mode:string;shipments:number;tonnes:number;tonne_km:number}[];notice:string}};
 let data=$state<Evidence|null>(null),error=$state(''),crop=$state('pea'),volume=$state(1000),shortfall=$state(10),avoided=$state(25),annualCost=$state(10000);
 const safe=(v:number)=>Number.isFinite(v)?v:0;
 const price=$derived(data?.supply.prices.find(p=>p.item===crop));
 const missing=$derived(Math.max(0,safe(volume))*Math.max(0,Math.min(100,safe(shortfall)))/100);
 const premium=$derived(missing*Number(price?.contract_price_eur_t??0)*Number(price?.replacement_import_premium_frac??0));
 onMount(()=>{let disposed=false;fetch('/data/decision/evidence.json').then(r=>{if(!r.ok)throw Error('Evidence data unavailable');return r.json();}).then((d:Evidence)=>{if(!disposed)data=d;}).catch(e=>{if(!disposed)error=String(e);});return()=>{disposed=true;};});
 function exportScenario(){const content={evidence:data,scenario:{crop,contract_tonnes:safe(volume),shortfall_pct:safe(shortfall),avoided_shortfall_pct:safe(avoided),annualized_cost_eur:safe(annualCost),extra_replacement_premium_eur:premium,notice:'User-specified hypothetical shortfall and effectiveness; synthetic Apetit prices. No calibrated link to climate/weather or actual supplier losses.'}};const url=URL.createObjectURL(new Blob([JSON.stringify(content,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='terra-decision-scenario.json';a.click();URL.revokeObjectURL(url);}
 const change=(m:Member)=>{const b=data!.climate.members.find(v=>v.place===m.place&&v.model===m.model&&v.period==='baseline')!;return {temp:m.mean_temp_c-b.mean_temp_c,rain:100*(m.mean_annual_precip_mm/b.mean_annual_precip_mm-1)};};
 const line=(series:{model_soil_mm:number;era5_land_soil_mm:number}[],key:'model_soil_mm'|'era5_land_soil_mm')=>{const max=Math.max(...series.flatMap(s=>[s.model_soil_mm,s.era5_land_soil_mm]));return series.map((s,i)=>`${5+i*270/(series.length-1)},${85-80*s[key]/max}`).join(' ');};
</script>
<details class="evidence"><summary>Climate, validation & supply scenarios</summary>
{#if error}<p role="alert">{error}</p>{:else if data}
<strong>PUBLIC CLIMATE MODELS · TWO-MEMBER SCREEN</strong>
<p>2040–2049 minus 2000–2009. Temperature and annual precipitation changes at representative locations.</p>
<table><thead><tr><th>Location / model</th><th>Δ °C</th><th>Rain Δ %</th></tr></thead><tbody>{#each data.climate.members.filter(m=>m.period==='future') as m}{@const d=change(m)}<tr><td>{m.place}<small>{m.model}</small></td><td>{d.temp.toFixed(2)}</td><td>{d.rain.toFixed(1)}</td></tr>{/each}</tbody></table>
<p>Rows show individual members, so disagreement remains visible. They are not forecasts for a particular day.</p><p>{data.climate.notice}</p><a href={data.climate.source} target="_blank" rel="noreferrer">Climate source & methods ↗</a>
<strong>2018 DROUGHT · REANALYSIS BENCHMARK</strong>
{#each data.benchmark.results as r}<p>{r.place} · {r.days} daily endpoints<br>Bias {r.bias_mm.toFixed(1)} mm · RMSE {r.rmse_mm.toFixed(1)} mm</p><svg viewBox="0 0 280 90" role="img" aria-label={`${r.place} modeled and ERA5-Land soil storage, April through September 2018`}><polyline points={line(r.series,'model_soil_mm')} fill="none" stroke="#cfeb9b" stroke-width="2"/><polyline points={line(r.series,'era5_land_soil_mm')} fill="none" stroke="#7cb7ff" stroke-width="2"/></svg>{/each}
<p>Green: generic land model · blue: reanalysis reference. Storage in mm over 1 m; chart axes fit each location.</p><p>{data.benchmark.notice}</p><a href={data.benchmark.source} target="_blank" rel="noreferrer">Historical source ↗</a>
<strong>SYNTHETIC APETIT SUPPLY / COST SCREEN</strong>
<p>Shipment-mode totals from the synthetic 2025 package. Route endpoints are absent from these records; no actual supplier routing is inferred.</p>
<table><thead><tr><th>Mode</th><th>Tonnes</th><th>Tonne-km</th></tr></thead><tbody>{#each data.supply.shipments_2025_by_mode as m}<tr><td>{m.mode}</td><td>{m.tonnes.toFixed(0)}</td><td>{m.tonne_km.toFixed(0)}</td></tr>{/each}</tbody></table>
<label>Crop / item<select bind:value={crop}>{#each data.supply.prices as p}<option value={p.item}>{p.item}</option>{/each}</select></label>
<label>Assumed contract tonnes<input type="number" min="0" bind:value={volume}/></label>
<label>Assumed shortfall (%)<input type="number" min="0" max="100" bind:value={shortfall}/></label>
<p>Public climate/weather does not automatically set the shortfall: no calibrated yield-to-volume relationship is available.</p>
<p>Assumed missing volume: {missing.toFixed(1)} t<br>Package contract price: €{Number(price?.contract_price_eur_t??0).toFixed(2)}/t<br>Replacement premium: {(100*Number(price?.replacement_import_premium_frac??0)).toFixed(0)}%<br><b>Extra purchasing premium: €{premium.toFixed(0)}</b></p>
<label>Assumed shortfall avoided (%)<input type="number" min="0" max="100" bind:value={avoided}/></label>
<label>Annualized adaptation cost (€)<input type="number" min="0" bind:value={annualCost}/></label>
<p>Illustrative avoided premium: €{(premium*Math.max(0,Math.min(100,safe(avoided)))/100).toFixed(0)}<br>Less assumed annualized cost: €{Math.max(0,safe(annualCost)).toFixed(0)}<br>Scenario difference: €{(premium*Math.max(0,Math.min(100,safe(avoided)))/100-Math.max(0,safe(annualCost))).toFixed(0)}</p>
<p>No ROI or investment recommendation: this omits implementation timing, uncertainty, financing, transport premiums and other effects.</p><p>{data.supply.notice}</p>
<button onclick={exportScenario}>Export evidence + current cost assumptions</button>
{:else}<p>Loading public evidence and synthetic scenarios…</p>{/if}
</details>
<style>
.evidence{padding:4px 0}summary{color:#cfeb9b;cursor:pointer;font-size:12px;font-weight:600}strong{display:block;font-size:10px;color:#cfeb9b;margin-top:18px}p{font-size:10px;color:#abc0c5;line-height:1.6}table{width:100%;font-size:10px;border-collapse:collapse;color:#e3eee8}th,td{text-align:left;padding:7px 3px;border-bottom:1px solid #385158}small{display:block;font-size:8px;color:#abc0c5}svg{width:100%}label{display:flex;justify-content:space-between;align-items:center;gap:8px;margin:12px 0;font-size:10px}input,select{width:90px;color:#e3eee8;background:#17333c;border:1px solid #426772;border-radius:4px;padding:5px}button{padding:8px;width:100%;background:#cfeb9b;color:#14251a;border:0;border-radius:4px;cursor:pointer}a{font-size:10px;color:#8ee4f1}b{color:#cfeb9b}
</style>
