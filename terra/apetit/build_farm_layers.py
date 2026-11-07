"""Build licensed synthetic challenge layers. Optional build dependency: duckdb.
Usage: python terra/apetit/build_farm_layers.py /path/to/package.zip
Runtime itself needs no extra Python packages. Never imports code from the ZIP.
"""
import argparse,base64,csv,io,json,math,sys,tempfile,zipfile
from pathlib import Path
from datetime import date,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from physics import land_step,crop_coefficient
ATTRIBUTION='Apetit Climate & Nature Navigator synthetic dataset, Since AI ry 2026 (CC BY 4.0)'
CROPS=['pea','turnip_rape','potato','carrot','spinach','barley','wheat','oats','grass_ley','fallow']
SOILS=['clay','silt','fine_sand','sand','organic']
STRESS=['pea','turnip_rape','potato','carrot','spinach','cereal','grass_ley']
ROOT=[.6,1.,.5,.6,.3,1.,1.]
TAW=[160,140,120,60,200] # illustrative mm available water / metre

def build(archive,out):
    import duckdb
    out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        root=next(n[:-len('LICENSE_DATA.txt')] for n in z.namelist() if n.endswith('/LICENSE_DATA.txt'))
        def rows(name):return list(csv.DictReader(io.StringIO(z.read(root+name).decode('utf-8-sig'))))
        parcels=rows('data/01_master/parcels.csv');farms={r['farm_id']:r for r in rows('data/01_master/farm_registry.csv')}
        cells=rows('data/01_master/climate_grid_cells.csv');plans=rows('data/03_farming/parcel_crop_history_and_plan.csv')
        histories={};current={}
        for r in plans:
            y=int(r['year'])
            if 2021<=y<=2026:histories.setdefault(r['parcel_id'],[]).append(r)
            if y==2026:current[r['parcel_id']]=r['crop']
        reported={}
        for r in rows('data/03_farming/farm_survey_fi.csv'):
            if r['farm_id'] not in reported or int(r['year'])>int(reported[r['farm_id']]['year']):reported[r['farm_id']]=r
        p={k:[] for k in ['id','farm','lat','lon','area','region','crop','soil','clay','peat','peat_misreported','bio','rot','catch','organic_farm','drainage','cell']}
        for r in parcels:
            f=farms[r['farm_id']];lat,lon=float(r['lat']),float(r['lon']);soil=r['soil_class_soilmap'];crop=current.get(r['parcel_id'],'fallow')
            if soil not in SOILS or crop not in CROPS:raise ValueError('Unknown crop or soil code')
            h=histories.get(r['parcel_id'],[]);rotation=len({a['crop'] for a in h})/max(1,len(h));catch=sum(a['catch_crop'].lower()=='true' for a in h)/max(1,len(h));organic=f['organic_certified'].lower()=='true'
            bio=round(.5*rotation+.3*catch+.2*organic,4)
            eligible=[i for i,c in enumerate(cells) if c['region']==f['region']]
            cell=min(eligible,key=lambda i:(float(cells[i]['lat'])-lat)**2+((float(cells[i]['lon'])-lon)*math.cos(math.radians(lat)))**2)
            mismatch=soil=='organic' and 'mineral' in reported.get(r['farm_id'],{}).get('soil_type_reported','').lower()
            values=[r['parcel_id'],r['farm_id'],lat,lon,float(r['area_ha']),f['region'],CROPS.index(crop),SOILS.index(soil),float(r['clay_pct_soilmap']),int(soil=='organic'),int(mismatch),bio,round(rotation,4),round(catch,4),int(organic),r['drainage'],cell]
            for k,v in zip(p,values):p[k].append(v)
        obj=dict(schema='terra.apetit.parcels.v1',source=ATTRIBUTION+'; locations and attributes are synthetic, not real growers.',crop_year=2026,crop_codes=CROPS,soil_codes=SOILS,stress_crops=STRESS,cells=[dict(id=c['cell_id'],lat=float(c['lat']),lon=float(c['lon'])) for c in cells],parcels=p,biodiversity_note='Illustrative management proxy = 0.5 × rotation diversity + 0.3 × catch-crop share + 0.2 × organic certification. Not measured biodiversity or a validated ecological index.',peat_note='Synthetic soil-map organic class versus latest synthetic farm self-report. A mismatch is not evidence of misreporting; the challenge soil map is imperfect. The 29 t CO2/ha/year factor is an illustrative drained-organic-soil assumption, not a measured parcel emission.',biodiversity_weights=dict(rotation=.5,catch=.3,organic=.2))
        (out/'apetit_parcels.json').write_text(json.dumps(obj,separators=(',',':')))
        for name in ['LICENSE_DATA.txt','docs/ASSUMPTIONS_AND_LIMITATIONS.md','docs/SOURCES_AND_LICENCES.md']:(out/Path(name).name).write_bytes(z.read(root+name))
        with tempfile.TemporaryDirectory() as tmp:
            weather=Path(tmp)/'weather.parquet';weather.write_bytes(z.read(root+'data/04_climate/weather_daily_1991_2060.parquet'))
            con=duckdb.connect()
            for key,year,scenario in [('2018',2018,'historical'),('2026',2026,'historical'),('2050_ssp585',2050,'ssp585')]:
                start=date(year,4,1);end=date(year,9,30);days=(end-start).days+1;doy0=start.timetuple().tm_yday
                data=con.execute('SELECT cell_id,date,tmean_c,precip_mm,pet_mm FROM read_parquet(?) WHERE scenario=? AND date>=? AND date<? ORDER BY cell_id,date',[str(weather),scenario,str(start),str(end+timedelta(days=1))]).fetchall()
                bycell={}
                for c,d,t,r,e in data:bycell.setdefault(c,[]).append((d.date(),float(t),float(r),float(e)))
                packed=bytearray()
                for crop,depth in zip(STRESS,ROOT):
                    for taw in TAW:
                        capacity=taw*depth/.43
                        for c in cells:
                            daily=bycell[c['cell_id']]
                            if len(daily)!=days:raise ValueError('Incomplete season forcing')
                            soil=.7*capacity;snow=0;ts=daily[0][1];lat=float(c['lat']);sow=130+3*(lat-60);harvest=sow+130
                            for day,t,r,e in daily:
                                doy=day.timetuple().tm_yday;ks=1.
                                # Daily inputs distributed over 24 hourly conservative land steps.
                                for _ in range(24):
                                    ts+=(t-ts)*(1-math.exp(-3600/43200))
                                    soil,snow,ledger=land_step(soil,snow,r/24,e/24,t,ts,3600,capacity,kc=crop_coefficient(doy,lat));ks=ledger['ks']
                                active=sow<=doy<=harvest
                                packed.append(1+round(200*(1-ks)) if active else 0)
                result=dict(key=key,label=f'{year} {scenario} · synthetic challenge weather · generic FAO-56 replay (not observed or calibrated yield)',year=year,doy0=doy0,days=days,dims=[len(STRESS),len(SOILS),len(cells),days],data=base64.b64encode(packed).decode(),source=ATTRIBUTION,assumptions=dict(root_depth_m=dict(zip(STRESS,ROOT)),taw_mm_per_m=dict(zip(SOILS,TAW)),initialization='field capacity on 1 April; snow zero',crop_calendar='generic Nordic spring-crop curve, latitude shifted; 2026 crop map reused for all seasons',weather='synthetic daily mean temperature, precipitation and PET; uniformly distributed over hourly land steps',validation='water balance only; not validated against ERA5-Land or measured crops'))
                (out/f'season_{key}.json').write_text(json.dumps(result,separators=(',',':')))
                print('Built',key,len(packed),'stress values',flush=True)
    print('Built',len(parcels),'synthetic parcel points',len(cells),'climate cells')
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('archive',type=Path);a.add_argument('--out',type=Path,default=Path(__file__).resolve().parents[2]/'frontend/static/data/apetit');args=a.parse_args();build(args.archive,args.out)
