"""Matched-time weather comparisons; does not reset or advance the physics engine."""
import math
import threading
import time
from datetime import datetime,timezone
from model import NX,NY,WEST,EAST,SOUTH,NORTH,MASK,iso
from weather import Forecast
from global_model import GlobalForecast,GLONS,GLATS,GLOBAL_MASK
from agriculture import CROP_FIELDS,THRESHOLDS

class Comparison:
    def __init__(self,engine):
        self.engine=engine;self.lock=threading.RLock();self.loading=False;self.error=None;self.forecast=None;self.global_forecast=None;self.date=None;self.cache={}
    def select(self,body):
        if not isinstance(body,dict) or set(body)!={'date'}:raise ValueError('Supply one historical date')
        day=body['date'];Forecast.history_dates(day,day)
        with self.lock:
            if self.loading:raise ValueError('Comparison already loading')
            self.loading=True;self.error=None
        threading.Thread(target=self.load,args=(day,),daemon=True).start()
        return self.frame()
    def load(self,day):
        try:
            with self.engine.lock:period=self.engine.history_cache.get((day,day))
            if day in self.cache:f,g=self.cache[day]
            elif period:f,g=period[:2]
            else:f,g=Forecast.fetch_history(day,day),GlobalForecast.fetch_history(day,day)
            self.cache[day]=(f,g)
            while len(self.cache)>5:self.cache.pop(next(iter(self.cache)))
            with self.lock:self.forecast=f;self.global_forecast=g;self.date=day;self.loading=False

        except Exception as exc:
            with self.lock:self.error=f'{type(exc).__name__}: {exc}';self.loading=False
    def frame(self,now=None):
        now=time.time() if now is None else now
        with self.lock:
            historical=self.forecast;global_historical=self.global_forecast;status=dict(schema='terra.comparison.v1',ready=False,loading=self.loading,error=self.error,date=self.date,published_at=iso(now))
        with self.engine.lock:
            live=self.engine.live_forecast;global_live=self.engine.live_global_forecast;weights=[a if m else 0 for a,m in zip(self.engine.model.transport.area,MASK)]
        if historical is None:return status
        if not live.records or not live.records[0]['hourly']['time'][0]<=now<=live.end:
            status['error']='Waiting for a real forecast covering current wall time';return status
        utc=datetime.fromtimestamp(now,timezone.utc)
        past=historical.start+utc.hour*3600+utc.minute*60+utc.second+utc.microsecond/1e6
        def selected(f,t):
            data=f.at(t)
            return dict(temp_c=data['temp_c'],precip_mm_h=data['precip_mm_h'],wind=[math.hypot(u,v) for u,v in zip(data['u_ms'],data['v_ms'])],**{k:data[k] for k in CROP_FIELDS})
        def datasets(current,old):
            a,b=selected(current,now),selected(old,past)
            delta={k:[x-y for x,y in zip(a[k],b[k])] for k in a}
            delta['rain_day_coverage_h']=[min(x,y) for x,y in zip(a['rain_day_coverage_h'],b['rain_day_coverage_h'])]
            return a,b,delta
        a,b,delta=datasets(live,historical)
        total=sum(weights);mean=lambda values:sum(w*v for w,v in zip(weights,values))/total
        summary={k:dict(live=mean(a[k]),historical=mean(b[k]),difference=mean(delta[k])) for k in a if k!='rain_day_coverage_h'}
        status.update(ready=True,live_time=iso(now),historical_time=iso(past),live_source=live.meta(),historical_source=historical.meta(),grid=dict(crs='EPSG:4326',nx=NX,ny=NY,west=WEST,east=EAST,south=SOUTH,north=NORTH,land_mask=MASK),live=a,historical=b,difference=delta,summary=summary,units=dict(temp_c='°C',precip_mm_h='mm/h',wind='m/s',rain_day_mm='mm/UTC day',frost_pct='%',heat_pct='%',wind_risk_pct='%',heavy_rain_pct='%'),screening_thresholds=THRESHOLDS,notice='Matched UTC hour for temperature/wind; daily rain compares complete UTC calendar days. Difference is live minus historical. Crop screens are illustrative, not crop-specific damage forecasts.')
        if global_historical and global_live.records and global_live.records[0]['hourly']['time'][0]<=now<=global_live.end:
            ga,gb,gd=datasets(global_live,global_historical)
            status['global']=dict(ready=True,grid=dict(crs='EPSG:4326',nx=len(GLONS),ny=len(GLATS),west=GLONS[0],east=GLONS[-1],south=GLATS[0],north=GLATS[-1],land_mask=GLOBAL_MASK,periodic_longitude=True),live=ga,historical=gb,difference=gd,live_source=global_live.meta(),historical_source=global_historical.meta())
        else:status['global']=dict(ready=False)
        return status
