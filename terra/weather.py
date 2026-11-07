"""Sparse API samples interpolated to the display grid, with explicit provenance."""
from datetime import date,datetime,timedelta,timezone
import bisect
import hashlib
import json
import math
import time
import urllib.parse
import urllib.request
from model import LATS,LONS,iso
from agriculture import enrich,THRESHOLDS

ANCHORS=[(lat,lon) for lat in (55.,58.5,62.,65.5,70.) for lon in (11.,16.25,21.5,26.75,32.)]
LAND_VARIABLES='soil_moisture_0_to_7cm,soil_moisture_7_to_28cm,soil_moisture_28_to_100cm,soil_temperature_0_to_7cm,snow_depth'
VARIABLES='temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,wind_direction_10m,et0_fao_evapotranspiration'
# Optional transport-level winds. Served by the forecast API; the ERA5 archive
# endpoint returns nulls, so history falls back to 10 m winds (recorded in frames).
TRANSPORT_VARIABLES='wind_speed_850hPa,wind_direction_850hPa'

def vapor(t,rh):
    # Absolute vapor concentration from Tetens saturation pressure, near-surface proxy.
    return 216.7*(rh/100)*6.112*math.exp(17.67*t/(t+243.5))/(t+273.15)

class Forecast:
    anchors=ANCHORS
    variables=VARIABLES+','+LAND_VARIABLES
    lats=LATS
    lons=LONS
    spatial_method="inverse-distance weighted, 25 samples; not native grid resolution"
    def __init__(self,start=None,records=None,fetched=None):
        self.start=start if start is not None else time.time()
        self.records=records; self.fetched=fetched
        self.end=records[0]['hourly']['time'][-1] if records else self.start+7*86400
        self.digest=hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest()[:12] if records else 'synthetic-v1'
        self.weights=[]
        for y in self.lats:
            for x in self.lons:
                distances=[((x-lon)*math.cos(math.radians(y)))**2+(y-lat)**2 for lat,lon in self.anchors]
                w=[1/max(d,.001) for d in distances]; total=sum(w)
                self.weights.append([v/total for v in w])
    @classmethod
    def fetch(cls):
        params=dict(latitude=','.join(str(a[0]) for a in cls.anchors),longitude=','.join(str(a[1]) for a in cls.anchors),hourly=cls.variables+','+TRANSPORT_VARIABLES,wind_speed_unit='ms',timeformat='unixtime',timezone='GMT',forecast_days=7,cell_selection='nearest')
        req=urllib.request.Request('https://api.open-meteo.com/v1/forecast?'+urllib.parse.urlencode(params),headers={'User-Agent':'TERRA-hackathon-prototype/1.0'})
        with urllib.request.urlopen(req,timeout=20) as response: records=json.load(response)
        cls.validate(records)
        return cls(records=records,fetched=time.time())
    @classmethod
    def validate(cls,records):
        if not isinstance(records,list) or len(records)!=len(cls.anchors): raise ValueError('Unexpected number of API locations')
        timeline=None
        for r in records:
            h=r['hourly']; ts=h['time']
            if len(ts)<24 or any(b-a!=3600 for a,b in zip(ts,ts[1:])): raise ValueError('Invalid hourly timeline')
            if timeline is not None and ts!=timeline: raise ValueError('Mismatched timelines')
            timeline=ts
            for k in VARIABLES.split(','):
                if len(h[k])!=len(ts) or any(not isinstance(x,(float,int)) or not math.isfinite(x) for x in h[k]): raise ValueError('Missing or nonfinite '+k)
            if any(not -100<=t<=65 for t in h['temperature_2m']): raise ValueError('Temperature out of bounds')
            if any(not 0<=v<=100 for v in h['relative_humidity_2m']): raise ValueError('Humidity out of bounds')
            if any(v<0 for k in ('precipitation','et0_fao_evapotranspiration','wind_speed_10m') for v in h[k]): raise ValueError('Negative forcing')
    @staticmethod
    def history_dates(start_date,end_date):
        start=date.fromisoformat(start_date);end=date.fromisoformat(end_date)
        latest=datetime.now(timezone.utc).date()-timedelta(days=1)
        if start<date(1950,1,1) or end>latest or end<start or (end-start).days>6:
            raise ValueError('Choose 1–7 days from 1950 through '+latest.isoformat()+' (UTC).')
        return start,end
    @classmethod
    def fetch_history(cls,start_date,end_date):
        start,end=cls.history_dates(start_date,end_date)
        # Extra endpoint day supplies the midnight closing the final hourly interval.
        params=dict(latitude=','.join(str(a[0]) for a in cls.anchors),longitude=','.join(str(a[1]) for a in cls.anchors),hourly=cls.variables,wind_speed_unit='ms',timeformat='unixtime',timezone='GMT',models='era5_seamless',start_date=start.isoformat(),end_date=(end+timedelta(days=1)).isoformat(),cell_selection='nearest')
        recent=end>datetime.now(timezone.utc).date()-timedelta(days=7)
        if recent:
            params.pop('models')
        base='https://api.open-meteo.com/v1/forecast' if recent else 'https://archive-api.open-meteo.com/v1/archive'
        req=urllib.request.Request(base+'?'+urllib.parse.urlencode(params),headers={'User-Agent':'TERRA-hackathon-prototype/2.1'})
        with urllib.request.urlopen(req,timeout=40) as response:records=json.load(response)
        cls.validate(records)
        beginning=datetime.combine(start,datetime.min.time(),timezone.utc).timestamp()
        ending=datetime.combine(end+timedelta(days=1),datetime.min.time(),timezone.utc).timestamp()
        if records[0]['hourly']['time'][0]>beginning or records[0]['hourly']['time'][-1]<ending:raise ValueError('Archive did not cover requested period')
        f=cls(start=beginning,records=records,fetched=time.time());f.end=ending;f.product='recent-history' if recent else 'reanalysis';f.history_range=[start.isoformat(),end.isoformat()]
        return f
    def initial_land(self,t):
        """IDW land initialization; renormalize around sea/missing soil samples."""
        output={k:[] for k in LAND_VARIABLES.split(',')}
        if not self.records:return output
        anchor_values=[]
        for record in self.records:
            h=record['hourly'];ts=h['time'];index=min(range(len(ts)),key=lambda i:abs(ts[i]-t))
            anchor_values.append({k:h[k][index] if isinstance(h.get(k),list) and len(h[k])==len(ts) else None for k in output})
        for weights in self.weights:
            for key in output:
                pairs=[(w,a[key]) for w,a in zip(weights,anchor_values) if isinstance(a[key],(int,float)) and math.isfinite(a[key])]
                output[key].append(sum(w*v for w,v in pairs)/sum(w for w,v in pairs) if pairs else None)
        return output
    def at(self,t):
        out={k:[] for k in ('temp_c','u_ms','v_ms','precip_mm_h','et0_mm_h','vapor_g_m3','u_transport_ms','v_transport_ms')}
        if self.records:
            values=[];levels=set()
            for r in self.records:
                h=r['hourly']; ts=h['time']; hi=max(1,min(len(ts)-1,bisect.bisect_right(ts,t))); lo=hi-1
                a=max(0,min(1,(t-ts[lo])/3600))
                def lerp(k): return h[k][lo]*(1-a)+h[k][hi]*a
                def uv(i):
                    rad=math.radians(h['wind_direction_10m'][i]); s=h['wind_speed_10m'][i]
                    return -s*math.sin(rad),-s*math.cos(rad)
                u0,v0=uv(lo); u1,v1=uv(hi)
                def uv850(i):
                    sp=h.get('wind_speed_850hPa');di=h.get('wind_direction_850hPa')
                    if not (isinstance(sp,list) and isinstance(di,list) and len(sp)==len(ts)==len(di)):return None
                    s_,d_=sp[i],di[i]
                    if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in (s_,d_)):return None
                    rad=math.radians(d_);return -s_*math.sin(rad),-s_*math.cos(rad)
                t0,t1=uv850(lo),uv850(hi)
                if t0 and t1:levels.add('850hPa');tu,tv=t0[0]*(1-a)+t1[0]*a,t0[1]*(1-a)+t1[1]*a
                else:levels.add('10m');tu,tv=u0*(1-a)+u1*a,v0*(1-a)+v1*a
                # Interval accumulation is held over (time[k-1],time[k]], not linearly blended.
                rate_index=max(0,min(len(ts)-1,bisect.bisect_left(ts,t)))
                temp=lerp('temperature_2m'); rh=lerp('relative_humidity_2m')
                values.append((temp,u0*(1-a)+u1*a,v0*(1-a)+v1*a,h['precipitation'][rate_index],h['et0_fao_evapotranspiration'][rate_index],vapor(temp,rh),tu,tv))
            for weights in self.weights:
                for idx,key in enumerate(out): out[key].append(sum(w*v[idx] for w,v in zip(weights,values)))
            self.transport_wind='850hPa' if levels=={'850hPa'} else '10m' if levels=={'10m'} else 'mixed 850hPa/10m'
        else:
            hour=(t-self.start)/3600
            for y in self.lats:
                for x in self.lons:
                    front=math.exp(-((x-(16+hour*.22))**2/14+(y-63)**2/35))
                    temp=8-(y-55)*.7+2*math.sin(hour*.26+x*.2)
                    uu,vv=5+2*math.sin(y*.4+hour*.1),2+2*math.cos(x*.3)
                    for key,value in zip(out,(temp,uu,vv,front*2.2,max(0,.07*math.sin(hour*.26)),vapor(temp,60+35*front),uu,vv)): out[key].append(value)
        return enrich(self,out,t)
    def meta(self,error=None,attempt=None):
        historical=getattr(self,'product',None) in ('reanalysis','recent-history')
        recent=getattr(self,'product',None)=='recent-history'
        mode='open-meteo-history' if historical else 'open-meteo' if self.records else 'synthetic'
        notice='Recent past model data from the forecast API; not direct observations or an as-issued forecast archive.' if recent else 'ERA5/ERA5-Land historical reanalysis; reconstructed past weather, not original forecasts or direct station measurements.' if historical else 'Forecast product, not live observations. Fetch time is not model issuance time.' if self.records else 'Entirely synthetic demo forcing; no observations.'
        return dict(mode=mode,fetched_at=iso(self.fetched) if self.fetched else None,last_attempt_at=iso(attempt) if attempt else None,last_error=error,forecast_id=self.digest,valid_start=iso(self.start if historical else self.records[0]['hourly']['time'][0] if self.records else self.start),valid_end=iso(self.end),refresh_seconds=None if historical else 900,hourly_resolution_seconds=3600,sample_count=len(self.anchors) if self.records else 0,spatial_method=self.spatial_method,model_run_time=None,forcing_kind='recent_model_history' if recent else 'weather_reanalysis' if historical else 'numerical_weather_forecast' if self.records else 'synthetic',agriculture=dict(thresholds=THRESHOLDS,notice='Illustrative air-weather screens; not crop-specific damage or yield predictions. Daily rain requires 24 complete UTC intervals.'),reanalysis_model='era5_seamless' if historical and not recent else None,notice=notice)
