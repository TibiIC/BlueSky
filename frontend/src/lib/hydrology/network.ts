import type {Globe} from '../globe/viewer.ts';
import type {Frame} from '../weather/terra.ts';
export interface Basin{id:number;next_down:number;area_km2:number;modeled_area_km2:number;center:number[];geometry:unknown;cells:number[][]}
export interface Reach{id:number;next_down:number;basin_ids:number[];length_km:number;mean_discharge_m3_s:number;coordinates:number[][];direction_known:boolean}
export interface Network{places?:{name:string;lon:number;lat:number;basin_id:number}[];schema:string;basins:Basin[];rivers:Reach[];source:string;notice:string}
export function attachHydrology(g:Globe,onData:(d:Network)=>void,onError:(e:string)=>void){
 const {viewer,C}=g;let disposed=false,building=false,built=false,enabled=false,selected=0,flow=true,frame:Frame|undefined,data:Network|undefined,ds:import('cesium').GeoJsonDataSource|undefined;
 const lines=viewer.scene.primitives.add(new C.PolylineCollection());const dots=viewer.scene.primitives.add(new C.PointPrimitiveCollection());const borders=viewer.scene.primitives.add(new C.PolylineCollection());const borderLines:{id:number;line:import('cesium').Polyline}[]=[];lines.show=false;dots.show=false;
 const material=C.Material.fromType('Color',{color:C.Color.fromCssColorString('#18dfff').withAlpha(.95)});
 const paths=new Map<number,{r:Reach;line:import('cesium').Polyline;segments:number[];length:number}>();
 const particles:{path:number;distance:number;point:import('cesium').PointPrimitive}[]=[];
 function paint(){lines.show=enabled;borders.show=enabled;dots.show=enabled&&flow;for(const b of borderLines)b.line.show=!selected||b.id===selected;
  for(const p of paths.values())p.line.show=!selected||p.r.basin_ids.includes(selected);
  if(ds){ds.show=enabled;for(const e of ds.entities.values)e.show=!selected||Number(e.properties?.id?.getValue())===selected;}
 }
 function rings(b:Basin):number[][][]{const geo=b.geometry as {type:string;coordinates:number[][][]|number[][][][]};return geo.type==='Polygon'?geo.coordinates as number[][][]:(geo.coordinates as number[][][][]).flat();}
 async function build(d:Network){if(building||built||disposed)return;building=true;
  const borderMaterial=C.Material.fromType('Color',{color:C.Color.fromCssColorString('#ffe09c')});for(const b of d.basins)for(const ring of rings(b))borderLines.push({id:b.id,line:borders.add({positions:C.Cartesian3.fromDegreesArrayHeights(ring.flatMap(v=>[v[0],v[1],16500])),width:2,material:borderMaterial})});
  for(const r of d.rivers){const segments=[0];for(let i=1;i<r.coordinates.length;i++){const a=r.coordinates[i-1],b=r.coordinates[i];segments.push(segments[i-1]+111320*Math.hypot((b[0]-a[0])*Math.cos((a[1]+b[1])/2*Math.PI/180),b[1]-a[1]));}
   const line=lines.add({positions:C.Cartesian3.fromDegreesArrayHeights(r.coordinates.flatMap(v=>[v[0],v[1],17000])),width:Math.min(4.5,2.2+Math.log10(1+r.mean_discharge_m3_s)/2),material});paths.set(r.id,{r,line,segments,length:segments[segments.length-1]});}
  const candidates=d.rivers.filter(r=>r.direction_known&&r.mean_discharge_m3_s>0).sort((a,b)=>b.mean_discharge_m3_s-a.mean_discharge_m3_s);
  for(let i=0;i<Math.min(800,candidates.length);i++){const p=paths.get(candidates[Math.floor(i*candidates.length/Math.min(800,candidates.length))].id)!;particles.push({path:p.r.id,distance:Math.random()*p.length,point:dots.add({position:C.Cartesian3.fromDegrees(...p.r.coordinates[0] as [number,number],19000),pixelSize:4,color:C.Color.WHITE})});}
  const loaded=await C.GeoJsonDataSource.load({type:'FeatureCollection',features:d.basins.map(b=>({type:'Feature',properties:{id:b.id},geometry:b.geometry}))},{stroke:C.Color.fromCssColorString('#53cde0'),fill:C.Color.fromCssColorString('#2387b2').withAlpha(.08),strokeWidth:1,clampToGround:false});
  if(disposed){loaded.entities.removeAll();return;}ds=loaded;for(const e of ds.entities.values){if(e.polygon){e.polygon.height=new C.ConstantProperty(15500);e.polygon.outline=new C.ConstantProperty(true);}}
  await viewer.dataSources.add(ds);built=true;paint();
 }
 fetch('/data/hydrology/network.json').then(r=>{if(!r.ok)throw Error('Hydrology dataset unavailable');return r.json();}).then((d:Network)=>{if(disposed)return;if(d.schema!=='terra.hydrology.v1')throw Error('Invalid hydrology schema');data=d;onData(d);if(enabled)return build(d);}).catch(e=>{if(!disposed)onError(String(e));});
 let last=performance.now();const remove=viewer.scene.preRender.addEventListener(()=>{
  const now=performance.now(),dt=Math.min(.1,(now-last)/1000);last=now;if(!enabled||!flow||!frame||frame.ready===false||frame.controls.paused)return;
  for(const p of particles){let path=paths.get(p.path)!;p.point.show=!selected||path.r.basin_ids.includes(selected);if(!p.point.show)continue;
   const q=path.r.mean_discharge_m3_s,width=Math.max(3,5*Math.sqrt(q)),depth=Math.max(.3,.15*Math.pow(q,.3)),velocity=Math.max(.1,Math.min(3,q/(width*depth)));
   p.distance+=dt*frame.controls.speed*velocity;
   if(p.distance>=path.length){const next=paths.get(path.r.next_down);if(next?.r.direction_known&&(!selected||next.r.basin_ids.includes(selected))){p.path=next.r.id;p.distance=0;path=next;}else p.distance=0;}
   let i=1;while(i<path.segments.length-1&&path.segments[i]<p.distance)i++;const a=path.r.coordinates[i-1],b=path.r.coordinates[i],f=(p.distance-path.segments[i-1])/Math.max(1,path.segments[i]-path.segments[i-1]);p.point.position=C.Cartesian3.fromDegrees(a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f,19000);
  }
 });
 return {setEnabled(v:boolean){enabled=v;if(v&&data&&!built&&!building)build(data).catch(e=>{if(!disposed)onError(String(e));});paint();},setFlow(v:boolean){flow=v;paint();},updateFrame(f:Frame|undefined){frame=f;},select(id:number){selected=id;paint();},focus(){const b=data?.basins.find(b=>b.id===selected);if(b){const sphere=C.BoundingSphere.fromPoints(rings(b).flat().map(v=>C.Cartesian3.fromDegrees(v[0],v[1],17000)));viewer.camera.flyToBoundingSphere(sphere,{offset:new C.HeadingPitchRange(0,-Math.PI/2,0)});}else viewer.camera.flyTo({destination:C.Cartesian3.fromDegrees(21.5,63,2600000)});},destroy(){disposed=true;remove();viewer.scene.primitives.remove(lines);viewer.scene.primitives.remove(dots);viewer.scene.primitives.remove(borders);if(ds)viewer.dataSources.remove(ds,true);}};
}
