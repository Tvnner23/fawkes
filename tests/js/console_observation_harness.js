'use strict';
const assert=require('assert');
const {consoleApi:api,rawProjection,fakeDocument,textOf}=require('./dev_console_projection_harness.js');
const fs=require('fs'),vm=require('vm'),sandbox={module:{exports:{}},Date};
vm.runInNewContext(fs.readFileSync('src/app/static/native-attention.js','utf8'),sandbox);
const native=sandbox.module.exports;
const now=Date.parse('2026-09-11T08:00:00Z');
const base=api.normalizePayloads(rawProjection,{nowMs:now,baseUrl:'https://localhost:8791/'});
const current={...base.campaigns[0],campaign_id:'new-objective',status:'failed_safe',
  managed:[], reporting:{turns:[],observed_at:new Date(now).toISOString()}};
const old={...current,campaign_id:'old-nonadjacent-trial',status:'awaiting_independent_review',
  managed:[{invocation_id:'old-trial-invocation',role:'worker',state:'running',
    updated_at:new Date(now).toISOString(),verified_at:new Date(now).toISOString()}]};
const p={...base,current_campaign_id:'new-objective',campaigns:[current,old]};
assert.strictEqual(api.selectCampaign(p.campaigns,'').campaign_id,'new-objective');
assert.strictEqual(api.selectCampaign(p.campaigns,old.campaign_id).campaign_id,old.campaign_id);
assert.ok(api.managedFeedObservation(p,'live',now).label.includes('not attached'));
const turn={role:'worker',turn_id:'turn-1',thread_id:'thread-1',invocation_id:'worker-1',
 started_at:'2026-09-11T07:59:00Z',observed_at:'2026-09-11T08:00:00Z',ended_at:'',
 active_seconds:30,waiting_seconds:30,active_verified:true,state:'running'};
current.reporting.turns=[turn];
let clocks=api.roleClocks(current,'live',now);
assert.strictEqual(clocks[0].seconds,30);assert.strictEqual(clocks[0].total,30);
assert.strictEqual(api.roleClocks(current,'live',now+5000)[0].seconds,35);
assert.strictEqual(api.roleClocks(current,'disconnected',now+60000)[0].seconds,30);
turn.state='waiting';turn.active_verified=false;
assert.strictEqual(api.roleClocks(current,'live',now+5000)[0].seconds,30);
assert.ok(api.roleClocks(current,'live',now)[0].label.includes('paused'));
turn.ended_at='2026-09-11T08:00:00Z';turn.state='completed';
current.reporting.turns.push({...turn,role:'reviewer',turn_id:'review-1',active_seconds:0,
 started_at:'2026-09-11T08:00:00Z',ended_at:'',active_verified:true,state:'running'});
clocks=api.roleClocks(current,'live',now);
assert.strictEqual(clocks[0].label,'Waiting · last turn completed');
assert.strictEqual(clocks[1].seconds,0);assert.strictEqual(clocks[1].label,'Executing');
assert.strictEqual(api.campaignObservation([current],'live',now).label,'REVIEWER EXECUTING');
assert.strictEqual(api.campaignObservation([current],'disconnected',now).label,'EXECUTION UNKNOWN');
current.reporting.turns.push({...turn,turn_id:'turn-2',active_seconds:12,waiting_seconds:0});
assert.strictEqual(api.roleClocks(current,'live',now)[0].total,42);
assert.strictEqual(api.roleClocks(JSON.parse(JSON.stringify(current)),'live',now)[0].total,42);
current.reporting.timing_history_incomplete=true;
assert.strictEqual(api.roleClocks(current,'live',now)[0].total,null);
current.managed=[{role:'worker',invocation_id:'worker-1',state:'running',
 updated_at:'2026-09-10T01:00:00Z',verified_at:new Date(now).toISOString()}];
