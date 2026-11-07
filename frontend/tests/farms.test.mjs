import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validateParcels,validateSeason,stressRgb} from '../src/lib/farms/farms.ts';
const dir=new URL('../static/data/apetit/',import.meta.url);
const parcels=JSON.parse(readFileSync(new URL('apetit_parcels.json',dir)));
test('generated synthetic parcel arrays are coherent',()=>{validateParcels(parcels);assert.equal(parcels.parcels.id.length,14213);assert.match(parcels.source,/synthetic/);const broken=structuredClone(parcels);broken.parcels.lon.pop();assert.throws(()=>validateParcels(broken));});
for(const key of ['2018','2026','2050_ssp585'])test(`season ${key} covers a complete April–September replay`,()=>{const s=JSON.parse(readFileSync(new URL(`season_${key}.json`,dir)));const b=Buffer.from(s.data,'base64');validateSeason(s,parcels,b.length);assert.equal(s.days,183);assert.ok(b.every(x=>x<=201));assert.ok(b.some(x=>x>101));assert.match(s.label,/synthetic/);assert.throws(()=>validateSeason({...s,dims:[1,2,3,4]},parcels,b.length));});
test('stress ramp clamps meaningful endpoints',()=>{assert.deepEqual(stressRgb(-1),stressRgb(0));assert.deepEqual(stressRgb(2),stressRgb(1));assert.notDeepEqual(stressRgb(0),stressRgb(1));});
