'use strict';
const assert=require('assert'),fs=require('fs'),vm=require('vm');
const moduleBox={exports:{}};
vm.runInNewContext(fs.readFileSync('src/app/static/native-attention.js','utf8'),{module:moduleBox,Date});
const {explainRequest}=moduleBox.exports;
const base={campaign_id:'task-one',blocked_action:'not executed by rendering',
  requested_authority:JSON.stringify({method:'item/commandExecution/requestApproval',kind:'command'}),
  why_required:'I need to write the trial marker to check the Pi decision path.',
  resources:['/disposable/task'],expires_at:'2030-09-11T02:14:03Z',
  protocol_binding:{method:'item/commandExecution/requestApproval',managed_scope:['src/pi_trial_result.txt'],
    native_decision_choices:['approve_once','deny','cancel_campaign'],native_scope_explanation:'One exact command; no future grant.'}};
const text=explainRequest(base);
assert.equal(text.what,'Run a command requested by this managed Worker.');
assert.equal(text.why,base.why_required);
assert(text.affects.includes('src/pi_trial_result.txt')&&text.affects.includes('/disposable/task'));
assert(text.affects.includes('not proof of every effect'));
assert(text.authority.includes('once')&&text.authority.includes('does not approve code'));
assert(text.duration.includes('Response deadline:')&&text.duration.includes('separate 60-second window'));
assert(text.duration.includes('neither promises how long execution will take'));
assert(!JSON.stringify(text).includes('safe'));
for(const method of ['execCommandApproval','applyPatchApproval','item/fileChange/requestApproval','item/permissions/requestApproval','unrecognized']) {
  const value=explainRequest({...base,protocol_binding:{...base.protocol_binding,method,native_decision_choices:method==='applyPatchApproval'||method==='execCommandApproval'?['approve_once','deny']:['deny']}});
  assert(value.what&&value.why&&value.affects&&value.authority&&value.duration);
  if(method==='item/permissions/requestApproval')assert(value.what.includes('whole turn or session')&&value.authority.includes('not available'));
  if(method==='item/fileChange/requestApproval')assert(value.what.includes('does not supply the complete changes'));
  if(method==='unrecognized')assert(value.what.includes('Unknown'));
}
for(const reason of [null,42,{},'', 'Codex requested native approval'])assert(explainRequest({...base,why_required:reason}).why.includes('did not supply'));
const missing=explainRequest({resources:[{},42],expires_at:'not a date',protocol_binding:{managed_scope:[null,3]}});
assert(missing.affects.includes('not available')&&missing.affects.includes('No affected locations'));
assert(missing.duration.includes('unknown'));
const hostile='<img src=x onerror="approve()"> This command is always safe';
assert.equal(explainRequest({...base,why_required:hostile}).why,hostile,'Worker text remains attributable data, never evaluated');
assert(explainRequest({...base,protocol_binding:{...base.protocol_binding,managed_scope:['other.txt']}}).affects.includes('other.txt'));
assert(!explainRequest({...base,protocol_binding:{...base.protocol_binding,managed_scope:['other.txt']}}).affects.includes('src/pi_trial_result.txt'));
const terminal={...base,requested_authority:JSON.stringify({method:base.protocol_binding.method,kind:'writeStdin'}),protocol_binding:{...base.protocol_binding,native_decision_choices:['deny','cancel_campaign'],native_scope_explanation:'Terminal-input or undisclosed command scope cannot be approved here.'}};
assert(explainRequest(terminal).what.startsWith('Send input to a running command.'));
assert(explainRequest(terminal).authority.includes('not available'));
for(const body of [null,'truncated {',JSON.stringify({method:'another',kind:'command'})])assert(explainRequest({...terminal,requested_authority:body}).what.includes('subtype is unavailable'));
const decision={choice:'approve_once',consumed:false,claim_expires_at:'2030-09-11T02:15:00Z'};
assert(explainRequest(base,decision).duration.includes('Owner-recorded claim deadline:'));
assert(!explainRequest(base,decision).duration.includes('After approval'));
assert(explainRequest(base,{...decision,consumed:true}).duration.includes('Already consumed once'));
assert(explainRequest(base,{choice:'deny'}).duration.includes('No approval was granted'));
assert(explainRequest(base,{choice:'cancel_campaign'}).duration.includes('No approval was granted'));
console.log('permission-explanation-ok: request methods, reason attribution, unknown effects, scope, expiry, no safety inference, no cached cross-request explanation');
