'use strict';
const { fetchBeacon, roundAt, roundTime } = require('drand-client');
const { createHash } = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { writeFileSync } = require('node:fs');
const assert = require('node:assert/strict');
const chainHash = '52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971';
const publicKey = '83cf0f2896adee7eb8b5f01fcad3912212c437e0073e911fb90022d3e760183c8c4b450b6a0a6c3ac6a5776a2d1064510d1fec758c921cc22b0e17e63aaf4bcb5ed66304de9cf809bd274ca73bab4af5a6e9c76a4bc09e76eae8991ef5ece45a';
const hosts = ['api.drand.sh', 'drand.cloudflare.com', 'api2.drand.sh'];
const info = Object.freeze({hash:chainHash,public_key:publicKey,
  schemeID:'bls-unchained-g1-rfc9380',genesis_time:1692803367,period:3,
  groupHash:'f477d5c89f21a17c863a7f937c6a6d15859414d2be09cd448d4279af331c5d3e',
  metadata:{beaconID:'quicknet'}});
const options = { disableBeaconVerification:false, noCache:true,
  chainVerificationParams:{ chainHash, publicKey } };
function raw(host, path) {
  return execFileSync('curl', ['--proto','=https','--fail','--silent','--show-error',
    '--max-time','5','--max-filesize','16384','https://' + host + '/' + chainHash + '/' + path],
    {maxBuffer:16384});
}
async function proof(startedAt, out, transport=raw, log=writeFileSync) {
  const start = Date.parse(startedAt);
  assert.match(startedAt, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$/);
  assert(Number.isFinite(start));
  const round = roundAt(start, info) + 1;
  const scheduled = roundTime(info, round);
  assert(scheduled > start && scheduled - start <= 3000);
  assert(scheduled <= Date.now() + 3000,'B start is unexpectedly in the future');
  await new Promise(r => setTimeout(r, Math.max(0, scheduled + 1500 - Date.now())));
  const attempts=[];
  const deadline=Date.now()+23000;
  for (const [i,host] of [...hosts, ...hosts].entries()) {
    if (Date.now()+5000 > deadline) break;
    const record={host,round,requested_at:new Date().toISOString()};
    let value;
    try {
      const bytes=transport(host,'public/'+round);
      log(out+'/drand-response-'+(i+1)+'-'+host+'.json',bytes,{flag:'wx'});
      value=JSON.parse(bytes);
      assert.equal(value.round,round);
      assert.match(value.signature,/^[0-9a-f]{96}$/);
      assert.equal(createHash('sha256').update(Buffer.from(value.signature,'hex')).digest('hex'),value.randomness);
      await fetchBeacon({options,chain:()=>({info:async()=>info}),get:async()=>value},round);
    } catch (e) {
      attempts.push({...record,result:'rejected',reason:e.name});
      continue;
    }
    attempts.push({...record,result:'verified'});
    log(out+'/drand-attempts.json',JSON.stringify(attempts),{flag:'wx'});
    log(out+'/drand-chain-pinned.json',JSON.stringify(info),{flag:'wx'});
    return {source:'drand.quicknet.sha512-v1',event_id:'quicknet:'+round,
      source_timestamp:new Date(scheduled).toISOString(),
      value:createHash('sha512').update('TBP-001/v1 drand.quicknet\0','ascii')
        .update(Buffer.from(value.randomness,'hex')).digest('hex')};
  }
  log(out+'/drand-attempts.json',JSON.stringify(attempts),{flag:'wx'});
  throw new Error('No valid signature for the predetermined round within relay budget');
}
module.exports={proof};
if (require.main === module) proof(process.argv[2],process.argv[3])
  .then(x=>console.log(JSON.stringify(x)))
  .catch(e=>{ console.error(e.name); process.exitCode=1; });
