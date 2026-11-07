"""Pinned open Finnish soil-biochemistry measurements, distinct from DNA diversity."""
import argparse,csv,hashlib,io,json,math,urllib.request
from pathlib import Path
from datetime import datetime,timezone
BASE='https://zenodo.org/api/records/13837158/files/'
FILES=['Karstula_SOM.csv','Karstula_Enzyme_activity.csv']

def summarize(som,enzymes):
    def rows(b):return list(csv.DictReader(io.StringIO(b.decode('utf-8-sig'))))
    def number(v):
        if v in ('NA','',None):return None
        x=float(v)
        if not math.isfinite(x):raise ValueError('Non-finite measured value')
        return x
    activities={}
    for r in rows(enzymes):activities.setdefault(r['code'],[]).append(dict(enzyme=r['Enzyme'],value=number(r['Value (nmol.h-1.g-1 DW)']),unit='nmol h⁻¹ g⁻¹ dry weight'))
    samples=[]
    for r in rows(som):
        if r['Sample_type']!='Soil':continue
        samples.append(dict(id=r['code'],plot=r['Plot'],block=r['BlockID'],replicate=r['Replicate'],layer=r['Layer'],treatment=r['Treatment'],date='2021-09',date_precision='month',lat=62+54/60+43.343/3600,lon=24+34/60+16.021/3600,coordinate_scope='Study-level coordinate; plot coordinates not supplied',fungal_biomass_mg_g_dw=number(r['fungal_biomass_mg_g-1_DW']),fungal_necromass_mg_g_dw=number(r['fungal_necromass_mg_g-1_DW']),ph=number(r['pH']),enzymes=activities.get(r['code'],[])))
    if len({s['id'] for s in samples})!=len(samples):raise ValueError('Duplicate sample ID')
    return dict(schema='terra.measured-finland-biology.v1',title='Karstula forest soil biology · Finland',source_url='https://zenodo.org/records/13837158',doi='10.5281/zenodo.13837158',license='CC BY 4.0',citation='Adamczyk B, Adamczyk S, Tupek B, Li Q, Martinovic T, Richy E, Lehtonen A, Baldrian P, Mäkipää R (2025). Soil chemistry, organic carbon pool, microbial biomass and necromass, enzymes activity and greenhouse gas fluxes after a long-term N fertilization of a Scots pine forest in Finland. Zenodo. https://doi.org/10.5281/zenodo.13837158',retrieved_at=datetime.now(timezone.utc).isoformat(),sources=[dict(url=BASE+n+'/content',sha256=hashlib.sha256(b).hexdigest()) for n,b in zip(FILES,[som,enzymes])],samples=samples,sample_count=len(samples),enzyme_record_count=sum(len(s['enzymes']) for s in samples),notice='Historical forest soil measurements from September 2021. Fungal biomass/necromass are source-reported biomarker-based estimates, not DNA richness, organism counts or a microbiome diversity index. Treatments and soil layers are separate; values are not directly comparable to Swedish ASV/Shannon data. No link to Apetit farms. One study-level coordinate; individual plot positions and spatial uncertainty are not supplied.',methods='Organic and upper mineral soil (0–20 cm) sampled in September 2021. Dataset reports fungal biomass based on ergosterol and necromass markers based on glucosamine. Source file units are retained: mg/g dry weight. Enzyme activities retain nmol/h/g dry weight. Sampling depth is layer-dependent; no exact depth is invented for the organic layer.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input-dir',type=Path);a=p.parse_args()
    bs=[(a.input_dir/n).read_bytes() if a.input_dir else urllib.request.urlopen(BASE+n+'/content',timeout=30).read() for n in FILES]
    d=summarize(*bs);out=Path(__file__).resolve().parents[2]/'frontend/static/data/biology/karstula.json';out.write_text(json.dumps(d,ensure_ascii=False,indent=2));print(d['sample_count'],'Finnish samples;',d['enzyme_record_count'],'enzyme measurements')
