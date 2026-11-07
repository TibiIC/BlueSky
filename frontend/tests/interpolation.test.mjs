import {test} from 'node:test';
import assert from 'node:assert/strict';
import {sampleGrid,smoothRamp} from '../src/lib/weather/interpolation.mjs';
test('bilinear sampling preserves centers and a linear field',()=>{assert.equal(sampleGrid([0,2,4,6],2,2,.25,.5),2.5);assert.equal(sampleGrid([0,2,4,6],2,2,1,1),6);});
test('global sampling is continuous across the dateline',()=>{const a=[2,4,6,8];assert.equal(sampleGrid(a,4,1,-.5,0,true),5);assert.equal(sampleGrid(a,4,1,3.5,0,true),5);});
test('missing observations are not interpolated into invented values',()=>{assert.equal(sampleGrid([1,NaN,2,3],2,2,.5,.5),null);assert.equal(sampleGrid([1,NaN,2,3],2,2,0,0),1);});
test('rain edges fade continuously',()=>{assert.equal(smoothRamp(.05,.15,0),0);assert.ok(Math.abs(smoothRamp(.05,.15,.1)-.5)<1e-12);assert.equal(smoothRamp(.05,.15,1),1);});
