'use strict';
const assert=require('assert');
const fs=require('fs');
const vm=require('vm');
const crypto=require('crypto');
const text=process.argv.includes('--escaping-short') ? 'x'+'\0'.repeat(1998)+'y'
  : 'Purpose: preserve the current job.\n'+('é'.repeat(1500));
const digest=crypto.createHash('sha256').update(text).digest('hex');
let calls=0,bad=false;
const sandbox={module:{exports:{}},TextEncoder,Map,Uint8Array,console,
  crypto:crypto.webcrypto,fetch:async function(url,options){
    calls++;assert.equal(url,'/api/development/dev-console/objectives/campaign-one/'+digest);
    assert.equal(options.credentials,'same-origin');assert.equal(options.cache,'no-store');
    return {ok:true,text:async()=>JSON.stringify({campaign_id:'campaign-one',objective:bad?'not the original':text,
      sha256:digest,byte_length:Buffer.byteLength(text),creates_authority:false})};
  }};
sandbox.globalThis=sandbox;
vm.runInNewContext(fs.readFileSync('src/app/static/dev-console/console.js','utf8'),sandbox);
const api=sandbox.module.exports;
class El {
  constructor(){this.children=[];this.style={};this.dataset={};this.events={};this.textContent='';}
  setAttribute(){}
  append(...nodes){this.children.push(...nodes);}
  addEventListener(k,fn){this.events[k]=fn;}
}
const doc={createElement:()=>new El()};
const source={sha256:digest,byte_length:Buffer.byteLength(text),excerpt:true};
const job={job_id:'campaign-one',objective_source:source};
async function main(){
  assert(api.normalizeObjectiveSource(source));
  assert(api.normalizeObjectiveSource({...source,byte_length:2000}));
  for(const value of [{...source,sha256:'nothex'},{...source,byte_length:32001},{...source,byte_length:0},{...source,excerpt:false},null])
    assert.equal(api.normalizeObjectiveSource(value),null);
  const invalid=new El();api.appendFullObjective(doc,invalid,{...job,job_id:'../other'});
  assert.equal(invalid.children.length,0);
  const target=new El();api.appendFullObjective(doc,target,job);
  assert.equal(calls,0);await target.children[0].events.click();
  assert.equal(target.children[1].textContent,text);assert.equal(calls,1);
  const refreshed=new El();api.appendFullObjective(doc,refreshed,job);
  assert.equal(refreshed.children[1].textContent,text);assert.equal(calls,1);
  bad=true;await refreshed.children[0].events.click();
  assert(refreshed.children[1].textContent.includes('could not be verified'));
  const recovered=new El();api.appendFullObjective(doc,recovered,job);
  assert.equal(recovered.children[1].textContent,text);
  assert.equal(recovered.children[0].disabled,undefined);
  const excerpt='x'.repeat(1500)+' [objective excerpt; complete text in Details]';
  const campaign=api.normalizeCampaignProjection({campaign_id:'campaign-one',status:'succeeded',objective:excerpt,objective_source:source});
  assert.equal(campaign.objective,excerpt);assert.equal(campaign.objective_source.sha256,digest);
  console.log('objective-render-binding-refresh-failure-ok');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
