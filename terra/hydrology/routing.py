"""Conservative linear-reservoir routing of modeled local runoff; not observed full river flow."""
import json,math
from functools import lru_cache
from pathlib import Path

@lru_cache(maxsize=1)
def load_basins(path):
 return json.loads(Path(path).read_text())['basins'] if Path(path).exists() else []

class Router:
 def __init__(self,areas,mask,network=None):
  p=Path(__file__).resolve().parents[2]/'frontend/static/data/hydrology/network.json'
  self.basins=network['basins'] if network else load_basins(str(p))
  self.areas=areas;self.mask=mask;self.storage={b['id']:0. for b in self.basins};self.flows={k:0. for k in self.storage};self.budget={};self.tau=21600.
  byid={b['id']:b for b in self.basins};indeg={k:0 for k in byid}
  for b in self.basins:
   if b['next_down'] in indeg:indeg[b['next_down']]+=1
  ready=[k for k,v in indeg.items() if not v];self.order=[]
  while ready:
   k=ready.pop();self.order.append(byid[k]);n=byid[k]['next_down']
   if n in indeg:
    indeg[n]-=1
    if not indeg[n]:ready.append(n)
  if len(self.order)!=len(self.basins):raise ValueError('Catchment graph contains a cycle')
 def advance(self,rates,dt):
  if dt<=0:return
  before=sum(self.storage.values());inflow={b['id']:sum(max(0,rates[i])*self.areas[i]*f/1000/3600 for i,f in b['cells'] if self.mask[i]) for b in self.basins}
  external_input=sum(inflow.values())*dt;outlet=0
  for b in self.order:
   k=b['id'];incoming=inflow[k];old=self.storage[k];new=old*math.exp(-dt/self.tau)+incoming*self.tau*(1-math.exp(-dt/self.tau));volume=old+incoming*dt-new
   self.storage[k]=new;self.flows[k]=volume/dt
   if b['next_down'] in inflow:inflow[b['next_down']]+=volume/dt
   else:outlet+=volume
  after=sum(self.storage.values());self.budget=dict(input_m3=external_input,outlet_m3=outlet,storage_before_m3=before,storage_after_m3=after,residual_m3=external_input-outlet-(after-before))
 def frame(self):
  return dict(method='6-hour linear reservoirs, exact constant-inflow integration, routed via HydroBASINS NEXT_DOWN',notice='Modeled regional runoff + drainage contribution only, not total river discharge or a flood forecast. Initial routing storage is zero; groundwater, lakes and infrastructure are not calibrated. Domain-edge flows exit the model.',budget=self.budget,basins=[dict(id=b['id'],outflow_m3_s=round(self.flows[b['id']],5),storage_m3=round(self.storage[b['id']],3),modeled_area_km2=b['modeled_area_km2']) for b in self.basins])
