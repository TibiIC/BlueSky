"""TERRA regional state evolution; numerical kernels in physics.py. SI except explicitly labelled mm/hour."""
import math
from datetime import datetime, timezone

NX, NY = 25, 29
WEST, EAST, SOUTH, NORTH = 10., 33., 54., 71.
LONS = [WEST + i*(EAST-WEST)/(NX-1) for i in range(NX)]
LATS = [SOUTH + j*(NORTH-SOUTH)/(NY-1) for j in range(NY)]
# Deliberately coarse, hand-drawn geographic masks; not authoritative boundaries.
LAND = {
 'Sweden': [(12.5,55.3),(14.2,56),(16.7,56.2),(18.8,59.3),(17.2,60.5),(19.5,63.5),(23.7,65.8),(23.7,68.5),(20.5,69.1),(18,68),(16,66),(14,64),(12,61),(11,59),(12.5,57.5)],
 'Finland': [(20.6,69),(22,68),(23.6,66),(24.6,65),(21.3,63),(21,61),(23,59.8),(27.5,60.3),(30.5,62),(31.5,63.5),(29.5,66),(28.5,69.8),(26,70.1)],
 'Norway': [(5,58),(7,58),(10.7,59),(12,61),(14,64),(16,66),(18,68),(20.5,69.1),(26,70.1),(30,70.6),(28,71.3),(22,70.5),(17,69.3),(13,67),(10,64),(7,63),(5,61)],
 'East': [(33,54),(33,71),(30,70.6),(28.5,69.8),(29.5,66),(31.5,63.5),(30.5,62),(27.5,60.3),(29,59.5),(28,58),(24,58),(23.5,57),(21,56),(21,54)],
 'South': [(10,54),(21,54),(18,54.8),(14,54.5),(12,55.3),(10,56)]
}
def inside(x,y,poly):
    hit=False
    for (a,b),(c,d) in zip(poly,poly[1:]+poly[:1]):
        if (b>y)!=(d>y) and x < (c-a)*(y-b)/(d-b)+a: hit=not hit
    return hit
MASK=[any(inside(x,y,p) for p in LAND.values()) for y in LATS for x in LONS]
def iso(t): return datetime.fromtimestamp(t,timezone.utc).isoformat().replace('+00:00','Z')
def sample(a,x,y):
    x=max(0,min(NX-1,x)); y=max(0,min(NY-1,y))
    i,j=int(x),int(y); k,l=min(i+1,NX-1),min(j+1,NY-1); u,v=x-i,y-j
    return (1-v)*((1-u)*a[j*NX+i]+u*a[j*NX+k])+v*((1-u)*a[l*NX+i]+u*a[l*NX+k])
def advect(q,u,v,dt):
    """Semi-Lagrangian backtrace; clamped edge = zero-gradient open approximation."""
    out=[]
    dy=111320*(NORTH-SOUTH)/(NY-1)
    for j,lat in enumerate(LATS):
        dx=111320*math.cos(math.radians(lat))*(EAST-WEST)/(NX-1)
        for i in range(NX):
            n=j*NX+i
            out.append(sample(q,i-u[n]*dt/dx,j-v[n]*dt/dy))
    return out

def bucket(s,p,et,dt,capacity):
    """One soil reservoir. p,et mm/h; dt seconds; exact per-step water ledger."""
    rain=max(0,p)*dt/3600
    evaporation=min(s+rain,max(0,et)*dt/3600*(s/capacity))
    available=s+rain-evaporation
    runoff=max(0,available-capacity)
    available-=runoff
    drainage=min(available,max(0,available-.7*capacity)*(1-math.exp(-dt/86400)))
    return available-drainage, rain, evaporation, runoff, drainage

