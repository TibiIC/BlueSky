#!/usr/bin/env python3
"""Fetch actual API forcing, initialize v2 physics and check a six-hour run."""
import argparse
import json
import math
import time
from pathlib import Path
from model import Model
from weather import Forecast

def main():
    p=argparse.ArgumentParser();p.add_argument('--hours',type=float,default=6);p.add_argument('--output',default='live-physics-verification.json');args=p.parse_args()
    f=Forecast.fetch();m=Model(time.time());m.initialize(f)
    assert m.initialization['soil_seeded_cells']>0,'API did not supply usable soil initialization'
    start=m.time;end=min(f.end,start+args.hours*3600);max_land_residual=0.;max_atmosphere_residual=0.;start_soil=m.soil[:];start_snow=m.snow[:]
    totals={}
    while m.time<end-1e-6:
        dt=min(60,end-m.time,3600-m.time%3600)
        m.step(f.at(m.time+dt/2),dt)
        max_land_residual=max(max_land_residual,abs(m.ledger['residual_mm']))
        max_atmosphere_residual=max(max_atmosphere_residual,abs(m.atmosphere_ledger['relative_residual']))
        for k,v in m.ledger.items():totals[k]=totals.get(k,0)+v
        assert min(m.q)>=0 and all(math.isfinite(v) for v in m.q)
        assert all(0<=s<=m.capacity for s in m.soil)
    assert max_land_residual<1e-9 and max_atmosphere_residual<1e-10
    report=dict(verified_at=time.time(),source=f.meta(),initialization=m.initialization,simulated_hours=(m.time-start)/3600,engine_version='2.0',max_land_budget_residual_mm=max_land_residual,max_atmosphere_relative_residual=max_atmosphere_residual,cumulative_area_weighted_land_fluxes_mm=totals,last_atmosphere_budget_kg=m.atmosphere_ledger,soil_changed_cells=sum(abs(a-b)>1e-8 for a,b in zip(start_soil,m.soil)),snow_changed_cells=sum(abs(a-b)>1e-8 for a,b in zip(start_snow,m.snow)))
    Path(args.output).write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
