"""Illustrative weather exposure screens, not calibrated crop/yield predictions."""
import bisect
import math

THRESHOLDS=dict(frost_c=0.,heat_c=28.,wind_ms=12.,wet_day_mm=20.)
CROP_FIELDS=('rain_day_mm','rain_day_coverage_h','frost_pct','heat_pct','wind_risk_pct','heavy_rain_pct')

def enrich(forecast,fields,t):
    if forecast.records:
        day=int(t//86400)*86400
        cache=getattr(forecast,'_rain_days',{})
        if day not in cache:
            ts=forecast.records[0]['hourly']['time'];lo=bisect.bisect_right(ts,day);hi=bisect.bisect_right(ts,day+86400)
            values=[sum(r['hourly']['precipitation'][lo:hi]) for r in forecast.records]
            cache[day]=([sum(w*v for w,v in zip(weights,values)) for weights in forecast.weights],float(hi-lo))
            while len(cache)>8:cache.pop(next(iter(cache)))
            forecast._rain_days=cache
        rain,coverage=cache[day]
    else:rain=[p*24 for p in fields['precip_mm_h']];coverage=24.
    fields.update(rain_day_mm=rain,rain_day_coverage_h=[coverage]*len(rain),frost_pct=[100. if t<=THRESHOLDS['frost_c']+1e-9 else 0. for t in fields['temp_c']],heat_pct=[100. if t>=THRESHOLDS['heat_c']-1e-9 else 0. for t in fields['temp_c']],wind_risk_pct=[100. if math.hypot(u,v)>=THRESHOLDS['wind_ms']-1e-9 else 0. for u,v in zip(fields['u_ms'],fields['v_ms'])],heavy_rain_pct=[100. if p>=THRESHOLDS['wet_day_mm']-1e-9 else 0. for p in rain])
    return fields