class Model:
    """Regional prescribed-wind transport, effective mixing layer, snow/soil stores."""
    def __init__(self,now):
        from physics import Transport
        self.time=now; self.q=None; self.rain_pattern=None; self.soil=[90. if m else 0. for m in MASK]
        self.snow=[0.]*len(MASK); self.soil_temp=[2.]*len(MASK)
        self.speed=1.; self.capacity=450.; self.rain_scale=1.; self.paused=False
        self.ks=[1. if m else None for m in MASK]
        self.seq=0; self.ledger={}; self.fields={}; self.atmosphere_ledger={}
        self.transport=Transport(LONS,LATS); self.layer_height_m=1000.
        from hydrology.routing import Router
        self.hydrology=Router(self.transport.area,MASK)
        self.transport_wind='10m'
        self.initialization=dict(kind='assumed',soil_depth_m=1.,snow_density_kg_m3=200.,note='Explicit synthetic initial state')
    def initialize(self,forecast):
        forcing=forecast.at(self.time); self.q=forcing['vapor_g_m3'][:];self.rain_pattern=forcing['precip_mm_h'][:]
        self.fields=forcing
        if not forecast.records:return
        land=forecast.initial_land(self.time); seeded=0;clipped=0;snow_seeded=0
        for i,mask in enumerate(MASK):
            if not mask:continue
            theta=[land[k][i] for k in ('soil_moisture_0_to_7cm','soil_moisture_7_to_28cm','soil_moisture_28_to_100cm')]
            if all(v is not None and 0<=v<=1 for v in theta):
                total=sum(d*v for d,v in zip((70,210,720),theta))
                self.soil[i]=min(self.capacity,total);seeded+=1;clipped+=total>self.capacity
            depth=land['snow_depth'][i]
            if depth is not None and depth>=0:self.snow[i]=depth*200.;snow_seeded+=1
            temp=land['soil_temperature_0_to_7cm'][i]
            self.soil_temp[i]=temp if temp is not None else forcing['temp_c'][i]
        self.initialization=dict(kind='api_model_history' if getattr(forecast,'product',None)=='recent-history' else 'api_reanalysis' if getattr(forecast,'product',None)=='reanalysis' else 'api_forecast',at=iso(self.time),forecast_id=forecast.digest,soil_depth_m=1.,soil_seeded_cells=seeded,land_cells=sum(MASK),soil_capacity_clipped_cells=clipped,snow_seeded_cells=snow_seeded,snow_density_kg_m3=200.,note='Soil from depth-integrated API theta; snow-depth conversion assumes 200 kg/m3. Missing cells retain explicit assumptions; not in-situ observations.')
    def step(self,forcing,dt):
        from physics import land_step,crop_coefficient,water_stress
        if self.q is None:self.q=forcing['vapor_g_m3'][:]
        if self.rain_pattern is None:self.rain_pattern=forcing['precip_mm_h'][:]
        rain_advected,rain_budget=self.transport.advance(self.rain_pattern,forcing.get('u_transport_ms',forcing['u_ms']),forcing.get('v_transport_ms',forcing['v_ms']),dt,forcing['precip_mm_h'])
        rain_weight=1-math.exp(-dt/1800)
        self.rain_pattern=[max(0,a+(b-a)*rain_weight) for a,b in zip(rain_advected,forcing['precip_mm_h'])]
        self.rain_pattern_budget=rain_budget
        before=math.fsum(q*a for q,a in zip(self.q,self.transport.area))*self.layer_height_m/1000
        transported,transport_budget=self.transport.advance(self.q,forcing.get('u_transport_ms',forcing['u_ms']),forcing.get('v_transport_ms',forcing['v_ms']),dt,forcing['vapor_g_m3'])
        doy=datetime.fromtimestamp(self.time,timezone.utc).timetuple().tm_yday
        totals={};evap=[0.]*len(MASK);runoff_rates=[0.]*len(MASK)
        land_area=math.fsum(a for a,m in zip(self.transport.area,MASK) if m)
        for i,m in enumerate(MASK):
            if not m:continue
            self.soil_temp[i]+=(forcing['temp_c'][i]-self.soil_temp[i])*(1-math.exp(-dt/43200))
            soil,snow,ledger=land_step(self.soil[i],self.snow[i],forcing['precip_mm_h'][i]*self.rain_scale,forcing['et0_mm_h'][i],forcing['temp_c'][i],self.soil_temp[i],dt,self.capacity,kc=crop_coefficient(doy,LATS[i//NX]))
            self.soil[i]=soil;self.snow[i]=snow;evap[i]=ledger['et_mm'];ledger.pop('ks');self.ks[i]=water_stress(soil,self.capacity)
            runoff_rates[i]=(ledger['runoff_mm']+ledger['drainage_mm'])*3600/dt if dt>0 else 0.
            for k,value in ledger.items():totals[k]=totals.get(k,0.)+value*self.transport.area[i]/land_area
        self.ledger=totals
        self.hydrology.advance(runoff_rates,dt)
        nudging=0.;evap_mass=0.;precip_mass=0.;unresolved=0.;new=[]
        weight=1-math.exp(-dt/21600)
        for i,(q,target,area) in enumerate(zip(transported,forcing['vapor_g_m3'],self.transport.area)):
            correction=(target-q)*weight; q+=correction
            # 1 mm water = 1 kg/m2; q [g/m3] -> layer water q*H/1000 [mm].
            source=evap[i]*1000/self.layer_height_m
            demand=forcing['precip_mm_h'][i]*self.rain_scale*dt/3600
            removed=min(max(0,q+source)*self.layer_height_m/1000,demand)
            new.append(max(0.,q+source-removed*1000/self.layer_height_m))
            nudging+=correction*area*self.layer_height_m/1000
            evap_mass+=evap[i]*area;precip_mass+=removed*area;unresolved+=(demand-removed)*area
        self.q=new
        after=math.fsum(q*a for q,a in zip(new,self.transport.area))*self.layer_height_m/1000
        boundary=transport_budget['boundary_exchange_g_m']*self.layer_height_m/1000
        residual=after-before-boundary-nudging-evap_mass+precip_mass
        self.atmosphere_ledger=dict(before_kg=before,after_kg=after,boundary_exchange_kg=boundary,forecast_nudging_kg=nudging,land_evaporation_kg=evap_mass,precipitation_removed_kg=precip_mass,external_precipitation_water_kg=unresolved,residual_kg=residual,relative_residual=residual/max(1,before),cfl_substeps=transport_budget['cfl_substeps'])
        self.time+=dt; self.fields=forcing; self.seq+=1
    def advance(self,forecast,wall_dt):
        remaining=0 if self.paused else min(wall_dt,2)*self.speed
        remaining=min(remaining,max(0,forecast.end-self.time))
        if not self.fields:self.initialize(forecast);self.step(self.fields,0)
        while remaining>1e-8:
            dt=min(60.,remaining,3600-(self.time % 3600))
            self.step(forecast.at(self.time+dt/2),dt);remaining-=dt
        self.transport_wind=getattr(forecast,'transport_wind','10m') if forecast.records else 'synthetic (10m-equivalent)'
    def frame(self,source):
        fields={k:[round(x,4) for x in v] for k,v in self.fields.items() if k!='vapor_g_m3'}
        fields.update(rain_pattern_mm_h=[round(v,4) for v in (self.rain_pattern or self.fields['precip_mm_h'])],moisture_g_m3=[round(x,4) for x in self.q],soil_mm=[round(s,4) if m else None for s,m in zip(self.soil,MASK)],soil_fraction=[round(s/self.capacity,4) if m else None for s,m in zip(self.soil,MASK)],snow_water_mm=[round(s,4) if m else None for s,m in zip(self.snow,MASK)],water_stress_ks=[round(k,4) if m else None for k,m in zip(self.ks,MASK)],crop_stress=[round(1-k,4) if m else None for k,m in zip(self.ks,MASK)])
        fields.pop('u_transport_ms',None);fields.pop('v_transport_ms',None)
        return dict(schema='terra.frame.v1',engine_version='2.0',sequence=self.seq,sim_time=iso(self.time),published_at=iso(datetime.now(timezone.utc).timestamp()),catchments=self.hydrology.frame(),source=source,initialization=self.initialization,physics=dict(transport='conservative finite-volume upwind + diffusion; CFL substeps',diffusivity_m2_s=self.transport.k,layer_height_m=self.layer_height_m,wind='prescribed forecast; no prognostic momentum solver',transport_wind=self.transport_wind,land='snow + 1m soil bucket; degree-day melt; frozen-soil infiltration reduction; FAO-56 ET_a = Ks*Kc*ET0 with wilting point',crop_coefficient='generic Nordic spring crop, FAO-56 four-stage; placeholder for Apetit crop calendars'),rain_pattern=dict(method='conservative transport of a rain-intensity proxy with 30-minute relaxation to hourly forecast precipitation; not microphysics, radar or diagnosed weather fronts',land_coupling='Land and water budgets retain API forecast precipitation, not the visualization tracer'),grid=dict(crs='EPSG:4326',nx=NX,ny=NY,west=WEST,east=EAST,south=SOUTH,north=NORTH,order='row-major; south to north; west to east; cell centers at inclusive bounds',land_mask=MASK),fields=fields,controls=dict(speed=self.speed,paused=self.paused,capacity_mm=self.capacity,rain_scale=self.rain_scale),water_budget_mean_land_mm=self.ledger,water_budget_weighting='area-weighted; last substep; includes snow storage',atmosphere_budget_kg=self.atmosphere_ledger,units=dict(rain_pattern_mm_h='mm/h advected intensity proxy',temp_c='degC',u_ms='m/s east',v_ms='m/s north',precip_mm_h='mm/h water equivalent',et0_mm_h='mm/h',moisture_g_m3='g/m3 effective layer',soil_mm='mm over 1m depth',soil_fraction='1',snow_water_mm='mm water equivalent',water_stress_ks='1 (FAO-56 Ks; 1=no stress)',crop_stress='1 (1-Ks)',rain_day_mm='mm/UTC day',frost_pct='% land area',heat_pct='% land area',wind_risk_pct='% land area',heavy_rain_pct='% land area'))
