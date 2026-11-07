#!/usr/bin/env python3
"""Example SSE consumer for a bridge process. No external dependencies."""
import argparse
import json
import math
import urllib.request

def ecef(lon_deg,lat_deg,height_m=0):
    """WGS84 longitude,latitude,height -> Earth-centered Earth-fixed meters."""
    lon,lat=math.radians(lon_deg),math.radians(lat_deg)
    a,e2=6378137.,6.69437999014e-3
    n=a/math.sqrt(1-e2*math.sin(lat)**2)
    return ((n+height_m)*math.cos(lat)*math.cos(lon),(n+height_m)*math.cos(lat)*math.sin(lon),(n*(1-e2)+height_m)*math.sin(lat))

def frames(url):
    # Complete snapshots; no replay required. Reconnect in your production adapter.
    with urllib.request.urlopen(urllib.request.Request(url,headers={'Accept':'text/event-stream'}),timeout=15) as stream:
        data=[]
        for raw in stream:
            line=raw.decode().rstrip('\r\n')
            if line.startswith('data:'):data.append(line[5:].lstrip())
            elif not line and data:
                yield json.loads('\n'.join(data));data=[]

def main():
    p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8765/events');p.add_argument('--count',type=int,default=3);args=p.parse_args()
    count=0
    for frame in frames(args.url):
        if frame.get("ready") is False:continue
        count+=1
        grid=frame['grid'];i,j=grid['nx']//2,grid['ny']//2
        lon=grid['west']+i*(grid['east']-grid['west'])/(grid['nx']-1)
        lat=grid['south']+j*(grid['north']-grid['south'])/(grid['ny']-1)
        k=j*grid['nx']+i
        print(json.dumps(dict(schema=frame['schema'],simulation=frame['sim_time'],mode=frame['source']['mode'],center_lon_lat=[lon,lat],center_ecef_m=ecef(lon,lat,2000),center_moisture_g_m3=frame['fields']['moisture_g_m3'][k])))
        if count>=args.count:break
if __name__=='__main__':main()
