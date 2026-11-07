"""Coarse global atmosphere. Separate periodic grid; no global soil-water claims."""
import math
import time
from model import iso
from weather import Forecast,vapor,VARIABLES
from agriculture import enrich
from geography import land_mask

GX,GY=36,18
GLONS=[-180+i*10 for i in range(GX)]
GLATS=[-85+j*10 for j in range(GY)]
GLOBAL_MASK=land_mask(GLONS,GLATS)
class GlobalForecast(Forecast):
    variables=VARIABLES
    anchors=[(lat,lon) for lat in (-60.,0.,60.) for lon in (-157.5,-112.5,-67.5,-22.5,22.5,67.5,112.5,157.5)]
    lats=GLATS; lons=GLONS
    spatial_method='spherical inverse-distance weighted, 24 samples; 10 degree simulation grid'
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.weights=[]
        for lat in self.lats:
            for lon in self.lons:
                w=[]
                for alat,alon in self.anchors:
                    cosine=math.sin(math.radians(lat))*math.sin(math.radians(alat))+math.cos(math.radians(lat))*math.cos(math.radians(alat))*math.cos(math.radians(lon-alon))
                    d=math.acos(max(-1,min(1,cosine)));w.append(1/max(d*d,1e-5))
                total=sum(w);self.weights.append([a/total for a in w])
    def at(self,t):
        if self.records:return super().at(t)
        out={k:[] for k in ('temp_c','u_ms','v_ms','precip_mm_h','et0_mm_h','vapor_g_m3')};h=(t-self.start)/3600
        for lat in self.lats:
            for lon in self.lons:
                temp=27-abs(lat)*.65+3*math.sin(math.radians(lon)+h*.1)
                moist=.5+.5*math.sin(math.radians(lon*2)+h*.08)*math.cos(math.radians(lat*2))
                for key,value in zip(out,(temp,8*math.sin(math.radians(lat*3)),3*math.sin(math.radians(lon)+h*.04),moist*.6,.06,vapor(temp,55+35*moist))):out[key].append(value)
        return enrich(self,out,t)

def global_advect(q,u,v,dt):
    result=[]
    for j,lat in enumerate(GLATS):
        dx=111320*10*math.cos(math.radians(lat));dy=111320*10
        for i in range(GX):
            n=j*GX+i;x=(i-u[n]*dt/dx)%GX;y=max(0,min(GY-1,j-v[n]*dt/dy))
            a,b=int(x),int(y);c,d=(a+1)%GX,min(b+1,GY-1);s,r=x-a,y-b
            result.append((1-r)*((1-s)*q[b*GX+a]+s*q[b*GX+c])+r*((1-s)*q[d*GX+a]+s*q[d*GX+c]))
    return result
class GlobalModel:
    def __init__(self,now):self.time=now;self.q=None;self.fields={};self.seq=0
    def advance_to(self,target,forecast):
        target=min(target,forecast.end)
        if self.q is None:
            self.fields=forecast.at(self.time);self.q=self.fields['vapor_g_m3'][:]
        while target>self.time+1e-6:
            dt=min(300,target-self.time,3600-self.time%3600)
            f=forecast.at(self.time+dt/2);q=global_advect(self.q,f['u_ms'],f['v_ms'],dt);w=1-math.exp(-dt/21600)
            self.q=[max(0,a+(b-a)*w) for a,b in zip(q,f['vapor_g_m3'])];self.fields=f;self.time+=dt;self.seq+=1
    def frame(self,forecast,error=None,attempt=None):
        return dict(schema='terra.global-frame.v1',sequence=self.seq,sim_time=iso(self.time),published_at=iso(time.time()),source=forecast.meta(error,attempt),grid=dict(crs='EPSG:4326',nx=GX,ny=GY,west=-180,east=170,south=-85,north=85,periodic_longitude=True,land_mask=GLOBAL_MASK,land_mask_source='Natural Earth 1:110m; coarse cell-center mask',order='row-major; south to north; west to east; centers at inclusive bounds',coverage='10 degree global longitude; centers 85S..85N; display edges 90S..90N; polar values are sparse-sample interpolation, not a polar circulation model'),fields={**{k:[round(v,4) for v in a] for k,a in self.fields.items() if k not in ('et0_mm_h','vapor_g_m3')},'moisture_g_m3':[round(v,4) for v in self.q]},units=dict(temp_c='degC',u_ms='m/s east',v_ms='m/s north',precip_mm_h='mm/h',moisture_g_m3='g/m3 tracer'))
