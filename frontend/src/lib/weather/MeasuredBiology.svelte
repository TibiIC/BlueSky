<script lang="ts">
 import { onMount } from 'svelte';
 import type { Globe } from '../globe/viewer.ts';
 type Sample={id:string;date:string;lat:number;lon:number;asv_richness:number;shannon_reads:number;sequence_reads:number;gravimetric_water_g_g:number|null;depth_min_m:number;depth_max_m:number;ena_sample:string};
 type Dataset={schema:string;title:string;sample_count:number;record_count:number;source_url:string;license:string;citation:string;metrics_notice:string;coverage_notice:string;time_notice:string;samples:Sample[]};
 let {globe,onFocus}:{globe:Globe;onFocus:()=>void}=$props();
 let data=$state<Dataset|null>(null),error=$state(''),show=$state(false),selected=$state('');
 const sample=$derived(data?.samples.find(s=>s.id===selected));
 onMount(()=>{let disposed=false;fetch('/data/biology/kungsangen.json').then(r=>{if(!r.ok)throw Error('Measured sample data unavailable');return r.json();}).then((d:Dataset)=>{if(d.schema!=='terra.measured-biology.v1'||!d.samples?.length)throw Error('Invalid measured data');if(!disposed){data=d;selected=d.samples[0].id;}}).catch(e=>{if(!disposed)error=String(e);});return()=>{disposed=true;};});
 $effect(()=>{if(!data)return;const s=data.samples[0],{viewer,C}=globe;const entity=viewer.entities.add({name:'Measured fungal DNA · Kungsängen · 2016',show,position:C.Cartesian3.fromDegrees(s.lon,s.lat,16000),point:{pixelSize:14,color:C.Color.CYAN,outlineColor:C.Color.WHITE,outlineWidth:2},label:{text:'Measured fungal DNA · 2016',font:'12px sans-serif',showBackground:true,pixelOffset:new C.Cartesian2(0,-24),distanceDisplayCondition:new C.DistanceDisplayCondition(0,7000000)}});return()=>{viewer.entities.remove(entity);};});
 function focus(){if(!data)return;show=true;onFocus();const s=data.samples[0];globe.viewer.camera.flyTo({destination:globe.C.Cartesian3.fromDegrees(s.lon,s.lat,180000)});}
</script>
<details class="biology"><summary>Measured soil biology · Sweden</summary>
<p class="badge">REAL SAMPLED DATA · HISTORICAL LAB RESULTS</p>
{#if error}<p role="alert">{error}</p>{:else if data}
<p>{data.title}<br>{data.sample_count} samples · {data.record_count} fungal DNA occurrence records</p>
<label><span>Measured fungal DNA (2016)</span><input type="checkbox" bind:checked={show}/></label>
<button onclick={focus}>Show measured Swedish site</button>
<p>{data.time_notice}</p>
<label>Sample <select bind:value={selected}>{#each data.samples as s}<option value={s.id}>{s.id}</option>{/each}</select></label>
{#if sample}
<dl><dt>Collected</dt><dd>{sample.date}</dd><dt>Depth</dt><dd>{sample.depth_min_m*100}–{sample.depth_max_m*100} cm</dd><dt>Observed fungal ASVs</dt><dd>{sample.asv_richness}</dd><dt>Shannon index (reads)</dt><dd>{sample.shannon_reads.toFixed(3)}</dd><dt>Sequence reads</dt><dd>{sample.sequence_reads.toLocaleString()}</dd><dt>Measured water content</dt><dd>{sample.gravimetric_water_g_g??'Not supplied'} g/g dry soil</dd></dl>
<p>Gravimetric water content is a different quantity from the model’s volumetric soil moisture. Sequence reads are not organism counts.</p>
<a href={sample.ena_sample} target="_blank" rel="noreferrer">ENA sample record ↗</a>
{/if}
<p>{data.metrics_notice}</p><p>{data.coverage_notice}</p>
<p class="source">{data.citation}<br>{data.license}</p>
<div class="links"><a href={data.source_url} target="_blank" rel="noreferrer">Study & methods ↗</a><a href="/data/biology/kungsangen.json" download>Download derived sample data</a></div>
{:else}<p>Loading measured sample data…</p>{/if}
<p>Broader European bacterial/fungal data: <a href="https://esdac.jrc.ec.europa.eu/content/soil-biodiversity-dna-bacteria-and-fungi" target="_blank" rel="noreferrer">LUCAS 2018 ↗</a> (metadata registration required; not yet integrated).</p>
</details>
<style>
.biology{border:1px solid #3b6d79;border-radius:5px;margin:12px 0;padding:10px}summary{cursor:pointer;color:#8ee4f1;font-size:12px;font-weight:600}p{font-size:10px;line-height:1.6;color:#abc0c5}.badge{color:#8ee4f1;font-size:9px;letter-spacing:.5px}label{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:11px;margin:12px 0}button{width:100%;background:#a4e8ed;border:0;border-radius:4px;color:#10272d;padding:8px;cursor:pointer}select{background:#17333c;color:#e3eee8;border:1px solid #426772;border-radius:3px;padding:5px}dl{display:grid;grid-template-columns:1fr auto;gap:7px;margin:14px 0;font-size:10px}dt{color:#abc0c5}dd{margin:0;color:#e3eee8}.source{font-size:9px}a{font-size:10px;color:#8ee4f1}.links{display:grid;gap:8px}
</style>
