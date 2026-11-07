"""Import a pinned CC0 SBDI Darwin Core archive; derive sample-level fungal ASV metrics."""
import argparse,collections,csv,hashlib,io,json,math,urllib.request,zipfile
from pathlib import Path
from datetime import datetime,timezone
URL='https://www.gbif.se/ipt/archive.do?r=pb363_kungsangen_otu_a&v=1.9'

def summarize(blob):
    z=zipfile.ZipFile(io.BytesIO(blob))
    def rows(name):return list(csv.DictReader(io.StringIO(z.read(name).decode('utf-8-sig')),delimiter='\t'))
    records=rows('occurrence.txt');measurements={r['id']:r for r in rows('extendedmeasurementorfact.txt') if r['measurementType']=='water content'}
    groups=collections.defaultdict(list)
    for r in records:
        if r['organismQuantityType']!='DNA sequence reads':raise ValueError('Expected DNA sequence read counts')
        groups[r['eventID']].append(r)
    samples=[]
    for event,rs in sorted(groups.items()):
        first=rs[0];counts=collections.defaultdict(float);moisture=set()
        for r in rs:
            for key in ('eventDate','decimalLatitude','decimalLongitude'):
                if r[key]!=first[key]:raise ValueError('Inconsistent sample metadata')
            n=float(r['organismQuantity'])
            if not math.isfinite(n) or n<=0:raise ValueError('Invalid read count')
            counts[r['occurrenceID'].rsplit(':',1)[-1]]+=n
            if r['id'] in measurements:
                m=measurements[r['id']]
                if m['measurementUnit']!='g/g':raise ValueError('Unexpected water-content unit')
                moisture.add(float(m['measurementValue']))
        if len(moisture)>1:raise ValueError('Inconsistent measured water content')
        total=sum(counts.values());h=-sum((v/total)*math.log(v/total) for v in counts.values())
        samples.append(dict(id=event.rsplit(':',1)[-1],event_id=event,date=first['eventDate'],lat=float(first['decimalLatitude']),lon=float(first['decimalLongitude']),coordinate_uncertainty_m=float(first['coordinateUncertaintyInMeters']) if first['coordinateUncertaintyInMeters'] else None,asv_richness=len(counts),shannon_reads=round(h,6),sequence_reads=total,gravimetric_water_g_g=next(iter(moisture),None),depth_min_m=float(first['minimumDepthInMeters']),depth_max_m=float(first['maximumDepthInMeters']),ena_sample=first['materialSampleID']))
    return dict(schema='terra.measured-biology.v1',title='Kungsängen soil fungal DNA samples',dataset_key='d850eb3d-d7e2-48f9-b6c1-cf1136a50bbb',version='1.9',source_url='https://www.gbif.se/ipt/resource?r=pb363_kungsangen_otu_a&v=1.9',archive_url=URL,archive_sha256=hashlib.sha256(blob).hexdigest(),license='CC0 1.0',license_url='https://creativecommons.org/publicdomain/zero/1.0/',citation='Rosling A, Eshghi Sahraei S, Furneaux B, Kluting K, Zakieh M (2026). Kungsängen soil microbial communities. Version 1.9. Biology Section, Uppsala University. https://doi.org/10.15468/upxbwy',retrieved_at=datetime.now(timezone.utc).isoformat(),record_count=len(records),sample_count=len(samples),kingdoms=sorted({r['kingdom'] for r in records}),samples=samples,protocol=records[0]['samplingProtocol'],metrics_notice='ASV richness and Shannon index are derived from published fungal DNA sequence read counts, not organism abundance, species richness or a soil-health score. No rarefaction or sequencing-depth standardization applied. These values depend on laboratory and bioinformatics methods.',coverage_notice='20 samples at one shared published location in a Swedish meadow; no Finland coverage or Apetit farm link. Coordinates are shown as published; spatial uncertainty is unspecified. No parcel interpolation or coordinate jitter.',time_notice='Collected 7 June 2016. Historical laboratory measurements; not a live sensor feed. Live weather animation does not update these measurements.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--archive',type=Path);p.add_argument('--out',type=Path,default=Path(__file__).resolve().parents[2]/'frontend/static/data/biology/kungsangen.json');a=p.parse_args()
    b=a.archive.read_bytes() if a.archive else urllib.request.urlopen(URL,timeout=45).read()
    d=summarize(b);a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(d,ensure_ascii=False,indent=2));print(d['sample_count'],'measured samples;',d['record_count'],'DNA occurrence records')
