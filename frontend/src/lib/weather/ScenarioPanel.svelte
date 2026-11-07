<script lang="ts">
 import type { Frame } from './terra.ts';
 let {onMap,active}:{active:boolean;onMap:(frame:Frame|null)=>void}=$props();
 let warming=$state(2),rain=$state(.8),et=$state(1.1),hours=$state(48),busy=$state(false),error=$state('');
 type Metrics={soil_mm:number;snow_mm:number;dry_area_pct:number};
 type Result={start:string;end:string;notice:string;actual_hours:number;max_water_residual_mm:number;frame:Frame;series:{time:string;regions:Record<string,{baseline:Metrics;scenario:Metrics}>}[]};
 let result=$state<Result|null>(null);
 const curve=(key:'baseline'|'scenario')=>{if(!result)return '';const values=result.series.flatMap(s=>[s.regions['Nordic land'].baseline.soil_mm,s.regions['Nordic land'].scenario.soil_mm]);const lo=Math.min(...values),hi=Math.max(...values);return result.series.map((s,i)=>`${10+i*260/Math.max(1,result!.series.length-1)},${80-65*(s.regions['Nordic land'][key].soil_mm-lo)/Math.max(.01,hi-lo)}`).join(' ');};
 async function run(){busy=true;error='';try{const r=await fetch('/terra/api/scenario',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({warming_c:warming,rain_factor:rain,et_factor:et,hours})});if(!r.ok)throw Error(await r.text());result=await r.json();onMap(null);}catch(e){error=String(e);}finally{busy=false;}}
 function download(){if(!result)return;const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='terra-regional-sensitivity.json';a.click();URL.revokeObjectURL(url);}
</script>
<details><summary>Regional evolution & adaptation</summary>
<p>Paired soil/snow simulation from identical API-initialized stores. Uses the active live or historical period. Inputs below are hypothetical climate stress assumptions.</p>
<label>Local warming (°C)<input type="number" min="-3" max="8" step=".5" bind:value={warming}/></label>
<label>Rain multiplier<input type="number" min="0" max="3" step=".1" bind:value={rain}/></label>
<label>Evaporation-demand multiplier<input type="number" min=".5" max="2" step=".1" bind:value={et}/></label>
<label>Hours to evolve<input type="number" min="1" max="168" bind:value={hours}/></label>
<button disabled={busy} onclick={run}>{busy?'Simulating paired water balances…':'Run baseline + stress scenario'}</button>
{#if error}<p role="alert">{error}</p>{/if}
{#if result}
<p>{result.start.slice(0,16)} → {result.end.slice(0,16)} UTC<br>{result.actual_hours.toFixed(1)} hours simulated · 15-minute land steps</p>
{@const end=result.series[result.series.length-1]}
<svg viewBox="0 0 280 95" role="img" aria-label="Nordic land mean soil storage evolution: baseline blue, scenario green"><polyline points={curve('baseline')} fill="none" stroke="#7cb7ff" stroke-width="2"/><polyline points={curve('scenario')} fill="none" stroke="#cfeb9b" stroke-width="2"/></svg><p>Nordic mean soil water · baseline (blue) / scenario (green). Vertical scale fits this run; compare numeric values below.</p>
<table><caption>Final soil storage · baseline → scenario</caption><tbody>{#each Object.entries(end.regions) as [name,v]}<tr><th>{name}</th><td>{v.baseline.soil_mm.toFixed(1)} → {v.scenario.soil_mm.toFixed(1)} mm<br><small>Dry-screen area {v.baseline.dry_area_pct.toFixed(1)} → {v.scenario.dry_area_pct.toFixed(1)}%</small></td></tr>{/each}</tbody></table>
<p>Dry screen: storage below 30% of assumed capacity. Approximate country masks; area-weighted values. Review changing dry exposure for irrigation/storage planning and wet conditions for drainage or harvest contingency. No crop-loss or supply forecast is inferred.</p>
<label>Map final scenario soil<input type="checkbox" checked={active} onchange={e=>onMap(e.currentTarget.checked?result!.frame:null)}/></label>
{#if active}<p>Frozen scenario endpoint on Nordic soil layer; the global Earth remains visible. Turn this off to return to evolving weather.</p>{/if}
<button onclick={download}>Export assumptions + hourly results (JSON)</button>
<p>Maximum water-balance residual: {result.max_water_residual_mm.toExponential(1)} mm.</p>
<p>{result.notice}</p>
{/if}
<p>For policy-grade climate analysis, add multi-decade observations, regional CMIP6 ensembles, crop calendars and supplier locations. <a href="https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/" target="_blank" rel="noreferrer">IPCC regional uncertainty ↗</a></p>
</details>
<style>
 details{border-top:1px solid #385158;padding:12px 0}summary{cursor:pointer;color:#cfeb9b;font-weight:600}p{color:#a3b6b8;font-size:11px;line-height:1.6}label{display:flex;justify-content:space-between;align-items:center;margin:12px 0;gap:8px}input[type=number]{width:65px;padding:5px;background:#18313b;color:#e3eee8;border:1px solid #385158;border-radius:4px}button{width:100%;padding:9px;background:#cfeb9b;color:#14251a;border:0;border-radius:5px;cursor:pointer}button:disabled{opacity:.5}table{width:100%;font-size:11px;border-collapse:collapse}caption{text-align:left;margin-bottom:8px}th,td{text-align:left;padding:8px 3px;border-bottom:1px solid #385158}small{color:#a3b6b8}a{color:#cfeb9b}
</style>
