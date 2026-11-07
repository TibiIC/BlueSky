"""Paired regional land-water stress experiment, not a climate projection."""
import math
from model import Model, MASK, LONS, LATS, LAND, inside, iso
from physics import land_step

def run(forecast, start, body):
    limits={'warming_c':(-3,8,2.),'rain_factor':(0,3,.8),'et_factor':(.5,2,1.1),'hours':(1,168,48)}
    if not isinstance(body,dict) or set(body)-set(limits):raise ValueError('Unknown scenario parameter')
    params={}
    for k,(lo,hi,default) in limits.items():
        v=body.get(k,default)
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not lo<=v<=hi:raise ValueError(f'{k} must be {lo}..{hi}')
        params[k]=v
    duration=min(params['hours']*3600,max(0,forecast.end-start))
    if duration<3600:raise ValueError('Less than one hour remains; reset the timeline or load a longer period')
    initial=Model(start);initial.initialize(forecast)
    states=[dict(soil=initial.soil[:],snow=initial.snow[:],temp=initial.soil_temp[:]) for _ in range(2)]
    groups={'Nordic land':[i for i,m in enumerate(MASK) if m]}
    for country in ('Finland','Sweden'):
        groups[country]=[j*len(LONS)+i for j,y in enumerate(LATS) for i,x in enumerate(LONS) if inside(x,y,LAND[country])]
    weights=initial.transport.area
    land_area=sum(weights[j] for j in groups['Nordic land'])
    def mean(a,indices):return sum(a[i]*weights[i] for i in indices)/sum(weights[i] for i in indices)
    series=[];totals=[{'et_mm':0.,'runoff_mm':0.,'drainage_mm':0.} for _ in states];max_residual=0.
    def record(t):
        return dict(time=iso(t),regions={name:{label:dict(soil_mm=mean(s['soil'],idx),snow_mm=mean(s['snow'],idx),dry_area_pct=100*sum(weights[i] for i in idx if s['soil'][i]/initial.capacity<.3)/sum(weights[i] for i in idx)) for label,s in zip(('baseline','scenario'),states)} for name,idx in groups.items()})
    series.append(record(start));elapsed=0
    while elapsed<duration:
        dt=min(900,duration-elapsed);forcing=forecast.at(start+elapsed+dt/2)
        for n,s in enumerate(states):
            for i in groups['Nordic land']:
                temp=forcing['temp_c'][i]+(params['warming_c'] if n else 0)
                s['temp'][i]+=(temp-s['temp'][i])*(1-math.exp(-dt/43200))
                soil,snow,ledger=land_step(s['soil'][i],s['snow'][i],forcing['precip_mm_h'][i]*(params['rain_factor'] if n else 1),forcing['et0_mm_h'][i]*(params['et_factor'] if n else 1),temp,s['temp'][i],dt,initial.capacity)
                s['soil'][i]=soil;s['snow'][i]=snow
                max_residual=max(max_residual,abs(ledger['residual_mm']))
                for k in totals[n]:totals[n][k]+=ledger[k]*weights[i]/land_area
        elapsed+=dt
        if elapsed%3600==0 or elapsed==duration:series.append(record(start+elapsed))
    frame=initial.frame(forecast.meta(None,None))
    frame['sim_time']=iso(start+duration)
    frame['fields']['soil_fraction']=[s/initial.capacity if m else None for s,m in zip(states[1]['soil'],MASK)]
    frame['fields']['snow_water_mm']=[s if m else None for s,m in zip(states[1]['snow'],MASK)]
    return dict(kind='paired-land-water-sensitivity',notice='Hypothetical regional stress test of the selected weather period. Not CMIP6, an SSP projection, a yield forecast or a policy recommendation. Wind and atmospheric moisture are unchanged. ET change is an independent prescribed assumption, not a temperature feedback.',parameters=params,start=iso(start),end=iso(start+duration),actual_hours=duration/3600,source=forecast.meta(None,None),initialization=initial.initialization,series=series,water_totals=totals,max_water_residual_mm=max_residual,frame=frame,geography='Approximate country masks; area-weighted grid cells, not farm boundaries',dry_threshold='soil / capacity < 0.30; illustrative screening threshold')
