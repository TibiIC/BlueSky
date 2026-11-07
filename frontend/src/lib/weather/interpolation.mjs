/** Bilinear display sampling. Missing corners stay missing; longitude can wrap. */
/** @param {ArrayLike<number|null>} values @param {number} nx @param {number} ny @param {number} x @param {number} y */
export function sampleGrid(values,nx,ny,x,y,periodic=false){
 x=periodic?((x%nx)+nx)%nx:Math.max(0,Math.min(nx-1,x));y=Math.max(0,Math.min(ny-1,y));
 const i=Math.floor(x),j=Math.floor(y),i1=periodic?(i+1)%nx:Math.min(nx-1,i+1),j1=Math.min(ny-1,j+1),fx=x-i,fy=y-j;
 const corners=[[j*nx+i,(1-fx)*(1-fy)],[j*nx+i1,fx*(1-fy)],[j1*nx+i,(1-fx)*fy],[j1*nx+i1,fx*fy]];
 let v=0;for(const [n,w] of corners){if(w<1e-12)continue;if(!Number.isFinite(values[n]))return null;v+=Number(values[n])*w;}return v;
}
/** @param {number} a @param {number} b @param {number} v */
export function smoothRamp(a,b,v){const t=Math.max(0,Math.min(1,(v-a)/(b-a)));return t*t*(3-2*t);}
