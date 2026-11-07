<script lang="ts">
 import CatchmentPanel from '../hydrology/CatchmentPanel.svelte';
 import DecisionEvidence from './DecisionEvidence.svelte';
 import MeasuredBiology from './MeasuredBiology.svelte';
 import FarmPanel from '../farms/FarmPanel.svelte';
 import { untrack } from 'svelte';
 import type { Globe } from '../globe/viewer.ts';
 import { attachTerra, ranges, rgb, differenceRanges, differenceRgb, comparableFields, riskFields, type ComparisonView, type Field, type Status } from './terra.ts';
 /** embedded: rendered inside the right panel's Weather tab (full width, always expanded). */
 let { globe, embedded = false }: {globe:Globe; embedded?: boolean} = $props();
 let status=$state<Status>({regionalConnected:false,globalConnected:false});
 let field=$state<Field>('moisture_g_m3');
 let error=$state('');
 let rotateEarth=$state(false);let weatherMotion=$state(true);let windOnRain=$state(true);
 let visible=$state(false);let focusMarkers=$state(false); // off by default: performance and a clear globe
 let compareDate=$state('');let comparing=$state(false);let compareView=$state<ComparisonView>('difference');
 const comparison=$derived(status.comparison);
 const legend=$derived(comparing&&compareView==='difference'?[-(differenceRanges[field]??10),differenceRanges[field]??10,riskFields.has(field)?'pp':ranges[field][2]]:ranges[field]);
 const legendColor=(v:number)=>comparing&&compareView==='difference'?differenceRgb(v,differenceRanges[field]??10):rgb(field,v);
 async function loadComparison(){
  try{if(!comparableFields.has(field)){field='temp_c';api?.setLayer(field);}await api?.compare(compareDate);comparing=true;api?.setComparisonView(compareView);error='';}catch(e){error=String(e);}
 }
 function viewComparison(view:ComparisonView){compareView=view;api?.setComparisonView(view);}
 function closeComparison(){comparing=false;api?.setComparisonView(null);}

 let historyOpen=$state(false);let startDate=$state('');let endDate=$state('');
 const timeline=$derived(status.regional?.timeline);
 const showHistory=$derived(historyOpen||timeline?.mode==='historical');
 $effect(()=>{if(!compareDate&&timeline?.max_history_date)compareDate=timeline.max_history_date;if(!startDate&&timeline?.max_history_date){startDate=timeline.range?.[0]??timeline.max_history_date;endDate=timeline.range?.[1]??timeline.max_history_date;}});
 async function changeTimeline(body:Record<string,string>){try{api?.setScenario(null);await api?.timeline(body);error='';if(body.mode==='live')historyOpen=false;}catch(e){error=String(e);}}
 const rainPoints=(series:{precip_mm_h:number}[])=>{const max=Math.max(.1,...series.map(s=>s.precip_mm_h));return series.map((s,i)=>`${i*240/Math.max(1,series.length-1)},${50-s.precip_mm_h/max*45}`).join(' ');};
 let api:ReturnType<typeof attachTerra>|undefined;
 const options: [Field,string][]=[['rain_bands','Animated rain bands · forecast'],['temp_c','Temperature · global'],['precip_mm_h','Hourly rain · global'],['rain_day_mm','UTC-day rain · global'],['wind','Wind · global'],['moisture_g_m3','Moisture · global'],['frost_pct','Air frost ≤0°C · crop screen'],['heat_pct','Heat ≥28°C · crop screen'],['heavy_rain_pct','Wet day ≥20mm · crop screen'],['wind_risk_pct','Wind ≥12m/s · crop screen'],['soil_fraction','Soil water · Nordic model'],['snow_water_mm','Snow water · Nordic model'],['crop_stress','Crop water stress (FAO-56) · Nordic model']];

 $effect(()=>{const g=globe;let last=performance.now();return g.viewer.clock.onTick.addEventListener(()=>{const now=performance.now(),dt=Math.min(.1,(now-last)/1000);last=now;if(rotateEarth){g.viewer.camera.rotate(g.C.Cartesian3.UNIT_Z,.025*dt);g.viewer.scene.requestRender();}});});
 $effect(()=>{const target=globe;const connection=untrack(()=>attachTerra(target,s=>status=s));api=connection;return()=>{connection.destroy();api=undefined;};});
 async function control(body:Record<string,number|boolean>){try{await api?.control(body);error='';}catch(e){error=String(e);}}
 function chooseField(){api?.setLayer(field);if(!comparing&&weatherMotion&&(field==='wind'||field==='rain_bands'))control({speed:600,paused:false,...(status.regional?.at_forecast_end?{reset:true}:{})});}
 const utc=(t:string|null|undefined)=>t?t.slice(0,16).replace('T',' ')+' UTC':'never';
 const connected=$derived(status.regionalConnected&&status.globalConnected);
 const modeLabel=$derived(comparing?(compareView==='difference'?'Showing live minus a past date':compareView==='historical'?'Showing a past date':'Showing live weather for comparison'):timeline?.mode==='historical'?'Historical replay with the land physics':'Live forecast with the land physics: soil water, snow and rivers');
 /** One-tap layers; the rest stay in "More layers". */
 const QUICK:[Field,string][]=[['rain_bands','Rain'],['wind','Wind'],['temp_c','Temperature'],['soil_fraction','Soil water'],['crop_stress','Crop stress'],['heat_pct','Heat ≥ 28 °C']];
 const NOTES:Partial<Record<Field,string>>={
  rain_bands:'Forecast rain ≥ 0.1 mm/h, moved by transport-level winds. A forecast-driven proxy, not radar.',
  wind:'10 m forecast winds as moving trails. Forecast forcing, not a momentum simulation.',
  soil_fraction:'How full the top metre of soil is. Nordic land model only.',
  snow_water_mm:'Snow water equivalent. Nordic land model only.',
  crop_stress:'FAO-56 water limitation: 0 none, 1 wilting point. Generic soil and crop calendar; not measured damage.',
  moisture_g_m3:'Near-surface humidity in an effective 1 km layer.'};
 const fieldNote=$derived(NOTES[field]??(riskFields.has(field)?'Coloured land cells pass the shown threshold. Weather screening, not a crop-damage forecast.':'Global coverage with finer Nordic detail.'));
 function fly(lon:number,lat:number,h:number){rotateEarth=false;globe.viewer.camera.flyTo({destination:globe.C.Cartesian3.fromDegrees(lon,lat,h)});}
 function pickField(key:Field){field=key;if(!visible){visible=true;api?.setVisible(true);}chooseField();}
