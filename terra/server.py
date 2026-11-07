#!/usr/bin/env python3
"""Zero-dependency local HTTP/SSE service. Bind to loopback by default."""
import argparse
import json
import math
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from model import Model,LAND,iso
from weather import Forecast
from global_model import GlobalForecast,GlobalModel
from datetime import datetime,timedelta,timezone
from history import summarize
from comparison import Comparison

class Engine:
    def __init__(self,offline=False,require_live=False):
        self.lock=threading.RLock(); self.stop=threading.Event(); self.offline=offline; self.require_live=require_live
        self.forecast=Forecast(); self.model=Model(time.time()); self.error=None; self.attempt=None; self.revision=0
        self.model.advance(self.forecast,0)
        self.global_forecast=GlobalForecast(start=self.model.time); self.global_model=GlobalModel(self.model.time)
        self.global_model.advance_to(self.model.time,self.global_forecast)
        self.global_error=None; self.global_attempt=None
        self.mode="live";self.history_loading=False;self.history_error=None;self.history_summary=None;self.history_request=0
        self.live_forecast=self.forecast;self.live_global_forecast=self.global_forecast;self.history_cache={}
        self.comparison=Comparison(self)
    def snapshot(self):
        with self.lock:
            f=self.model.frame(self.forecast.meta(None,None) if self.mode=="historical" else self.forecast.meta(self.error,self.attempt))
            f['revision']=self.revision
            f['timeline']=self.timeline()
            f['ready']=not self.require_live or bool(self.forecast.records)
            if not f['ready']:
                f['source'].update(mode='waiting',notice='Waiting for real API forcing. Simulation held; no synthetic fields published.')
                f['fields']={k:[None]*len(v) for k,v in f['fields'].items()}
            f['at_forecast_end']=self.model.time>=self.forecast.end
            return f
    def global_snapshot(self):
        with self.lock:
            f=self.global_model.frame(self.global_forecast,None if self.mode=="historical" else self.global_error,None if self.mode=="historical" else self.global_attempt)
            f["controls"]=dict(speed=self.model.speed,paused=self.model.paused,rain_scale=1.)
            f["revision"]=self.revision
            f["timeline"]={k:v for k,v in self.timeline().items() if k!="summary"}
            f["ready"]=not self.require_live or bool(self.global_forecast.records)
            if not f["ready"]:
                f["source"].update(mode="waiting",notice="Waiting for real global forecast.")
                f["fields"]={k:[None]*len(v) for k,v in f["fields"].items()}
            return f
    def timeline(self):
        return dict(mode=self.mode,loading=self.history_loading,error=self.history_error,request_id=self.history_request,max_history_date=(datetime.now(timezone.utc).date()-timedelta(days=1)).isoformat(),reanalysis_through=(datetime.now(timezone.utc).date()-timedelta(days=7)).isoformat(),range=getattr(self.forecast,'history_range',None),start_time=iso(self.forecast.start) if self.mode=='historical' else None,end_time=iso(self.forecast.end),position_seconds=max(0,self.model.time-self.forecast.start) if self.mode=='historical' else 0,summary=self.history_summary)
    def set_timeline(self,body):
        if not isinstance(body,dict) or set(body)-{'mode','start_date','end_date'}:raise ValueError('Invalid timeline request')
        mode=body.get('mode')
        if mode not in ('live','historical'):raise ValueError('Mode must be live or historical')
        if mode=='historical':Forecast.history_dates(body.get('start_date',''),body.get('end_date',''))
        with self.lock:
            if self.history_loading and mode=='historical':raise ValueError('A historical request is already loading')
            self.history_request+=1;request_id=self.history_request;self.history_error=None
            if mode=='live':
                returning=self.mode=='historical'
                self.mode='live';self.history_loading=False;self.history_summary=None
                if returning:
                    self.forecast=self.live_forecast;self.global_forecast=self.live_global_forecast
                    self.model=Model(time.time());self.model.initialize(self.forecast);self.model.step(self.model.fields,0)
                    self.global_model=GlobalModel(self.model.time);self.global_model.advance_to(self.model.time,self.global_forecast)
                self.revision+=1
            else:
                self.history_loading=True
                threading.Thread(target=self.load_history,args=(body['start_date'],body['end_date'],request_id),daemon=True).start()
        return self.snapshot()
    def load_history(self,start,end,request_id):
        try:
            key=(start,end)
            with self.lock:cached=self.history_cache.get(key)
            if cached:f,gf,summary=cached
            else:
                f=Forecast.fetch_history(start,end);gf=GlobalForecast.fetch_history(start,end)
                m=Model(f.start);summary=summarize(f,m)
                with self.lock:
                    self.history_cache[key]=(f,gf,summary)
                    while len(self.history_cache)>3:self.history_cache.pop(next(iter(self.history_cache)))
            m=Model(f.start);m.initialize(f);m.step(m.fields,0);m.speed=600
            gm=GlobalModel(f.start);gm.advance_to(f.start,gf)
            with self.lock:
                if request_id!=self.history_request:return
                self.forecast=f;self.global_forecast=gf;self.model=m;self.global_model=gm
                self.mode='historical';self.history_summary=summary;self.history_loading=False
                self.error=None;self.global_error=None;self.revision+=1
        except Exception as exc:
            with self.lock:
                if request_id==self.history_request:self.history_loading=False;self.history_error=f'{type(exc).__name__}: {exc}'
    def run(self):
        previous=time.monotonic()
        while not self.stop.wait(.5):
            now=time.monotonic()
            with self.lock:
                if not self.require_live or self.forecast.records:self.model.advance(self.forecast,now-previous)
                if not self.require_live or self.global_forecast.records:self.global_model.advance_to(self.model.time,self.global_forecast)
                self.revision+=1
            previous=now
    def refresh(self):
        while not self.stop.is_set():
            self.attempt=time.time()
            try:
                f=Forecast.fetch()
                with self.lock:
                    self.live_forecast=f
                    if self.mode=='historical':pass
                    elif f.records[0]['hourly']['time'][0] <= self.model.time <= f.end:
                        first_real=not self.forecast.records
                        self.forecast=f; self.error=None
                        if first_real:
                            controls=(self.model.speed,self.model.paused,self.model.rain_scale,self.model.capacity)
                            self.model=Model(time.time())
                            self.model.speed,self.model.paused,self.model.rain_scale,self.model.capacity=controls
                            self.model.initialize(f);self.model.step(self.model.fields,0)
                    else: self.error='New forecast does not cover simulation clock; reset to now to adopt it.'
            except Exception as exc:
                with self.lock: self.error=f'{type(exc).__name__}: {exc}'
            if self.stop.wait(900): break
    def refresh_global(self):
        while not self.stop.is_set():
            self.global_attempt=time.time()
            try:
                f=GlobalForecast.fetch()
                with self.lock:
                    self.live_global_forecast=f
                    if self.mode=="historical":pass
                    elif f.records[0]["hourly"]["time"][0] <= self.model.time <= f.end:
                        first_real=not self.global_forecast.records
                        self.global_forecast=f; self.global_error=None
                        if first_real:
                            self.global_model=GlobalModel(self.model.time)
                            self.global_model.advance_to(self.model.time,f)
                    else: self.global_error="New forecast does not cover clock; reset to now."
            except Exception as exc:
                with self.lock: self.global_error=f"{type(exc).__name__}: {exc}"
            if self.stop.wait(900): break
    def control(self,body):
        allowed={'speed','paused','rain_scale','capacity_mm','reset'}
        if not isinstance(body,dict) or set(body)-allowed: raise ValueError('Unknown control')
        # Validate entire request before any mutation.
        for key,low,high in [('speed',1,3600),('rain_scale',0,4),('capacity_mm',50,700)]:
            if key in body and (isinstance(body[key],bool) or not isinstance(body[key],(float,int)) or not math.isfinite(body[key]) or not low<=body[key]<=high): raise ValueError(f'{key} must be {low}..{high}')
        for key in ('paused','reset'):
            if key in body and not isinstance(body[key],bool): raise ValueError(key+' must be boolean')
        with self.lock:
            if body.get('reset'):
                self.model=Model(self.forecast.start if self.mode=="historical" else time.time()); self.model.initialize(self.forecast)
                self.global_model=GlobalModel(self.model.time)
                self.global_model.advance_to(self.model.time,self.global_forecast)
            m=self.model
            for key in ('speed','rain_scale','paused'):
                if key in body: setattr(m,key,body[key])
            if 'capacity_mm' in body:
                # Parameter change preserves saturation fraction and is a scenario reset of storage.
                ratio=body['capacity_mm']/m.capacity
                m.soil=[s*ratio for s in m.soil]; m.capacity=body['capacity_mm']; m.ledger={}
            m.advance(self.forecast,0); self.revision+=1
        return self.snapshot()

