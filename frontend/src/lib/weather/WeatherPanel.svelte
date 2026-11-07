<script lang="ts">
 import MeasuredBiology from './MeasuredBiology.svelte';
 import ScenarioPanel from './ScenarioPanel.svelte';
 import FarmPanel from '../farms/FarmPanel.svelte';
 import { untrack } from 'svelte';
 import type { Globe } from '../globe/viewer.ts';
 import { attachTerra, ranges, rgb, differenceRanges, differenceRgb, comparableFields, riskFields, type ComparisonView, type Field, type Status } from './terra.ts';
 let { globe }: {globe:Globe} = $props();
 let status=$state<Status>({regionalConnected:false,globalConnected:false});
 let field=$state<Field>('moisture_g_m3');
 let error=$state('');
 let rotateEarth=$state(false);
 let visible=$state(true);let focusMarkers=$state(true);
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
 let expanded=$state(typeof window !== 'undefined' && window.innerWidth > 900);
 let api:ReturnType<typeof attachTerra>|undefined;
 const options: [Field,string][]=[['temp_c','Temperature · global'],['precip_mm_h','Hourly rain · global'],['rain_day_mm','UTC-day rain · global'],['wind','Wind · global'],['moisture_g_m3','Moisture · global'],['frost_pct','Air frost ≤0°C · crop screen'],['heat_pct','Heat ≥28°C · crop screen'],['heavy_rain_pct','Wet day ≥20mm · crop screen'],['wind_risk_pct','Wind ≥12m/s · crop screen'],['soil_fraction','Soil water · Nordic model'],['snow_water_mm','Snow water · Nordic model'],['crop_stress','Crop water stress (FAO-56) · Nordic model']];

 $effect(()=>{const g=globe;let last=performance.now();return g.viewer.clock.onTick.addEventListener(()=>{const now=performance.now(),dt=Math.min(.1,(now-last)/1000);last=now;if(rotateEarth){g.viewer.camera.rotate(g.C.Cartesian3.UNIT_Z,.025*dt);g.viewer.scene.requestRender();}});});
 $effect(()=>{const target=globe;const connection=untrack(()=>attachTerra(target,s=>status=s));api=connection;return()=>{connection.destroy();api=undefined;};});
 async function control(body:Record<string,number|boolean>){try{await api?.control(body);error='';}catch(e){error=String(e);}}
 const utc=(t:string|null|undefined)=>t?t.slice(0,19).replace('T',' ')+' UTC':'Never / synthetic';
