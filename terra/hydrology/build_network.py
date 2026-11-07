"""Optional offline builder: pip install pyshp shapely. Runtime is standard-library only."""
import io,json,zipfile,hashlib,argparse,math,sys
from pathlib import Path
import shapefile
from shapely.geometry import shape,box,mapping,Point,LineString
from shapely.strtree import STRtree
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from model import NX,NY,LONS,LATS
from physics import Transport

def reader(p):
 z=zipfile.ZipFile(p);b=next(n[:-4] for n in z.namelist() if n.endswith('.shp'))
 return shapefile.Reader(shp=io.BytesIO(z.read(b+'.shp')),shx=io.BytesIO(z.read(b+'.shx')),dbf=io.BytesIO(z.read(b+'.dbf')))
def build(folder,out):
 out.mkdir(parents=True,exist_ok=True);domain=box(10,54,33,71);basins=[];polys=[]
 for r in reader(folder/'basins.zip').iterShapeRecords():
  b=r.shape.bbox
  if b[2]<10 or b[0]>33 or b[3]<54 or b[1]>71:continue
  g=shape(r.shape.__geo_interface__).buffer(0)
  if not g.intersects(domain):continue
  p=r.record.as_dict();basins.append(dict(id=int(p['HYBAS_ID']),next_down=int(p['NEXT_DOWN']),area_km2=p['SUB_AREA'],geometry=mapping(g.intersection(domain).simplify(.008,preserve_topology=True)),center=list(g.intersection(domain).representative_point().coords)[0]));polys.append(g)
 tree=STRtree(polys);areas=Transport(LONS,LATS).area;dx=LONS[1]-LONS[0];dy=LATS[1]-LATS[0]
 for b,g in zip(basins,polys):
  cells=[]
  for j,y in enumerate(LATS):
   for i,x in enumerate(LONS):
    cell=box(max(10,x-dx/2),max(54,y-dy/2),min(33,x+dx/2),min(71,y+dy/2));frac=g.intersection(cell).area/cell.area
    if frac>1e-7:cells.append([j*NX+i,round(frac,7)])
  b['cells']=cells;b['modeled_area_km2']=sum(areas[i]*f for i,f in cells)/1e6
 rivers=[];endpoints={}
 for r in reader(folder/'rivers.zip').iterShapeRecords():
  p=r.record.as_dict();b=r.shape.bbox
  if b[2]<10 or b[0]>33 or b[3]<54 or b[1]>71:continue
  coords=[list(v[:2]) for v in r.shape.points];endpoints[int(p['HYRIV_ID'])]=[coords[0],coords[-1]]
  if p['ORD_STRA']<4:continue
  line=LineString(coords)
  ids=[basins[int(i)]['id'] for i in tree.query(line) if polys[int(i)].intersects(line)]
  if not ids:continue
  simple=list(line.simplify(.003).coords)
  rivers.append(dict(id=int(p['HYRIV_ID']),next_down=int(p['NEXT_DOWN']),basin_ids=ids,length_km=p['LENGTH_KM'],mean_discharge_m3_s=p['DIS_AV_CMS'],order=p['ORD_STRA'],coordinates=simple,direction_known=False))
 for r in rivers:
  target=endpoints.get(r['next_down'])
  if target:
   def dist(p):return min((p[0]-q[0])**2+(p[1]-q[1])**2 for q in target)
   if dist(r['coordinates'][0])<dist(r['coordinates'][-1]):r['coordinates'].reverse()
   r['direction_known']=True
 data=dict(schema='terra.hydrology.v1',bounds=[10,54,33,71],basins=basins,rivers=rivers,source='HydroBASINS level 5 v1c and HydroRIVERS v1 Europe / WWF; Lehner & Grill (2013), doi:10.1002/hyp.9740',license_url='https://www.hydrosheds.org/page/license',source_urls=['https://www.hydrosheds.org/products/hydrobasins','https://www.hydrosheds.org/products/hydrorivers'],input_sha256={n:hashlib.sha256((folder/n).read_bytes()).hexdigest() for n in ['basins.zip','rivers.zip']},notice='Real terrain-derived hydrography, generalized for display. Reaches of Strahler order >=4 only. Basins clipped to the Nordic model domain; membership computed before display simplification. North of 60N the underlying DEM is coarser: unsuitable for farm-scale drainage. Long-term discharge is modeled 1971–2000 average, not live gauge data. Endpoint orientation uses NEXT_DOWN geometry; isolated/terminal reaches without verified direction have no flow particles.')
 data['places']=[dict(name=name,lon=x,lat=y,basin_id=next((b['id'] for b,g in zip(basins,polys) if g.covers(Point(x,y))),0)) for name,x,y in [('Säkylä',22.253773,61.078744),('Bjuv',12.91914,56.08372)]]
 (out/'network.json').write_text(json.dumps(data,separators=(',',':')));print(len(basins),'basins',len(rivers),'river reaches',flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('folder',type=Path);a=p.parse_args();build(a.folder,Path(__file__).resolve().parents[2]/'frontend/static/data/hydrology')
