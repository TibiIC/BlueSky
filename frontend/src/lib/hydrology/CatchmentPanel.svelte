<script lang="ts">
 import {untrack} from 'svelte';import type {Globe} from '../globe/viewer.ts';import type {Frame} from '../weather/terra.ts';import {attachHydrology,type Network} from './network.ts';
 let {globe,regional,onPlay,onFocus,onPause}:{globe:Globe;regional?:Frame;onPlay:()=>void;onFocus:()=>void;onPause:()=>void}=$props();
 let data=$state.raw<Network|null>(null),error=$state(''),enabled=$state(false),flow=$state(true),selected=$state(0);let api:ReturnType<typeof attachHydrology>|undefined;
 $effect(()=>{const g=globe;const a=untrack(()=>attachHydrology(g,d=>data=d,e=>error=e));api=a;return()=>{a.destroy();api=undefined;};});
 $effect(()=>{const f=regional;untrack(()=>api?.updateFrame(f));});
 const basin=$derived(data?.basins.find(b=>b.id===selected));const modeled=$derived(regional?.catchments?.basins.find(b=>b.id===selected));const rivers=$derived(selected?data?.rivers.filter(r=>r.basin_ids.includes(selected)):data?.rivers);
 function pickBasin(id:number){selected=id;api?.select(id);enabled=true;toggle();onFocus();api?.focus();}
 function toggle(){api?.setEnabled(enabled);if(enabled&&flow)onPlay();}
</script>
<details class="catchment"><summary>Rivers &amp; catchments <small style="font-weight:400;color:var(--text-faint,#889);font-size:10px">real HydroSHEDS network</small></summary>
<label>Catchment layer<input type="checkbox" bind:checked={enabled} onchange={toggle}/></label>
{#if error}<p role="alert">{error}</p>{:else if data}
<p>{data.basins.length} real basin polygons · {data.rivers.length.toLocaleString()} larger river reaches in the Nordic domain.</p>
<div class="places">{#each data.places??[] as place}<button onclick={()=>pickBasin(place.basin_id)}>Near {place.name}</button>{/each}</div>
<label>Basin<select bind:value={selected} onchange={()=>api?.select(Number(selected))}><option value={0}>All catchments</option>{#each data.basins as b}<option value={b.id}>{b.id} · {b.area_km2.toFixed(0)} km²</option>{/each}</select></label>
<button onclick={()=>{onFocus();api?.focus();}}>Focus basin / Nordics</button>
<label>Animate downstream flow<input type="checkbox" bind:checked={flow} onchange={()=>{api?.setFlow(flow);if(flow&&enabled)onPlay();}}/></label>
<button onclick={onPause}>{regional?.controls.paused?'Resume simulation':'Pause simulation'}</button>
<p>Clock: {regional?.sim_time?.slice(0,19)} UTC · {regional?.controls.speed??1}×{regional?.controls.paused?' · PAUSED':''}</p>
{#if basin}<p>Basin {basin.id} → {basin.next_down||'outlet / sink'}<br>{rivers?.length??0} mapped river reaches intersect this basin.<br>Regional model overlap: {basin.modeled_area_km2.toFixed(0)} km²</p>{/if}
{#if basin}<details><summary>River reach IDs in this basin</summary><p>Source contains IDs rather than river names. Showing up to 30 intersecting reaches.</p>{#each (rivers??[]).slice(0,30) as r}<p>Reach {r.id} → {r.next_down||'outlet'} · long-term Q {r.mean_discharge_m3_s.toFixed(1)} m³/s</p>{/each}</details>{/if}
{#if modeled}<p>Modeled runoff contribution leaving basin: <b>{modeled.outflow_m3_s.toFixed(2)} m³/s</b><br>Routing storage: {modeled.storage_m3.toFixed(0)} m³</p>{/if}
<p>{regional?.catchments?.method}<br>{regional?.catchments?.notice}</p>
<p>Last routing balance residual: {regional?.catchments?.budget?.residual_m3?.toExponential(2)??'Waiting'} m³.</p>
<p>White particles follow verified downstream reach connections. Velocity = long-term discharge / assumed cross-sectional area, limited to 0.1–3 m/s, displayed at the simulation speed. These are illustrative trajectories, not live gauged river velocities; tracers reseed at exits. Basin routing uses evolving modeled runoff/drainage with a 6-hour storage timescale.</p>
<p>{data.notice}</p><p>{data.source}</p><a href="https://data.hydrosheds.org/file/technical-documentation/HydroSHEDS_TechDoc_v1_4.pdf" target="_blank" rel="noreferrer">Source documentation & licence ↗</a>
{:else}<p>Loading real river topology…</p>{/if}
</details>
<style>.catchment{margin:10px 0;padding:0 12px;border-radius:10px;background:rgba(255,255,255,.035);border:1px solid rgba(255,255,255,.06)}.catchment[open]{padding-bottom:12px}summary{padding:11px 0;font-size:12px;font-weight:600;color:var(--text,#eef1f6);cursor:pointer}p{font-size:10px;color:#abc0c5;line-height:1.6}label{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:11px;margin:12px 0}select{max-width:145px;background:#17333c;color:#e3eee8;border:1px solid #426772;padding:5px}.places{display:flex;gap:6px;margin:10px 0}.places button{font-size:10px}button{width:100%;padding:7px;background:#16303a;color:#cfe3e6;border:1px solid #2f5560;border-radius:7px;cursor:pointer;font-size:11px}a{font-size:10px;color:#8ee4f1}</style>