assert.strictEqual(api.managedFeedObservation(p,'live',now).label,'◉ Live','quiet verified feed stays live');
assert.ok(api.managedFeedObservation(p,'disconnected',now).label.includes('Disconnected'));
assert.strictEqual(api.combinedOperationStatus('pi-companion',p,'live').short,'Remote unknown');
assert.strictEqual(api.combinedOperationStatus('managed-reviewer',p,'live').short,'Not attached');
assert.ok(api.combinedOperationStatus('managed-worker',p,'disconnected').detail.includes('Last activity'));
// A fresh process observation cannot override the actual native-turn state.
// Exercise both roles, identity isolation, recovery and observation freshness.
for (const role of ['worker','reviewer']) {
 const managed={role,invocation_id:role+'-current',state:'running',updated_at:new Date(now-60000).toISOString(),verified_at:new Date(now).toISOString()};
 const c={campaign_id:'bound-objective',managed:[managed],reporting:{turns:[]}};
 const projection={current_campaign_id:c.campaign_id,campaigns:[c]};
 const status=(state='live',at=now)=>api.combinedOperationStatus('managed-'+role,projection,state,at);
 assert.strictEqual(status().short,'No native turn','process start is not a native execution turn');
 const nativeTurn={...turn,role,invocation_id:managed.invocation_id,state:'running',ended_at:'',active_verified:true};
 c.reporting.turns=[{...nativeTurn,invocation_id:'older-invocation'}];
 assert.strictEqual(status().short,'No native turn','an older invocation cannot lend execution evidence');
 c.reporting.turns=[{...nativeTurn,role:role==='worker'?'reviewer':'worker'}];
 assert.strictEqual(status().short,'No native turn','the other role cannot lend execution evidence');
 c.reporting.turns=[nativeTurn];
 assert.strictEqual(status().short,'Executing');
 nativeTurn.active_verified=false;nativeTurn.state='unknown';nativeTurn.active_seconds=null;nativeTurn.duration_incomplete=true;
 assert.strictEqual(status().short,'Execution unknown');
 assert.strictEqual(api.roleClocks(c,'live',now).find(v=>v.role===role).label,'Execution unknown');
 assert.strictEqual(api.combinedOperationStatus('managed-'+role,JSON.parse(JSON.stringify(projection)),'live',now).short,'Execution unknown');
 nativeTurn.state='waiting';managed.state='waiting';
 assert.strictEqual(status().short,'Waiting');
 assert.ok(api.roleClocks(c,'live',now).find(v=>v.role===role).label.includes('Waiting for Tanner'));
 nativeTurn.state='running';nativeTurn.active_verified=true;nativeTurn.active_seconds=10;managed.state='running';
 assert.strictEqual(status('disconnected').short,'Unknown / last known');
 assert.strictEqual(status('stale').short,'Unknown / last known');
 managed.verified_at=new Date(now+60000).toISOString();
 assert.strictEqual(status().short,'Unknown / last known');
 managed.verified_at=new Date(now).toISOString();nativeTurn.observed_at=new Date(now-31000).toISOString();
 assert.strictEqual(status().short,'Execution unknown','fresh process does not refresh stale native state');
 nativeTurn.observed_at=new Date(now).toISOString();
 assert.strictEqual(status().short,'Executing','fresh authoritative recovery is visible');
 nativeTurn.ended_at=new Date(now).toISOString();nativeTurn.state='completed';nativeTurn.active_verified=false;
 assert.strictEqual(status().short,'Waiting','native turn completed; no new turn inferred');
 managed.state='completed';assert.strictEqual(status().short,'Last completed');
 managed.state='failed';assert.strictEqual(status().short,'Last failed');
}
const action={blocked_action:'tool --password="SYNTHETIC SECRET" token=marker-safe',why_required:'Necessary for "unfamiliar-task"'};
const frozen=JSON.stringify(action);
const masked=native.displayText(action.blocked_action);
assert.ok(!masked.includes('SYNTHETIC SECRET')&&!masked.includes('marker-safe'));
assert.ok(masked.includes('tool'));assert.strictEqual(JSON.stringify(action),frozen);
assert.strictEqual(native.displayText(action.why_required),action.why_required);
for(const secret of ['Authorization: Bearer TOKEN_VALUE','https://user:SECRET@example.invalid/','api_key=MARKER_123']) {
 const value=native.displayText(secret);assert.ok(!value.includes('TOKEN_VALUE')&&!value.includes('SECRET')&&!value.includes('MARKER_123'));
}
const fixture=fakeDocument();
api.renderJobs(fixture.document,fixture.byId.get('activity-feed'),[
 {job_id:'new-objective',objective:'Current failed objective',state:'failed',created_at:'2026-09-11T07:00:00Z',is_current_objective:true},
 {job_id:'old-nonadjacent-trial',objective:'Old trial',state:'waiting',created_at:'2026-09-10T01:00:00Z'}],'live');
const rendered=textOf(fixture.byId.get('activity-feed'));
assert.ok(rendered.indexOf('Current failed objective')<rendered.indexOf('Old trial'));
assert.ok(rendered.includes('CURRENT OBJECTIVE')&&rendered.includes('RETAINED JOB HISTORY'));
console.log('console-observation-ok');