class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,fmt,*args):
        if not args or (len(args)>1 and str(args[1]) not in ('200','202')) or str(args[0]).startswith('POST'):super().log_message(fmt,*args)
    def send(self,code,data,ctype='application/json'):
        if not isinstance(data,bytes): data=json.dumps(data,allow_nan=False).encode()
        self.send_response(code); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(data))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/api/comparison': return self.send(200,self.server.engine.comparison.frame())
        if path=='/api/global-frame': return self.send(200,self.server.engine.global_snapshot())
        if path=='/api/frame': return self.send(200,self.server.engine.snapshot())
        if path=='/api/health': return self.send(200,dict(ok=True,transport='SSE',mode=self.server.engine.snapshot()['source']['mode']))
        if path=='/api/geography': return self.send(200,LAND)
        if path in ('/events','/global-events'):
            self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.send_header('Cache-Control','no-cache, no-transform'); self.send_header('X-Accel-Buffering','no'); self.send_header('Connection','close'); self.end_headers()
            try:
                while not self.server.engine.stop.is_set():
                    frame=self.server.engine.global_snapshot() if path=='/global-events' else self.server.engine.snapshot()
                    packet='id: '+str(frame['revision'])+'\nevent: frame\ndata: '+json.dumps(frame,allow_nan=False,separators=(',',':'))+'\n\n'
                    self.wfile.write(packet.encode()); self.wfile.flush()
                    if self.server.engine.stop.wait(1): break
            except (BrokenPipeError,ConnectionResetError,TimeoutError): pass
            self.close_connection=True
            return
        files={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript'),'/style.css':('style.css','text/css')}
        if path in files:
            name,ctype=files[path]; return self.send(200,(Path(__file__).parent/'static'/name).read_bytes(),ctype)
        self.send(404,{'error':'Not found'})
    def do_POST(self):
        if self.path not in ('/api/control','/api/timeline','/api/comparison','/api/scenario'): return self.send(404,{'error':'Not found'})
        # Browsers may only control this local simulator from its own origin.
        origin=self.headers.get('Origin')
        if origin and origin!='http://'+self.headers.get('Host',''): return self.send(403,{'error':'Origin rejected'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=2048: raise ValueError('Body must be 1..2048 bytes')
            body=json.loads(self.rfile.read(size))
            if self.path=='/api/scenario':
                from scenario import run
                engine=self.server.engine
                with engine.lock:
                    if engine.require_live and not engine.forecast.records:raise ValueError('Wait for real weather data')
                    forecast,start=engine.forecast,engine.model.time
                return self.send(200,run(forecast,start,body))
            if self.path=='/api/comparison':return self.send(202,self.server.engine.comparison.select(body))
            self.send(202 if self.path=='/api/timeline' and body.get('mode')=='historical' else 200,self.server.engine.set_timeline(body) if self.path=='/api/timeline' else self.server.engine.control(body))
        except (ValueError,TypeError,AttributeError) as exc: self.send(400,{'error':str(exc)})

def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--offline',action='store_true'); parser.add_argument('--allow-synthetic',action='store_true',help='Permit synthetic startup/fallback; default waits for real API data'); parser.add_argument('--port',type=int,default=8765); parser.add_argument('--host',default='127.0.0.1'); args=parser.parse_args()
    engine=Engine(args.offline,require_live=not args.offline and not args.allow_synthetic)
    server=ThreadingHTTPServer((args.host,args.port),Handler); server.daemon_threads=True; server.engine=engine
    threading.Thread(target=engine.run,daemon=True).start()
    if not args.offline:
        threading.Thread(target=engine.refresh,daemon=True).start()
        threading.Thread(target=engine.refresh_global,daemon=True).start()
    print(f'TERRA running at http://{args.host}:{server.server_port} — Ctrl+C to stop',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: engine.stop.set(); server.server_close()
if __name__=='__main__': main()
