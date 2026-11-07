import {sampleGrid,smoothRamp} from './interpolation.mjs';
import type { Polyline } from 'cesium';
import { createFieldOverlay } from './overlay.ts';
import type { Globe } from '../globe/viewer.ts';

export type Field = 'rain_bands' | 'moisture_g_m3' | 'precip_mm_h' | 'soil_fraction' | 'temp_c' | 'snow_water_mm' | 'crop_stress' | 'wind' | 'rain_day_mm' | 'frost_pct' | 'heat_pct' | 'wind_risk_pct' | 'heavy_rain_pct';
export interface Timeline {
 mode:'live'|'historical';loading:boolean;error:string|null;request_id:number;max_history_date:string;reanalysis_through:string;range:[string,string]|null;position_seconds:number;start_time:string|null;end_time:string;
 summary?:{precipitation_total_mm:number;min_mean_temperature_c:number;max_mean_temperature_c:number;peak_mean_wind_ms:number;series:{time:string;temperature_c:number;precip_mm_h:number;wind_ms:number}[]}|null;
}
export interface Frame {
 catchments?:{notice:string;method:string;budget?:{residual_m3:number};basins:{id:number;outflow_m3_s:number;storage_m3:number;modeled_area_km2:number}[]};physics?:{transport_wind?:string};timeline?:Timeline;
 initialization?: {kind:string;soil_seeded_cells?:number;land_cells?:number}; atmosphere_budget_kg?: {relative_residual:number}; ready?: boolean; engine_version?: string; schema: string; sim_time: string; published_at: string;
 source: { notice?:string;forcing_kind?:string; mode: string; fetched_at: string | null; last_error: string | null; forecast_id: string; valid_end: string };
 grid: { nx: number; ny: number; west: number; east: number; south: number; north: number;land_mask?:boolean[];periodic_longitude?:boolean };
 fields: Record<string, (number | null)[]>;
 controls: { speed: number; paused: boolean; rain_scale: number; capacity_mm?: number };
 at_forecast_end?: boolean;
}
export type ComparisonView='live'|'historical'|'difference';
export interface WeatherComparison {
 ready:boolean;loading:boolean;error:string|null;date:string|null;notice?:string;live_time?:string;historical_time?:string;
 live_source?:{notice:string};historical_source?:{notice:string};
 global?:{ready:boolean;grid?:Frame['grid'];live?:Record<string,number[]>;historical?:Record<string,number[]>;difference?:Record<string,number[]>};
 grid?:Frame['grid'];live?:Record<string,number[]>;historical?:Record<string,number[]>;difference?:Record<string,number[]>;
 summary?:Record<string,{live:number;historical:number;difference:number}>;
}
export const riskFields=new Set<Field>(['frost_pct','heat_pct','wind_risk_pct','heavy_rain_pct','crop_stress']);
export const comparableFields=new Set<Field>(['temp_c','precip_mm_h','wind','rain_day_mm','frost_pct','heat_pct','wind_risk_pct','heavy_rain_pct']);
export const differenceRanges:Record<string,number>={rain_day_mm:20,frost_pct:100,heat_pct:100,wind_risk_pct:100,heavy_rain_pct:100,temp_c:10,precip_mm_h:3,wind:10};
export function differenceRgb(value:number,limit:number):[number,number,number]{
 const t=Math.min(1,Math.abs(value)/limit),end=value<0?[65,122,216]:[226,103,67];
 return [235,239,231].map((v,i)=>Math.round(v+(end[i]-v)*t)) as [number,number,number];
}
export interface Status {scenarioActive?:boolean;comparison?:WeatherComparison;comparisonView?:ComparisonView|null; regional?: Frame; global?: Frame; regionalConnected: boolean; globalConnected: boolean; error?: string }
export const ranges: Record<Field, [number, number, string]> = {
 rain_bands:[0,3,'mm/h'],
 rain_day_mm:[0,30,'mm/day'],frost_pct:[0,100,'%'],heat_pct:[0,100,'%'],wind_risk_pct:[0,100,'%'],heavy_rain_pct:[0,100,'%'],
 snow_water_mm: [0,150,'mm'], crop_stress: [0,1,'1 − Ks'], moisture_g_m3: [0, 12, 'g/m³'], precip_mm_h: [0, 3, 'mm/h'], soil_fraction: [0, 1, 'fraction'], temp_c: [-15, 30, '°C'], wind: [0, 20, 'm/s']
};
export function rgb(field: Field, value: number): [number, number, number] {
 const [lo, hi] = ranges[field], t = Math.max(0, Math.min(1, (value-lo)/(hi-lo)));
 const a = field==='rain_bands'?[70,155,255]:riskFields.has(field)?[235,239,231]:field === 'soil_fraction' ? [164, 95, 52] : [22, 62, 114], b = field==='rain_bands'?[211,95,245]:riskFields.has(field)?[226,103,67]:[210,242,145];
 return a.map((v,i) => Math.round(v+(b[i]-v)*t)) as [number, number, number];
}
export function attachTerra(globe: Globe, onStatus: (state: Status) => void) {
 const { C, viewer } = globe;
 const state: Status = { regionalConnected: false, globalConnected: false };
 let comparisonView:ComparisonView|null=null;let comparisonEnabled=false;let comparisonBusy=false;
 let scenarioFrame:Frame|null=null;
 let windOnRain=true;
 let selected: Field = 'moisture_g_m3', visible = true, disposed = false, previous = performance.now();
 const overlays: Partial<Record<'regional'|'global',ReturnType<typeof createFieldOverlay>>> = {};
 const buffers={regional:[document.createElement('canvas'),document.createElement('canvas')],global:[document.createElement('canvas'),document.createElement('canvas')]};
 const bufferIndex={regional:0,global:0};
 const previousFrames:Partial<Record<'regional'|'global',Frame>>={};const arrived={regional:0,global:0};
 const latestPublished={regional:0,global:0};
 const pendingPaint=new Set<'regional'|'global'>();let paintRequest=0;
 function queuePaint(kind:'regional'|'global'){
  pendingPaint.add(kind);if(paintRequest||disposed)return;
  paintRequest=requestAnimationFrame(()=>{paintRequest=0;for(const k of pendingPaint)paint(k);pendingPaint.clear();});
 }
 const points = viewer.scene.primitives.add(new C.PolylineCollection());
 const particles: { kind:'regional'|'global';lon: number; lat: number; line: Polyline; trail:{lon:number;lat:number;age:number}[]; elapsed:number }[] = [];
 const timestamps = { regional: 0, global: 0 };
 // Add a weather credit independently from existing Cesium/imagery credits.
 const credit = new C.Credit('Weather: Open-Meteo (CC BY 4.0) · TERRA simulated moisture / soil', true);
 viewer.creditDisplay.addStaticCredit(credit);
 function paint(kind: 'regional'|'global') {
  let f = kind==='regional'&&scenarioFrame?scenarioFrame:state[kind]; if (!f || disposed) return;
  const compare=kind==='global'?state.comparison?.global:state.comparison;
  if(comparisonView){
   if(!compare?.ready||!compare.grid||!compare[comparisonView]){overlays[kind]?.setVisible(false);return;}
   f={...f,grid:compare.grid,fields:compare[comparisonView]!,ready:true};
  }
  if(f.ready===false){overlays[kind]?.setVisible(false);return;}
  if ((selected === 'soil_fraction'||selected === 'snow_water_mm'||selected === 'crop_stress') && kind === 'global') { overlays.global?.setVisible(false); return; }
  const { nx,ny,west,east,south,north }=f.grid;
  bufferIndex[kind]=1-bufferIndex[kind];
  const canvas=buffers[kind][bufferIndex[kind]];
  // Two pixels per center interval: first/last cells have half width, so centers georeference exactly.
  canvas.width = kind === 'global' ? nx*2 : (nx-1)*2;
  canvas.height = kind === 'global' ? ny*2 : (ny-1)*2;
  const ctx=canvas.getContext('2d')!;
  for(let j=0;j<ny;j++)for(let i=0;i<nx;i++) {
   const n=j*nx+i;let raw=selected==='rain_bands'?(kind==='regional'?(f.fields.rain_pattern_mm_h??f.fields.precip_mm_h)?.[n]:f.fields.precip_mm_h?.[n]):selected==='wind'?(comparisonView?f.fields.wind[n]:Math.hypot(f.fields.u_ms[n] ?? 0,f.fields.v_ms[n] ?? 0)):f.fields[selected]?.[n];
   if(raw===null||raw===undefined)continue;
   if(selected==='rain_bands'&&kind==='regional'&&!f.controls.paused&&!comparisonView){const old=previousFrames.regional?.fields.rain_pattern_mm_h?.[n];if(old!=null)raw=old+(raw-old)*Math.min(1,(performance.now()-arrived.regional)/1000);}
   if(riskFields.has(selected)&&f.grid.land_mask?.[n]!==true)continue;
   if((selected==='rain_day_mm'||selected==='heavy_rain_pct')&&(f.fields.rain_day_coverage_h?.[n]??0)<24)continue;
   const value=(selected==='precip_mm_h'||selected==='rain_bands')?raw*(comparisonView?1:f.controls.rain_scale):raw;
   if(selected==='rain_bands'&&value<.1)continue;
   const col=comparisonView==='difference'?differenceRgb(value,differenceRanges[selected]??10):rgb(selected,value);const alpha=selected==='rain_bands'?.55+.3*Math.min(1,value/3):riskFields.has(selected)?(Math.abs(value)>0?.75:0):.63;ctx.fillStyle=`rgba(${col.join(',')},${alpha})`;
   if(kind==='global')ctx.fillRect(i*2,(ny-1-j)*2,2,2);
   else { const x=Math.max(0,i*2-1),y=Math.max(0,(ny-1-j)*2-1);ctx.fillRect(x,y,Math.min(canvas.width,i*2+1)-x,Math.min(canvas.height,(ny-1-j)*2+1)-y); }
  }
  // Interpolate scalar values before colouring: visual refinement, not extra forecast resolution.
  if(['rain_bands','precip_mm_h','temp_c','wind','moisture_g_m3'].includes(selected)){
   const values=Array.from({length:nx*ny},(_,n)=>{
    let v=selected==='rain_bands'?(kind==='regional'?(f.fields.rain_pattern_mm_h??f.fields.precip_mm_h)?.[n]:f.fields.precip_mm_h?.[n]):selected==='wind'?(comparisonView?f.fields.wind[n]:Math.hypot(f.fields.u_ms[n]??0,f.fields.v_ms[n]??0)):f.fields[selected]?.[n];
    if(selected==='rain_bands'&&kind==='regional'&&!f.controls.paused&&!comparisonView){const old=previousFrames.regional?.fields.rain_pattern_mm_h?.[n];if(old!=null&&v!=null)v=old+(v-old)*Math.min(1,(performance.now()-arrived.regional)/1000);}
    return v==null?NaN:v;
   });
   canvas.width=kind==='global'?nx*12:(nx-1)*12;canvas.height=(ny-1)*12;
   const image=ctx.createImageData(canvas.width,canvas.height);
   for(let y=0;y<canvas.height;y++)for(let x=0;x<canvas.width;x++){
    const gx=kind==='global'?(x+.5)/canvas.width*nx:(x+.5)/canvas.width*(nx-1),gy=(1-(y+.5)/canvas.height)*(ny-1);
    const raw=sampleGrid(values,nx,ny,gx,gy,kind==='global');if(raw==null)continue;
    const value=(selected==='rain_bands'||selected==='precip_mm_h')?raw*(comparisonView?1:f.controls.rain_scale):raw;
    const color=comparisonView==='difference'?differenceRgb(value,differenceRanges[selected]??10):rgb(selected,value);
    let alpha=selected==='rain_bands'?(.55+.3*Math.min(1,value/3))*smoothRamp(.05,.15,value):.63;
    if(kind==='regional')alpha*=smoothRamp(0,.65,Math.min(gx,nx-1-gx,gy,ny-1-gy));
    const k=(y*canvas.width+x)*4;image.data[k]=color[0];image.data[k+1]=color[1];image.data[k+2]=color[2];image.data[k+3]=Math.round(alpha*255);
   }
   ctx.putImageData(image,0,0);
  }
  // Global centers begin at -180: split at dateline by circularly shifting half a cell.
  if(kind==='global'&&!['rain_bands','precip_mm_h','temp_c','wind','moisture_g_m3'].includes(selected)) { const image=ctx.getImageData(0,0,canvas.width,canvas.height);ctx.clearRect(0,0,canvas.width,canvas.height);ctx.putImageData(image,-1,0);ctx.putImageData(image,canvas.width-1,0); }
  if(!overlays[kind])overlays[kind]=createFieldOverlay(globe,kind,[west,kind==='global'?-90:south,kind==='global'?180:east,kind==='global'?90:north],canvas);
  overlays[kind]!.update(canvas,visible);
 }
 function accept(kind:'regional'|'global',f:Frame){
  const stamp=Date.parse(f.published_at);
  if(!Number.isFinite(stamp)||stamp<latestPublished[kind])return;
  latestPublished[kind]=stamp;
  previousFrames[kind]=state[kind];arrived[kind]=performance.now();state[kind]=f;state[kind==='regional'?'regionalConnected':'globalConnected']=true;
  timestamps[kind]=performance.now();state.error=undefined;queuePaint(kind);onStatus({...state});
 }

 function connect(kind:'regional'|'global',url:string) {
  const es=new EventSource(url);
  es.addEventListener('frame',(event)=>{try {
   const f=JSON.parse((event as MessageEvent).data) as Frame;
   if(!f.schema?.startsWith('terra.')||!f.grid||!f.fields)throw Error('Invalid TERRA frame');
   accept(kind,f);
  }catch(e){state.error=String(e);onStatus({...state});}});
  es.onerror=()=>{state[kind==='regional'?'regionalConnected':'globalConnected']=false;onStatus({...state});};return es;
 }
 const windMaterial=C.Material.fromType('PolylineGlow',{color:C.Color.fromCssColorString('#ddffd1').withAlpha(.8),glowPower:.12,taperPower:.65});
 for(const [kind,count] of [['regional',450],['global',250]] as const)for(let i=0;i<count;i++){
  const lon=kind==='regional'?10+Math.random()*23:-180+Math.random()*360,lat=kind==='regional'?54+Math.random()*17:-85+Math.random()*170;
  particles.push({kind,lon,lat,trail:[],elapsed:0,line:points.add({positions:[],width:1.7,material:windMaterial})});
 }
 const removeTick=viewer.scene.preRender.addEventListener(()=>{
  const now=performance.now(),dt=Math.min(.05,(now-previous)/1000);previous=now;
  points.show=visible&&(selected==='wind'||(selected==='rain_bands'&&windOnRain))&&!scenarioFrame&&!comparisonView;
  if(!points.show)return;
  for(const p of particles){const f=state[p.kind];p.line.show=!!f&&f.ready!==false&&now-timestamps[p.kind]<4000;if(!f||!p.line.show||f.controls.paused||f.at_forecast_end)continue;
   const grid=f.grid,gx=p.kind==='global'?(p.lon-grid.west)/360*grid.nx:(p.lon-grid.west)/(grid.east-grid.west)*(grid.nx-1),gy=(p.lat-grid.south)/(grid.north-grid.south)*(grid.ny-1);
   const u=sampleGrid(f.fields.u_ms,grid.nx,grid.ny,gx,gy,p.kind==='global')??0,v=sampleGrid(f.fields.v_ms,grid.nx,grid.ny,gx,gy,p.kind==='global')??0;
   const elapsed=dt*f.controls.speed,oldLon=p.lon;
   p.lon+=u*elapsed/(111320*Math.cos(p.lat*Math.PI/180));p.lat+=v*elapsed/111320;
   let reseed=false;
   if(p.kind==='global'){p.lon=((p.lon+180)%360+360)%360-180;if(Math.abs(p.lat)>85){p.lat=-85+Math.random()*170;reseed=true;}if(Math.abs(p.lon-oldLon)>180)reseed=true;}
   else if(p.lon<10||p.lon>33||p.lat<54||p.lat>71){p.lon=10+Math.random()*23;p.lat=54+Math.random()*17;reseed=true;}
   if(reseed){p.trail=[];p.elapsed=0;p.line.positions=[];continue;}
   // Seed a short back-traced streamline so live 1× has a visible wind direction immediately.
   if(!p.trail.length){let lon=p.lon,lat=p.lat;const back=[];
    for(let k=0;k<24;k++){
     const x=p.kind==='global'?(lon-grid.west)/360*grid.nx:(lon-grid.west)/(grid.east-grid.west)*(grid.nx-1),y=(lat-grid.south)/(grid.north-grid.south)*(grid.ny-1);
     const bu=sampleGrid(f.fields.u_ms,grid.nx,grid.ny,x,y,p.kind==='global')??0,bv=sampleGrid(f.fields.v_ms,grid.nx,grid.ny,x,y,p.kind==='global')??0;
     lon-=bu*300/(111320*Math.cos(lat*Math.PI/180));lat-=bv*300/111320;
     if(lon<grid.west||lon>(p.kind==='global'?180:grid.east)||lat<grid.south||lat>grid.north)break;
     back.unshift({lon,lat,age:(k+1)*300});
    }p.trail=back;
   }
   for(const t of p.trail)t.age+=elapsed;
   p.trail=p.trail.filter(t=>t.age<=7200);p.elapsed+=elapsed;
   if(p.elapsed>=300){p.trail.push({lon:p.lon,lat:p.lat,age:0});p.elapsed=0;}
   p.line.positions=[...p.trail.map(t=>C.Cartesian3.fromDegrees(t.lon,t.lat,18000)),C.Cartesian3.fromDegrees(p.lon,p.lat,18000)];

  }
 });
 const focusEntities=[
  viewer.entities.add({name:'Nordic higher-detail weather domain',rectangle:{coordinates:C.Rectangle.fromDegrees(10,54,33,71),height:15000,fill:false,outline:true,outlineColor:C.Color.fromCssColorString('#d3ef9c')}}),
  ...[{name:'Säkylä region · Apetit',lon:22.33333,lat:61.03333},{name:'Bjuv region · Apetit',lon:12.91914,lat:56.08372}].map(place=>viewer.entities.add({name:place.name,description:'Approximate town center, not a contract farm boundary or exact facility position.',position:C.Cartesian3.fromDegrees(place.lon,place.lat,20000),point:{pixelSize:7,color:C.Color.fromCssColorString('#ffcf80'),outlineWidth:1,outlineColor:C.Color.BLACK},label:{text:place.name,font:'12px sans-serif',pixelOffset:new C.Cartesian2(0,-18),fillColor:C.Color.fromCssColorString('#ffdf9c'),showBackground:true,backgroundColor:C.Color.fromCssColorString('#10212c'),distanceDisplayCondition:new C.DistanceDisplayCondition(0,7000000)}}))
 ];
 const feeds=[connect('regional','/terra/events'),connect('global','/terra/global-events')];
 const recovering = new Set<string>();
 async function refreshComparison(){
  if(!comparisonEnabled||comparisonBusy||disposed)return;
  comparisonBusy=true;
  try{const r=await fetch('/terra/api/comparison',{signal:AbortSignal.timeout(8000)});if(!r.ok)throw Error('Comparison unavailable');const c=await r.json() as WeatherComparison;if(disposed)return;state.comparison=c;queuePaint('global');queuePaint('regional');onStatus({...state});}
  catch(e){if(!disposed){state.error=String(e);onStatus({...state});}}
  finally{comparisonBusy=false;}
 }
 const rainAnimation=setInterval(()=>{if(selected==='rain_bands'&&visible){queuePaint('global');queuePaint('regional');}},200);
 const comparisonTimer=setInterval(refreshComparison,3000);
 const stale=setInterval(()=>{
  for(const kind of ['regional','global'] as const) {
   if(performance.now()-timestamps[kind]<=4000)continue;
   state[kind==='regional'?'regionalConnected':'globalConnected']=false;onStatus({...state});
   // Some preview/reverse proxies buffer SSE. Recover with the identical snapshot schema.
   if(recovering.has(kind))continue;
   recovering.add(kind);
   fetch(kind==='regional'?'/terra/api/frame':'/terra/api/global-frame', {signal:AbortSignal.timeout(5000)})
    .then(r=>{if(!r.ok)throw Error('Snapshot unavailable');return r.json();})
    .then((f:Frame)=>{if(disposed)return;accept(kind,f);})
    .catch(()=>{/* Retain stale indicator and last field. */}).finally(()=>recovering.delete(kind));
  }
 },1500);
 return {
  setScenario(frame:Frame|null){scenarioFrame=frame;state.scenarioActive=!!frame;queuePaint('regional');onStatus({...state});},
  async compare(day:string){
   const r=await fetch('/terra/api/comparison',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:day})});
   if(!r.ok)throw Error(await r.text());comparisonEnabled=true;state.comparison=await r.json();onStatus({...state});await refreshComparison();
  },
  setComparisonView(view:ComparisonView|null){scenarioFrame=null;state.scenarioActive=false;comparisonView=view;comparisonEnabled=view!==null;state.comparisonView=view;queuePaint('global');queuePaint('regional');onStatus({...state});},
  setWindOnRain(show:boolean){windOnRain=show;},
  setFocusMarkers(show:boolean){focusEntities.forEach(e=>e.show=show);},
  setVisible(show:boolean){visible=show;queuePaint('global');queuePaint('regional');},
  setLayer(field:Field){scenarioFrame=null;state.scenarioActive=false;onStatus({...state});selected=field;queuePaint('global');queuePaint('regional');},
  async timeline(body:Record<string,string>){const r=await fetch('/terra/api/timeline',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw Error(await r.text());accept('regional',await r.json());},
  async control(body:Record<string,number|boolean>){const r=await fetch('/terra/api/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw Error(await r.text());accept('regional',await r.json());},
  destroy(){disposed=true;cancelAnimationFrame(paintRequest);clearInterval(rainAnimation);clearInterval(comparisonTimer);clearInterval(stale);feeds.forEach(es=>es.close());removeTick();viewer.creditDisplay.removeStaticCredit(credit);focusEntities.forEach(e=>viewer.entities.remove(e));for(const overlay of Object.values(overlays))overlay?.destroy();viewer.scene.primitives.remove(points);}
 };
}
