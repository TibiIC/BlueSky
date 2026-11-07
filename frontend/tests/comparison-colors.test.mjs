import test from 'node:test';
import assert from 'node:assert/strict';
import {differenceRgb} from '../src/lib/weather/terra.ts';
test('difference colors preserve neutral zero and clamp extreme differences',()=>{
 assert.deepEqual(differenceRgb(0,10),[235,239,231]);
 assert.deepEqual(differenceRgb(-100,10),differenceRgb(-10,10));
 assert.deepEqual(differenceRgb(100,10),differenceRgb(10,10));
 const lower=differenceRgb(-10,10),higher=differenceRgb(10,10);
 assert.ok(lower[2]>lower[0]);assert.ok(higher[0]>higher[2]);
});
