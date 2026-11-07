"""Conservative finite-volume scalar transport and a snow/soil water balance.

Concentration transport is forced by external winds, not a momentum solver.
Spherical control volumes use half-width boundary cells at inclusive grid bounds.
"""
import math

EARTH_RADIUS_M=6371000.

class Transport:
    def __init__(self,lons,lats,diffusivity_m2_s=500.):
        self.nx=len(lons); self.ny=len(lats); self.k=diffusivity_m2_s
        self.lon_edges=[lons[0]]+[(a+b)/2 for a,b in zip(lons,lons[1:])]+[lons[-1]]
        self.lat_edges=[lats[0]]+[(a+b)/2 for a,b in zip(lats,lats[1:])]+[lats[-1]]
        self.dx=[EARTH_RADIUS_M*math.radians(b-a) for a,b in zip(self.lon_edges,self.lon_edges[1:])]
        self.dy=[EARTH_RADIUS_M*math.radians(b-a) for a,b in zip(self.lat_edges,self.lat_edges[1:])]
        self.area=[EARTH_RADIUS_M*self.dx[i]*(math.sin(math.radians(self.lat_edges[j+1]))-math.sin(math.radians(self.lat_edges[j]))) for j in range(self.ny) for i in range(self.nx)]
        self.lons=lons;self.lats=lats
    def advance(self,q,u,v,dt,boundary=None):
        """Upwind fluxes + centered diffusion; adaptive positivity/CFL limit.

        q is g/m3; integrated ledger is g/m for a unit-thickness atmospheric layer.
        boundary=None means impermeable edges; otherwise use supplied exterior q.
        """
        if dt<0 or any(x<0 or not math.isfinite(x) for x in q):raise ValueError('Invalid transport input')
        n=self.nx*self.ny;current=list(q);remaining=dt;boundary_exchange=0.;steps=0
        before=sum(a*b for a,b in zip(current,self.area))
        while remaining>1e-9:
            faces=[];loss=[0.]*n
            def face(a,b,velocity,length,distance,external=None):
                # Signed flux from a to b, with None denoting the exterior.
                ca=current[a] if a is not None else external
                cb=current[b] if b is not None else external
                flux=length*(velocity*(ca if velocity>=0 else cb)-self.k*(cb-ca)/distance)
                faces.append((a,b,flux))
                # Bound total possible donor loss independently of the present gradient.
                if a is not None:loss[a]+=length*(max(0,velocity)+self.k/distance)
                if b is not None:loss[b]+=length*(max(0,-velocity)+self.k/distance)
            for j,lat in enumerate(self.lats):
                for i in range(self.nx-1):
                    a=j*self.nx+i;b=a+1
                    face(a,b,(u[a]+u[b])/2,self.dy[j],EARTH_RADIUS_M*math.cos(math.radians(lat))*math.radians(self.lons[i+1]-self.lons[i]))
            for j in range(self.ny-1):
                for i in range(self.nx):
                    a=j*self.nx+i;b=a+self.nx
                    face(a,b,(v[a]+v[b])/2,self.dx[i]*math.cos(math.radians(self.lat_edges[j+1])),EARTH_RADIUS_M*math.radians(self.lats[j+1]-self.lats[j]))
            if boundary is not None:
                for j,lat in enumerate(self.lats):
                    a=j*self.nx;b=a+self.nx-1
                    distance=EARTH_RADIUS_M*math.cos(math.radians(lat))*math.radians(self.lons[1]-self.lons[0])/2
                    face(None,a,u[a],self.dy[j],distance,boundary[a])
                    face(b,None,u[b],self.dy[j],distance,boundary[b])
                for i in range(self.nx):
                    a=i;b=(self.ny-1)*self.nx+i
                    face(None,a,v[a],self.dx[i]*math.cos(math.radians(self.lat_edges[0])),self.dy[0],boundary[a])
                    face(b,None,v[b],self.dx[i]*math.cos(math.radians(self.lat_edges[-1])),self.dy[-1],boundary[b])
            safe=min((.8*a/r for a,r in zip(self.area,loss) if r>0),default=remaining)
            h=min(remaining,safe)
            mass=[c*a for c,a in zip(current,self.area)]
            for a,b,flux in faces:
                moved=h*flux
                if a is not None:mass[a]-=moved
                else:boundary_exchange+=moved
                if b is not None:mass[b]+=moved
                else:boundary_exchange-=moved
            current=[m/a for m,a in zip(mass,self.area)]
            if min(current)<-1e-10:raise ArithmeticError('Transport positivity violation')
            current=[max(0,c) for c in current];remaining-=h;steps+=1
        after=sum(a*b for a,b in zip(current,self.area))
        return current,dict(before_g_m=before,after_g_m=after,boundary_exchange_g_m=boundary_exchange,residual_g_m=after-before-boundary_exchange,cfl_substeps=steps)

def land_step(soil,snow,precip_mm_h,et0_mm_h,temp_c,soil_temp_c,dt,capacity,field_capacity_fraction=.7):
    """All water stores/fluxes in mm water equivalent; dt seconds.

    Linear rain/snow transition -1..+1 C; degree-day melt 3 mm/(C day).
    Frozen-soil infiltration is reduced, not a heat/ice phase-change solution.
    """
    if dt<0 or capacity<=0 or min(soil,snow,precip_mm_h,et0_mm_h)<0:raise ValueError('Invalid land input')
    p=precip_mm_h*dt/3600
    rain_fraction=max(0,min(1,(temp_c+1)/2))
    rain=p*rain_fraction;snowfall=p-rain
    snow_available=snow+snowfall
    melt=min(snow_available,3*max(0,temp_c)*dt/86400)
    snow_new=snow_available-melt
    liquid=rain+melt
    unfrozen=max(.05,min(1,(soil_temp_c+2)/4))
    infiltration=min(liquid,12*unfrozen*dt/3600)
    runoff=liquid-infiltration
    wet=soil+infiltration
    runoff+=max(0,wet-capacity);wet=min(capacity,wet)
    stress=max(0,min(1,wet/(field_capacity_fraction*capacity)))
    et=min(wet,et0_mm_h*dt/3600*stress*(1 if soil_temp_c>0 else .1))
    wet-=et
    drainage=min(wet,max(0,wet-field_capacity_fraction*capacity)*(1-math.exp(-dt/86400)))
    new=wet-drainage
    ledger=dict(precip_mm=p,rain_mm=rain,snowfall_mm=snowfall,melt_mm=melt,infiltration_mm=infiltration,et_mm=et,runoff_mm=runoff,drainage_mm=drainage,storage_change_mm=new-soil,snow_storage_change_mm=snow_new-snow)
    ledger['residual_mm']=p-et-runoff-drainage-(new-soil)-(snow_new-snow)
    return new,snow_new,ledger