</script>
<section class="weather" class:collapsed={!expanded} aria-label="TERRA weather controls">
 <header><button class="expand" aria-label={expanded?'Collapse data sidebar':'Open data sidebar'} aria-expanded={expanded} onclick={()=>expanded=!expanded}>{expanded?'−':'+'}</button><strong>EARTH / DATA</strong><span class:live={status.regionalConnected&&status.globalConnected}>{status.regionalConnected&&status.globalConnected?'● CONNECTED':'○ RECONNECTING'}</span></header>
 <div class="mode-label">{status.scenarioActive?'HYPOTHETICAL SCENARIO · FINAL SOIL STATE':comparing?compareView==='difference'?'LIVE − HISTORICAL DIFFERENCE':compareView==='historical'?'HISTORICAL WEATHER COMPARISON':'LIVE WEATHER COMPARISON':timeline?.mode==='historical'?'HISTORICAL DATA + SIMULATION':'LIVE FORECAST + SIMULATION'}</div>
 <label class="climate-toggle"><span>Weather layers <small>Global coverage · finer Nordic detail</small></span><input aria-label="Weather layers" type="checkbox" bind:checked={visible} onchange={()=>api?.setVisible(visible)} /></label>
 {#if expanded}
 <label><span>Rotate Earth <small>presentation motion</small></span><input type="checkbox" bind:checked={rotateEarth}/></label>
 <div class="apetit-focus"><strong>APETIT / CROP WEATHER</strong><p>Global display: 10°. Nordic display cells: ~35–68 km; forcing uses 25 sparse locations (~250–500 km spacing).<br>Peas, vegetables and oilseed growing conditions.</p><div class="buttons"><button onclick={()=>{rotateEarth=false;globe.viewer.camera.flyTo({destination:globe.C.Cartesian3.fromDegrees(22,25,24000000)});}}>Whole world</button><button onclick={()=>{rotateEarth=false;globe.viewer.camera.flyTo({destination:globe.C.Cartesian3.fromDegrees(19,59.5,1800000)});}}>Apetit focus</button></div><label><span>Focus markers</span><input type="checkbox" bind:checked={focusMarkers} onchange={()=>api?.setFocusMarkers(focusMarkers)} /></label></div>
 <FarmPanel {globe} regional={status.regional} />
 <label>Field <select bind:value={field} onchange={()=>api?.setLayer(field)}>{#each options.filter(([k])=>!comparing||comparableFields.has(k)) as [key,title]}<option value={key}>{title}</option>{/each}</select></label>
 <div class="ramp" style={`background:linear-gradient(90deg,rgb(${legendColor(Number(legend[0])).join(',')}),rgb(${legendColor((Number(legend[0])+Number(legend[1]))/2).join(',')}),rgb(${legendColor(Number(legend[1])).join(',')}))`}></div><div class="range"><span>{legend[0]}</span><span>{legend[1]} {legend[2]}</span></div>
 {#if riskFields.has(field)&&field!=='crop_stress'}<p class="note">Colored land cells exceed the displayed, illustrative threshold. This is weather screening—not a calibrated crop-damage or yield forecast.</p>{/if}
 {#if field==='crop_stress'}<p class="note">FAO-56 water limitation: 0 = no limitation, 1 = wilting-point limit. Generic soil and crop-calendar assumptions; not measured crop damage.</p>{/if}
 {#if field==='soil_fraction'||field==='snow_water_mm'||field==='crop_stress'}<p class="note">Nordic model only; no global soil/snow simulation is being implied.</p>{/if}
 <MeasuredBiology {globe} onFocus={()=>{rotateEarth=false;}} />
 <ScenarioPanel active={!!status.scenarioActive} onMap={frame=>{if(frame){closeComparison();field='soil_fraction';api?.setLayer(field);}api?.setScenario(frame);}} />
 <details><summary>Live / historical comparison</summary>
 <div class="compare-box">
 <strong>Compare historical and live weather</strong>
 <label>Past date (UTC)<input aria-label="Comparison date" type="date" bind:value={compareDate} min="1950-01-01" max={timeline?.max_history_date} /></label>
 <button disabled={!compareDate||comparison?.loading} onclick={loadComparison}>{comparison?.loading?'Loading comparison…':'Compare with live'}</button>
 {#if comparing}
 <div class="mode-tabs"><button class:chosen={compareView==='live'} onclick={()=>viewComparison('live')}>Live</button><button class:chosen={compareView==='historical'} onclick={()=>viewComparison('historical')}>Historical</button><button class:chosen={compareView==='difference'} onclick={()=>viewComparison('difference')}>Difference</button></div>
 {#if comparison?.ready&&comparison.summary?.[field]}
 {@const s=comparison.summary[field]}
 <div class="compare-values"><span>Live <b>{s.live.toFixed(2)} {ranges[field][2]}</b></span><span>Past <b>{s.historical.toFixed(2)} {ranges[field][2]}</b></span><span>Change <b>{s.difference>=0?'+':''}{s.difference.toFixed(2)} {riskFields.has(field)?'pp':ranges[field][2]}</b></span></div>
 {#if compareView==='difference'}<p class="note">Blue: lower now · white: similar · red: higher now</p>{/if}
 <p class="note">{field==='rain_day_mm'||field==='heavy_rain_pct'?'Complete UTC calendar days':'Same UTC hour'} · Nordic land means<br>Live: {utc(comparison.live_time)}<br>Past: {utc(comparison.historical_time)}</p>
 <p class="note">{comparison.historical_source?.notice} Differences show live minus past weather, not a long-term climate anomaly.</p>
 {/if}
 <button class="secondary" onclick={closeComparison}>Return to physics layers</button>
 {/if}
 {#if comparison?.error}<p class="error" role="alert">{comparison.error}</p>{/if}
 </div>
 </details>
 <details><summary>Data timeline & replay</summary>
 <div class="mode-tabs"><button class:chosen={timeline?.mode!=='historical'&&!historyOpen} onclick={()=>changeTimeline({mode:'live'})}>Live forecast</button><button class:chosen={showHistory} onclick={()=>historyOpen=true}>Historical replay</button></div>
 {#if showHistory}
 <div class="history-controls">
 <label>From (UTC)<input aria-label="Historical start date" type="date" bind:value={startDate} min="1950-01-01" max={timeline?.max_history_date} /></label>
 <label>Through (UTC)<input aria-label="Historical end date" type="date" bind:value={endDate} min={startDate||'1950-01-01'} max={timeline?.max_history_date} /></label>
 <button disabled={timeline?.loading||!startDate||!endDate} onclick={()=>changeTimeline({mode:'historical',start_date:startDate,end_date:endDate})}>{timeline?.loading?'Loading historical data…':'Load period (up to 7 days)'}</button>
 <p class="note">ERA5/ERA5-Land through {timeline?.reanalysis_through??'…'}. More recent days use past model data from the forecast API. Both are labeled; neither is direct station observations.</p>
 {#if timeline?.summary&&timeline.mode==='historical'}
 <div class="history-summary"><p class="note">{status.regional?.source.notice}</p><strong>{timeline.range?.join(' → ')}</strong><p>Mean land precipitation: {timeline.summary.precipitation_total_mm.toFixed(1)} mm<br>Mean air temperature range: {timeline.summary.min_mean_temperature_c.toFixed(1)}–{timeline.summary.max_mean_temperature_c.toFixed(1)} °C<br>Peak mean wind: {timeline.summary.peak_mean_wind_ms.toFixed(1)} m/s</p>
 <svg viewBox="0 0 240 55" role="img" aria-label="Historical hourly precipitation across the selected period"><polyline points={rainPoints(timeline.summary.series)} fill="none" stroke="#cfea9b" stroke-width="2" /></svg><small>Hourly regional land-mean precipitation · historical forcing</small>
 <p>Replay position: {(timeline.position_seconds/3600).toFixed(1)} hours. Use speed and pause below.</p></div>
 {/if}
 </div>
 {/if}
 {#if timeline?.error}<p role="alert" class="error">Historical data: {timeline.error}</p>{/if}
 </details>
 <details><summary>Physics & data provenance</summary>
 <p>Whole Earth · coarse weather<br><b>Finland + Sweden · finer regional model</b></p>
 <div class="buttons"><button onclick={()=>{rotateEarth=false;globe.viewer.camera.flyTo({destination:globe.C.Cartesian3.fromDegrees(22,25,24000000)});}}>Whole Earth</button><button onclick={()=>{rotateEarth=false;globe.viewer.camera.flyTo({destination:globe.C.Cartesian3.fromDegrees(21.5,63,2600000)});}}>Nordics</button></div>


 <dl><dt>PHYSICS ENGINE</dt><dd>Regional v{status.regional?.engine_version??'—'} / finite-volume transport</dd><dt>SOIL INITIALIZATION</dt><dd>{status.regional?.initialization?.kind??'Waiting'} · {status.regional?.initialization?.soil_seeded_cells??0} cells</dd><dt>TRANSPORT WINDS</dt><dd>{status.regional?.physics?.transport_wind??'Waiting'}</dd><dt>NORDIC FORCING</dt><dd>{status.regional?.source.mode??'Waiting'}</dd><dt>GLOBAL FORCING</dt><dd>{status.global?.source.mode??'Waiting'}</dd><dt>SIMULATION CLOCK</dt><dd>{utc(status.regional?.sim_time)}</dd><dt>LAST NORDIC / GLOBAL FETCH</dt><dd>{utc(status.regional?.source.fetched_at)}<br>{utc(status.global?.source.fetched_at)}</dd></dl>
 {#if !comparing}<label>Speed <select value={String(status.regional?.controls.speed??1)} onchange={e=>control({speed:+e.currentTarget.value})}><option value="1">1× wall time</option><option value="60">60×</option><option value="600">600× demo</option><option value="3600">3600×</option></select></label>
 <label>Nordic precipitation <select value={String(status.regional?.controls.rain_scale??1)} onchange={e=>control({rain_scale:+e.currentTarget.value})}><option value="0">0× dry scenario</option><option value="1">1× forecast</option><option value="2">2× wet scenario</option><option value="4">4× extreme scenario</option></select></label>
 <div class="buttons"><button onclick={()=>control({paused:!status.regional?.controls.paused})}>{status.regional?.controls.paused?'Resume':'Pause'}</button><button onclick={()=>control({reset:true})}>{timeline?.mode==='historical'?'Restart period':'Reset to now'}</button></div>
 {/if}
 {#if status.regional?.at_forecast_end}<p class="error">Forecast horizon reached; simulation held.</p>{/if}
 {#if error||status.error}<p class="error" role="alert">{error||status.error}</p>{/if}
 {#if status.regional?.source.last_error||status.global?.source.last_error}<p class="error">API unavailable for at least one grid. Its last forecast or synthetic fallback remains active.</p>{/if}
 <p class="note">Nordic: 25×29 grid / 25 API samples.<br>Global: 36×18 grid / 24 API samples.<br>Polar bands use sparse-sample interpolation; no polar circulation solver.<br>{timeline?.mode==='historical'?'Hourly historical forcing · selected period':'Hourly forecasts · fetched every 15 min.'}<br>1 Hz feed · animated between frames.<br>Forecasts are not observations. Nordic: conservative transport + snow/soil water balance. Wind is forecast forcing. Soil is initialized from forecast soil moisture. Nordic rain scenarios do not alter the global layer.</p>
<p class="note">Säkylä/Bjuv markers are approximate town centers; actual contract-farm data has not been supplied. <a href="https://apetit.fi/en/sustainability/cultivation-and-experimental-work/" target="_blank" rel="noreferrer">Apetit context ↗</a></p>
 <a href="http://127.0.0.1:8765" target="_blank" rel="noreferrer">Open physics dashboard ↗</a>
 </details>
{:else}<p>{timeline?.mode==='historical'?timeline.range?.join(' → '):'Global atmosphere + finer Nordic weather'}</p><div class="buttons"><button onclick={()=>{rotateEarth=false;globe.viewer.camera.flyTo({destination:globe.C.Cartesian3.fromDegrees(22,25,24000000)});}}>Whole Earth</button><button onclick={()=>{rotateEarth=false;globe.viewer.camera.flyTo({destination:globe.C.Cartesian3.fromDegrees(21.5,63,2600000)});}}>Nordics</button></div>{/if}
</section>
<style>
.weather.collapsed{width:44px;padding:10px 4px}.weather.collapsed> :not(header){display:none}.weather.collapsed header strong,.weather.collapsed header span{display:none}.weather.collapsed header{justify-content:center}.weather.collapsed header .expand{padding:8px}details{border-top:1px solid #385158;padding:12px 0}summary{cursor:pointer;color:#cfeb9b;font-size:12px}

.apetit-focus{padding:10px;background:#122c31;border:1px solid #37534c;border-radius:5px;font-size:10px}.apetit-focus>strong{font-size:9px;letter-spacing:1px;color:#cfeb9b}.apetit-focus p{font-size:9px}.apetit-focus button{font-size:10px}

.compare-box{padding:10px;background:#0e222b;border:1px solid #385158;border-radius:5px;margin:10px 0}.compare-box>strong{font-size:10px}.compare-box input{max-width:140px;background:#18313b;color:#e3eee8;border:1px solid #385158;border-radius:4px;padding:4px;font:10px system-ui}.compare-box>button{width:100%;font-size:10px}.compare-values{display:grid;gap:7px}.compare-values span{display:flex;justify-content:space-between;font-size:10px}.compare-values b{font:10px monospace}.secondary{background:#18313b!important;color:#cfeb9b!important;border:1px solid #385158!important}.climate-toggle{padding:8px 0;border-top:1px solid #385158;border-bottom:1px solid #385158}.climate-toggle small{display:block;color:#a3b6b8;font-size:8px}

.mode-tabs{display:flex;gap:6px;margin:14px 0}.mode-tabs button{background:#18313b;color:#a3b6b8;border:1px solid #385158;font-size:10px}.mode-tabs button.chosen{background:#cfeb9b;color:#14251a}.mode-label{font-size:9px;color:#cfeb9b;letter-spacing:.8px;margin:12px 0}.history-controls{padding:10px;background:#0e222b;border-radius:5px}.history-controls label{font-size:10px}.history-controls input{width:140px;background:#18313b;color:#e3eee8;border:1px solid #385158;border-radius:4px;padding:4px;font-size:10px}.history-controls>button{width:100%;font-size:10px}.history-controls button:disabled{opacity:.5;cursor:wait}.history-summary{border-top:1px solid #385158;padding-top:10px;font-size:10px}.history-summary svg{width:100%;height:55px}.history-summary small{font-size:8px;color:#a3b6b8}

.weather{position:relative;flex:0 0 auto;box-sizing:border-box;width:330px;height:100%;overflow:auto;padding:18px;background:rgba(8,23,30,.94);border:1px solid #385158;border-radius:10px;color:#e3eee8;font:11px system-ui;backdrop-filter:blur(12px)}header{display:flex;justify-content:space-between;gap:8px;font-size:9px;letter-spacing:.8px}header .expand{flex:0;padding:0 5px;background:transparent;color:#cfeb9b;font-size:16px}header span{font-size:8px;color:#e3bc80}header .live{color:#cfea9b}p{line-height:1.6;color:#a3b6b8}b{color:#d3ebba;font-weight:500}label{display:flex;align-items:center;justify-content:space-between;margin:14px 0;gap:12px}select{max-width:180px;color:#e3eee8;background:#152f38;border:1px solid #3a555d;border-radius:4px;font:11px system-ui;padding:5px}.ramp{height:5px;background:linear-gradient(90deg,#163e72,#d2f291);margin-top:16px}.range{display:flex;justify-content:space-between;margin-top:5px;color:#a3b6b8;font-size:9px}dt{font-size:8px;letter-spacing:.8px;color:#a3b6b8;margin-top:12px}dd{margin:4px 0;font:10px monospace;line-height:1.6}.buttons{display:flex;gap:8px}button{flex:1;background:#cfeb9b;border:0;border-radius:4px;padding:7px;color:#14251a;cursor:pointer}.note{font-size:9px}.error{color:#edbb88}a{color:#cfeb9b;font-size:10px}@media(max-width:650px){.weather{width:min(300px,80vw);padding:12px}}
</style>
