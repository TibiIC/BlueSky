import test from 'node:test';
import assert from 'node:assert/strict';
import {createFieldOverlay} from '../src/lib/weather/overlay.ts';

test('streaming 600 frames keeps one geometry and one material alive',()=>{
 let geometryBuilds=0,materialBuilds=0,removed=0;
 const added=[];
 class Geometry {constructor(options){geometryBuilds++;this.options=options;}}
 class Material {constructor(options){materialBuilds++;this.uniforms=options.fabric.uniforms;}}
 class Appearance {static MaterialSupport={TEXTURED:{vertexFormat:{}}};constructor(options){Object.assign(this,options);}}
 class Primitive {constructor(options){Object.assign(this,options);this.show=true;}}
 const C={Material,MaterialAppearance:Appearance,Primitive,RectangleGeometry:Geometry,GeometryInstance:class{constructor(o){Object.assign(this,o);}},Rectangle:{fromDegrees:(...a)=>a},Math:{toRadians:x=>x*Math.PI/180}};
 const globe={C,viewer:{scene:{requestRender(){},primitives:{add:p=>(added.push(p),p),remove:()=>removed++}}}};
 const a={name:'buffer A'},b={name:'buffer B'};
 const overlay=createFieldOverlay(globe,'regional',[10,54,33,71],a);
 for(let i=0;i<600;i++)overlay.update(i%2?a:b,true);
 assert.equal(geometryBuilds,1);assert.equal(materialBuilds,1);assert.equal(added.length,1);
 assert.equal(added[0].appearance.material.uniforms.image,a);
 overlay.setVisible(false);assert.equal(added[0].show,false);
 overlay.update(b,true);assert.equal(added[0].show,true);
 overlay.destroy();overlay.destroy();assert.equal(removed,1);
 overlay.update(a,true);assert.equal(added[0].appearance.material.uniforms.image,b);
});
