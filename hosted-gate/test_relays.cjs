'use strict';
const assert=require('node:assert/strict');
const {proof}=require('./quicknet.cjs');
const {readFileSync}=require('node:fs');
const existing=readFileSync('./fixtures/signed-round.json');
const exact='public/34190090';
const start='2026-11-22T18:53:51.760504Z';
const logs=new Map();
const seen=[];
const log=(path,body)=>{assert(!logs.has(path));logs.set(path,body);};
(async()=>{
    const pulse=await proof(start,'/fake',(host,path)=>{
        seen.push({host,path});
        if(seen.length===1) throw new Error('offline');
        return existing;
    },log);
    assert.equal(pulse.event_id,'quicknet:34190090');
    assert.equal(seen.length,2);
    assert(seen.every(x=>x.path===exact));
    assert.notEqual(seen[0].host,seen[1].host);
    const wrongRound=JSON.parse(existing); wrongRound.round++;
    const alternateLogs=new Map();
    await assert.rejects(()=>proof(start,'/wrong',(host,path)=>{
        assert.equal(path,exact); return Buffer.from(JSON.stringify(wrongRound));
    },(p,b)=>alternateLogs.set(p,b)),/predetermined round/);
    assert.equal(JSON.parse(alternateLogs.get('/wrong/drand-attempts.json')).length,6);
    console.log('PASS same-round relay fallback and wrong-round rejection');
})().catch(e=>{console.error(e);process.exitCode=1;});