</script>
<section class="weather" class:embedded aria-label="Live weather and land">
 <header class="top">
  <div><span class="eyebrow">TERRA · LIVE WEATHER &amp; LAND</span><h2>What the weather is doing now</h2></div>
  <span class="pill" class:live={connected}>{connected?'● Live':'○ Reconnecting'}</span>
 </header>
 <p class="lede">{modeLabel}</p>
 <div class="nav">
  <button onclick={()=>fly(22,25,24000000)}>Whole Earth</button>
  <button onclick={()=>fly(21.5,63,2600000)}>Nordics</button>
  <button onclick={()=>fly(19,59.5,1800000)}>Apetit regions</button>
 </div>

 <article class="card">
  <div class="card-head">
   <h3>Weather on the map</h3>
   <label class="switch" title="Show weather layers"><input aria-label="Weather layers" type="checkbox" bind:checked={visible} onchange={()=>api?.setVisible(visible)} /><span></span></label>
  </div>
  <div class="quick">
   {#each QUICK as [key,label] (key)}
    <button class:on={visible&&field===key} disabled={comparing&&!comparableFields.has(key)} onclick={()=>pickField(key)}>{label}</button>
   {/each}
  </div>
  <label class="row">More layers <select bind:value={field} onchange={()=>pickField(field)}>{#each options.filter(([k])=>!comparing||comparableFields.has(k)) as [key,title]}<option value={key}>{title}</option>{/each}</select></label>
  <div class="ramp" style={`background:linear-gradient(90deg,rgb(${legendColor(Number(legend[0])).join(',')}),rgb(${legendColor((Number(legend[0])+Number(legend[1]))/2).join(',')}),rgb(${legendColor(Number(legend[1])).join(',')}))`}></div>
  <div class="range"><span>{legend[0]}</span><span>{legend[1]} {legend[2]}</span></div>
  <p class="note">{fieldNote}</p>
  {#if !comparing&&(field==='wind'||field==='rain_bands')}
   <label class="row">Animate (600× demo)<input type="checkbox" bind:checked={weatherMotion} onchange={()=>control({speed:weatherMotion?600:1,paused:false})}/></label>
   {#if field==='rain_bands'}<label class="row">Wind trails over rain<input type="checkbox" bind:checked={windOnRain} onchange={()=>api?.setWindOnRain(windOnRain)}/></label>{/if}
   <div class="buttons">
    <button onclick={()=>control({paused:!status.regional?.controls.paused})}>{status.regional?.controls.paused?'Resume':'Pause'}</button>
    <button class="ghost" onclick={async()=>{weatherMotion=false;await changeTimeline({mode:'live'});control({speed:1,reset:true});}}>Back to live 1×</button>
   </div>
   <p class="note">Model time {utc(status.regional?.sim_time)} · {status.regional?.controls.speed??1}× (600× = ten minutes per second)</p>
  {/if}
 </article>

 <article class="card"><FarmPanel {globe} regional={status.regional} /></article>

 <CatchmentPanel {globe} regional={status.regional} onPlay={()=>{weatherMotion=true;control({speed:600,paused:false});}} onFocus={()=>rotateEarth=false} onPause={()=>control({paused:!status.regional?.controls.paused})}/>

 <details class="card fold"><summary>Research evidence <small>real climate models · soil biology</small></summary>
  <DecisionEvidence />
  <MeasuredBiology {globe} onFocus={()=>{rotateEarth=false;}} />
 </details>

 <details class="card fold"><summary>Compare with a past date <small>live − historical</small></summary>
  <label class="row">Past date (UTC)<input aria-label="Comparison date" type="date" bind:value={compareDate} min="1950-01-01" max={timeline?.max_history_date} /></label>
  <button disabled={!compareDate||comparison?.loading} onclick={loadComparison}>{comparison?.loading?'Loading comparison…':'Compare with live'}</button>
  {#if comparing}
   <div class="seg"><button class:on={compareView==='live'} onclick={()=>viewComparison('live')}>Live</button><button class:on={compareView==='historical'} onclick={()=>viewComparison('historical')}>Historical</button><button class:on={compareView==='difference'} onclick={()=>viewComparison('difference')}>Difference</button></div>
   {#if comparison?.ready&&comparison.summary?.[field]}
    {@const s=comparison.summary[field]}
    <div class="stats"><div><b>{s.live.toFixed(2)}</b>live {ranges[field][2]}</div><div><b>{s.historical.toFixed(2)}</b>past</div><div><b>{s.difference>=0?'+':''}{s.difference.toFixed(2)}</b>change {riskFields.has(field)?'pp':''}</div></div>
    <p class="note">{field==='rain_day_mm'||field==='heavy_rain_pct'?'Complete UTC days':'Same UTC hour'} · Nordic land means · live {utc(comparison.live_time)} · past {utc(comparison.historical_time)}. {comparison.historical_source?.notice} Weather difference, not a climate anomaly.</p>
   {/if}
   <button class="ghost" onclick={closeComparison}>Back to live layers</button>
  {/if}
  {#if comparison?.error}<p class="error" role="alert">{comparison.error}</p>{/if}
 </details>

 <details class="card fold"><summary>Historical replay <small>any week since 1950</small></summary>
  <div class="seg"><button class:on={timeline?.mode!=='historical'&&!historyOpen} onclick={()=>changeTimeline({mode:'live'})}>Live forecast</button><button class:on={showHistory} onclick={()=>historyOpen=true}>Historical</button></div>
  {#if showHistory}
   <label class="row">From (UTC)<input aria-label="Historical start date" type="date" bind:value={startDate} min="1950-01-01" max={timeline?.max_history_date} /></label>
   <label class="row">Through (UTC)<input aria-label="Historical end date" type="date" bind:value={endDate} min={startDate||'1950-01-01'} max={timeline?.max_history_date} /></label>
   <button disabled={timeline?.loading||!startDate||!endDate} onclick={()=>changeTimeline({mode:'historical',start_date:startDate,end_date:endDate})}>{timeline?.loading?'Loading…':'Load period (up to 7 days)'}</button>
   <p class="note">ERA5/ERA5-Land through {timeline?.reanalysis_through??'…'}; newer days use past forecast-model data. Neither is station observations.</p>
   {#if timeline?.summary&&timeline.mode==='historical'}
    <div class="stats"><div><b>{timeline.summary.precipitation_total_mm.toFixed(1)}</b>mm rain</div><div><b>{timeline.summary.min_mean_temperature_c.toFixed(0)}–{timeline.summary.max_mean_temperature_c.toFixed(0)}</b>°C</div><div><b>{timeline.summary.peak_mean_wind_ms.toFixed(1)}</b>m/s peak wind</div></div>
    <svg class="spark" viewBox="0 0 240 55" role="img" aria-label="Hourly precipitation across the selected period"><polyline points={rainPoints(timeline.summary.series)} /></svg>
    <p class="note">{timeline.range?.join(' → ')} · replay {(timeline.position_seconds/3600).toFixed(1)} h · {status.regional?.source.notice}</p>
   {/if}
  {/if}
  {#if timeline?.error}<p role="alert" class="error">Historical data: {timeline.error}</p>{/if}
 </details>

 <details class="card fold"><summary>Engine &amp; provenance <small>physics, sources, controls</small></summary>
  <label class="row">Rotate Earth <small>presentation</small><input type="checkbox" bind:checked={rotateEarth}/></label>
  <label class="row">Säkylä / Bjuv markers<input type="checkbox" bind:checked={focusMarkers} onchange={()=>api?.setFocusMarkers(focusMarkers)} /></label>
  {#if !comparing}
   <label class="row">Speed <select value={String(status.regional?.controls.speed??1)} onchange={e=>control({speed:+e.currentTarget.value})}><option value="1">1× wall time</option><option value="60">60×</option><option value="600">600× demo</option><option value="3600">3600×</option></select></label>
   <label class="row">Nordic rain <select value={String(status.regional?.controls.rain_scale??1)} onchange={e=>control({rain_scale:+e.currentTarget.value})}><option value="0">0× dry</option><option value="1">1× forecast</option><option value="2">2× wet</option><option value="4">4× extreme</option></select></label>
   <div class="buttons"><button onclick={()=>control({paused:!status.regional?.controls.paused})}>{status.regional?.controls.paused?'Resume':'Pause'}</button><button class="ghost" onclick={()=>control({reset:true})}>{timeline?.mode==='historical'?'Restart period':'Reset to now'}</button></div>
  {/if}
  <dl><dt>Engine</dt><dd>Regional v{status.regional?.engine_version??'—'} · finite-volume transport</dd><dt>Soil start</dt><dd>{status.regional?.initialization?.kind??'Waiting'} · {status.regional?.initialization?.soil_seeded_cells??0} cells</dd><dt>Transport winds</dt><dd>{status.regional?.physics?.transport_wind??'Waiting'}</dd><dt>Forcing</dt><dd>Nordic {status.regional?.source.mode??'waiting'} · global {status.global?.source.mode??'waiting'}</dd><dt>Last fetch</dt><dd>{utc(status.regional?.source.fetched_at)}</dd></dl>
  <p class="note">Nordic 25×29 grid from 195 forecast samples; global 36×18 from 24. Forecasts are not observations. Wind is forecast forcing; soil starts from forecast soil moisture. Säkylä/Bjuv markers are town centres, not farms.</p>
  <a href="http://127.0.0.1:8765" target="_blank" rel="noreferrer">Open the physics dashboard ↗</a>
 </details>

 {#if status.regional?.at_forecast_end}<p class="error">Forecast horizon reached; simulation held.</p>{/if}
 {#if error||status.error}<p class="error" role="alert">{error||status.error}</p>{/if}
 {#if status.regional?.source.last_error||status.global?.source.last_error}<p class="error">Weather API unavailable for at least one grid; the last forecast stays active.</p>{/if}
</section>
<style>
.weather{box-sizing:border-box;padding:16px 12px 28px;color:var(--text,#eef1f6);font-size:12px;line-height:1.5}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
.eyebrow{font-size:9px;letter-spacing:.14em;color:#8ee4f1}
h2{margin:2px 0 4px;font-size:16px;font-weight:600}
.pill{flex:0 0 auto;padding:2px 8px;border-radius:999px;background:#2a2414;color:#e9cf8c;font-size:10px}
.pill.live{background:#163a33;color:#9fe8c4}
.lede{margin:0 0 10px;color:var(--text-dim,#aab);font-size:11px}
.nav,.buttons,.seg{display:flex;gap:6px;margin:8px 0}
.card{margin:10px 0;padding:12px;border-radius:10px;background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.06)}
.card-head{display:flex;align-items:center;justify-content:space-between}
h3{margin:0;font-size:13px;font-weight:600}
.quick{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:10px 0}
button{flex:1;padding:7px 8px;border:1px solid #2f5560;border-radius:7px;background:#16303a;color:#cfe3e6;font-size:11px;cursor:pointer;transition:background .15s,border-color .15s}
button:hover:not(:disabled){border-color:#8ee4f1}
button:disabled{opacity:.45;cursor:not-allowed}
.quick button.on,.seg button.on{background:#8ee4f1;border-color:#8ee4f1;color:#0c2229;font-weight:600}
.nav button,.buttons button:not(.ghost){background:#cfeb9b;border-color:#cfeb9b;color:#14251a}
button.ghost{background:transparent}
.row{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:10px 0;color:var(--text-dim,#aab);font-size:11px}
.row small{margin-right:auto;color:var(--text-faint,#889);font-size:10px}
select,input[type=date]{max-width:190px;padding:5px 6px;border:1px solid #2f5560;border-radius:6px;background:#122a33;color:#e3eee8;font:11px system-ui}
.ramp{height:8px;margin-top:6px;border-radius:4px}
.range{display:flex;justify-content:space-between;margin-top:4px;color:var(--text-faint,#889);font-size:10px}
.note{margin:8px 0 0;color:var(--text-faint,#889);font-size:10px}
.error{color:#edbb88;font-size:11px}
.switch{position:relative;width:36px;height:20px;cursor:pointer}
.switch input{position:absolute;opacity:0;inset:0;margin:0;cursor:pointer}
.switch span{position:absolute;inset:0;border-radius:999px;background:#2b3c43;transition:background .2s}
.switch span::after{content:'';position:absolute;top:3px;left:3px;width:14px;height:14px;border-radius:50%;background:#dfe9ec;transition:transform .2s}
.switch input:checked+span{background:#3fb8a3}
.switch input:checked+span::after{transform:translateX(16px)}
.fold{padding:0 12px}
.fold>summary{display:flex;align-items:baseline;gap:8px;padding:11px 0;list-style:none;cursor:pointer;font-size:12px;font-weight:600;color:var(--text,#eef1f6)}
.fold>summary::-webkit-details-marker{display:none}
.fold>summary::before{content:'›';color:#8ee4f1;transition:transform .15s}
.fold[open]>summary::before{transform:rotate(90deg)}
.fold>summary small{margin-left:auto;font-weight:400;font-size:10px;color:var(--text-faint,#889)}
.fold[open]{padding-bottom:12px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:10px}
.stats div{padding:6px 8px;border-radius:7px;background:rgba(255,255,255,.04);color:var(--text-faint,#889);font-size:10px}
.stats b{display:block;color:var(--text,#eef1f6);font-size:14px;font-weight:600}
.spark{width:100%;height:50px;margin-top:8px}
.spark polyline{fill:none;stroke:#8ee4f1;stroke-width:2;vector-effect:non-scaling-stroke}
dl{margin:10px 0 0}dt{margin-top:8px;font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:var(--text-faint,#889)}dd{margin:2px 0;font:10px ui-monospace,monospace;color:var(--text-dim,#aab)}
a{color:#8ee4f1;font-size:11px}
</style>
