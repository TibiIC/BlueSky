"""Coarse Natural Earth land mask for global crop-weather exposure overlays."""
import json
from pathlib import Path
from model import inside

def land_mask(lons,lats):
    data=json.loads((Path(__file__).parent/'geography/ne_110m_land.geojson').read_text())
    polygons=[]
    for feature in data['features']:
        g=feature['geometry']
        polygons.extend([g['coordinates']] if g['type']=='Polygon' else g['coordinates'])
    def land(x,y):
        return any(inside(x,y,p[0]) and not any(inside(x,y,h) for h in p[1:]) for p in polygons)
    return [land(x,y) for y in lats for x in lons]
