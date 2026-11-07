"""Reproducible public-data climate screen / reanalysis benchmark, plus synthetic package logistics."""
import argparse,hashlib,csv,io,json,math,statistics,time,urllib.parse,urllib.request,zipfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from physics import land_step,crop_coefficient
from datetime import datetime,timezone
PLACES=[('Säkylä',61.078744,22.253773),('Bjuv',56.08372,12.91914)]
MODELS=['MRI_AGCM3_2_S','EC_Earth3P_HR']

def fetch(base,params,cache):
    url=base+'?'+urllib.parse.urlencode(params)
    if cache.exists():return json.loads(cache.read_text())
    req=urllib.request.Request(url,headers={'User-Agent':'TERRA-research-prototype/1.0'})
    with urllib.request.urlopen(req,timeout=90) as r:d=json.load(r)
    cache.write_text(json.dumps(d));return d

def metrics(pairs):
    if not pairs:raise ValueError('No comparable soil values')
    dif=[a-b for a,b in pairs]
    return dict(days=len(pairs),bias_mm=statistics.mean(dif),rmse_mm=math.sqrt(statistics.mean(d*d for d in dif)))

def build(archive,out,cache):
    cache.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
    ensemble=[]
    for label,start,end in [('baseline','2000-01-01','2009-12-31'),('future','2040-01-01','2049-12-31')]:
        p=dict(latitude=','.join(str(v[1]) for v in PLACES),longitude=','.join(str(v[2]) for v in PLACES),models=','.join(MODELS),daily='temperature_2m_mean,precipitation_sum',start_date=start,end_date=end)
        data=fetch('https://climate-api.open-meteo.com/v1/climate',p,cache/(label+'.json'))
        if not isinstance(data,list) or len(data)!=2:raise ValueError('Expected two climate locations')
        for place,r in zip(PLACES,data):
            daily=r['daily'];dates=daily['time']
            for model in MODELS:
                def values(k):
                    a=daily.get(k+'_'+model,daily.get(k));
                    if not a or len(a)!=len(dates) or any(v is None or not math.isfinite(v) for v in a):raise ValueError('Incomplete climate series '+model+' '+k)
                    return a
                temp=values('temperature_2m_mean');rain=values('precipitation_sum');n_year=len({d[:4] for d in dates})
                ensemble.append(dict(place=place[0],model=model,period=label,start=start,end=end,mean_temp_c=statistics.mean(temp),mean_annual_precip_mm=sum(rain)/n_year,days=len(dates)))
        print('Climate',label,'complete',flush=True)
    benchmarks=[]
    p=dict(latitude=','.join(str(v[1]) for v in PLACES),longitude=','.join(str(v[2]) for v in PLACES),start_date='2018-04-01',end_date='2018-09-30',models='era5_seamless',hourly='temperature_2m,precipitation,et0_fao_evapotranspiration,soil_moisture_0_to_7cm,soil_moisture_7_to_28cm,soil_moisture_28_to_100cm',timezone='UTC')
    data=fetch('https://archive-api.open-meteo.com/v1/archive',p,cache/'era5-seamless-2018.json')
    for place,r in zip(PLACES,data):
        h=r['hourly'];times=h['time'];
        reference=[sum(depth*h[k][i] for depth,k in [(70,'soil_moisture_0_to_7cm'),(210,'soil_moisture_7_to_28cm'),(720,'soil_moisture_28_to_100cm')]) if all(h[k][i] is not None for k in ['soil_moisture_0_to_7cm','soil_moisture_7_to_28cm','soil_moisture_28_to_100cm']) else None for i in range(len(times))]
        if reference[0] is None:raise ValueError('Missing soil initialization')
        soil=min(450,reference[0]);snow=0;ts=h['temperature_2m'][0];series=[];max_residual=0
        for i in range(1,len(times)):
            t=times[i]
            temp=h['temperature_2m'][i];ts+=(temp-ts)*(1-math.exp(-1/12));doy=datetime.fromisoformat(t).timetuple().tm_yday
            soil,snow,b=land_step(soil,snow,h['precipitation'][i],h['et0_fao_evapotranspiration'][i],temp,ts,3600,450,kc=crop_coefficient(doy,place[1]));max_residual=max(max_residual,abs(b['residual_mm']))
            if t.endswith('23:00') and reference[i] is not None:series.append(dict(date=t[:10],model_soil_mm=soil,era5_land_soil_mm=reference[i]))
        benchmarks.append(dict(place=place[0],**metrics([(v['model_soil_mm'],v['era5_land_soil_mm']) for v in series]),series=series,max_water_residual_mm=max_residual))
    print('Reanalysis benchmark complete',flush=True)
    with zipfile.ZipFile(archive) as z:
        root=next(n[:-len('LICENSE_DATA.txt')] for n in z.namelist() if n.endswith('/LICENSE_DATA.txt'))
        def rows(n):return list(csv.DictReader(io.StringIO(z.read(root+n).decode('utf-8-sig'))))
        prices=[r for r in rows('data/05_scenarios/contract_prices_and_replacement_premiums.csv') if r['year']=='2026']
        shipments=[r for r in rows('data/02_raw_feeds/shipments.csv') if r['year']=='2025']
        modes=[]
        for mode in sorted({r['mode'] for r in shipments}):
            rs=[r for r in shipments if r['mode']==mode];modes.append(dict(mode=mode,shipments=len(rs),tonnes=sum(float(r['t']) for r in rs),tonne_km=sum(float(r['tkm']) for r in rs)))
    result=dict(input_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [cache/'baseline.json',cache/'future.json',cache/'era5-seamless-2018.json']},schema='terra.decision-evidence.v1',generated_at=datetime.now(timezone.utc).isoformat(),climate=dict(models=MODELS,members=ensemble,notice='Public CMIP6 HighResMIP projections via Open-Meteo, ERA5-Land bias correction enabled. Near-RCP8.5 forcing; not an SSP scenario ensemble. Two-model spread is not a probability interval or full uncertainty estimate. Ten-year windows are illustrative, not 30-year climate normals. Only two representative locations; no farm-scale projections.',source='https://open-meteo.com/en/docs/climate-api'),benchmark=dict(results=benchmarks,notice='2018 April–September comparison with ERA5-Land modeled 0–1 m storage. Uses ERA5/ERA5-Land seamless forcing and the same soil reanalysis for initialization: a diagnostic benchmark, not independent observational validation or held-out crop-yield validation. Generic Kc/capacity; snow starts zero; no irrigation/calibration.',source='https://open-meteo.com/en/docs/historical-weather-api'),supply=dict(prices=prices,shipments_2025_by_mode=modes,notice='Apetit Climate & Nature Navigator synthetic dataset, Since AI ry 2026 (CC BY 4.0). Volumes, prices and shipments are synthetic. No calibrated weather-to-loss function, actual supplier routing or real company cost claim. Replacement cost is a user-specified shortfall scenario, not a predicted loss. Adaptation project costs are not yet linked.'))
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print('Decision evidence saved')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archive',type=Path);p.add_argument('--cache',type=Path,required=True);a=p.parse_args();build(a.archive,Path(__file__).resolve().parents[2]/'frontend/static/data/decision',a.cache)
