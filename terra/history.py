"""Historical forcing summaries. These describe past weather, not observed soil response."""
from model import MASK,iso

def summarize(forecast,model):
    weights=[a if land else 0 for a,land in zip(model.transport.area,MASK)]
    total=sum(weights);weights=[a/total for a in weights]
    series=[];t=forecast.start+3600
    while t<=forecast.end:
        fields=forecast.at(t)
        mean=lambda key:sum(w*v for w,v in zip(weights,fields[key]))
        wind=sum(w*(u*u+v*v)**.5 for w,u,v in zip(weights,fields['u_ms'],fields['v_ms']))
        series.append(dict(time=iso(t),temperature_c=round(mean('temp_c'),3),precip_mm_h=round(mean('precip_mm_h'),4),wind_ms=round(wind,3)))
        t+=3600
    return dict(weighting='area-weighted regional land mean; forcing, not simulation output',precipitation_total_mm=round(sum(r['precip_mm_h'] for r in series),3),min_mean_temperature_c=min(r['temperature_c'] for r in series),max_mean_temperature_c=max(r['temperature_c'] for r in series),peak_mean_wind_ms=max(r['wind_ms'] for r in series),series=series)
