import type { Material, Primitive } from 'cesium';
import type { Globe } from '../globe/viewer.ts';

/** One persistent geometry/material per grid. No Entity material rebatching. */
export function createFieldOverlay(globe: Globe, kind: 'regional'|'global', bounds: [number,number,number,number], canvas: HTMLCanvasElement) {
 const {C,viewer}=globe;
 const material: Material=new C.Material({fabric:{type:'Image',uniforms:{image:canvas}},translucent:true});
 const primitive: Primitive=viewer.scene.primitives.add(new C.Primitive({
  geometryInstances:new C.GeometryInstance({geometry:new C.RectangleGeometry({
   rectangle:C.Rectangle.fromDegrees(...bounds),height:kind==='regional'?13000:12000,
   granularity:C.Math.toRadians(kind==='regional'?.5:1),vertexFormat:C.MaterialAppearance.MaterialSupport.TEXTURED.vertexFormat
  })}),
  appearance:new C.MaterialAppearance({material,translucent:true,flat:true,closed:false}),
  asynchronous:false,allowPicking:false
 }));
 let destroyed=false;
 return {
  update(image:HTMLCanvasElement,show:boolean){if(destroyed)return;material.uniforms.image=image;primitive.show=show;viewer.scene.requestRender();},
  setVisible(show:boolean){if(!destroyed)primitive.show=show;},
  destroy(){if(destroyed)return;destroyed=true;viewer.scene.primitives.remove(primitive);}
 };
}
