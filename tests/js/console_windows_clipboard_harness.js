const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const context={module:{exports:{}}};
vm.runInNewContext(fs.readFileSync('src/app/static/dev-console/console.js','utf8'),context);
const ui=context.module.exports;
const id='console-update-'+'a'.repeat(64),hash='b'.repeat(64);
const record={snapshot_id:id,content_sha256:hash};
function status(state,extra={}){return ui.windowsClipboardMessage({...record,windows_clipboard:{snapshot_id:id,content_sha256:hash,status:state,...extra}});}
assert.match(status('copied',{code:'verified_windows_readback',copied_at:'2026-09-12T04:00:00Z'}),/^Copied to Windows clipboard/);
assert.match(status('pending'),/pending; not confirmed/);
for(const state of ['unknown','unavailable','failed','not_requested','superseded'])assert.doesNotMatch(status(state),/^Copied/);
assert.doesNotMatch(status('copied',{content_sha256:'wrong',code:'verified_windows_readback',copied_at:'2026-09-12T04:00:00Z'}),/^Copied/);
assert.doesNotMatch(status('copied',{snapshot_id:'wrong',code:'verified_windows_readback',copied_at:'2026-09-12T04:00:00Z'}),/^Copied/);
assert.doesNotMatch(status('copied',{code:'unverified',copied_at:'2026-09-12T04:00:00Z'}),/^Copied/);
assert.doesNotMatch(status('copied',{code:'verified_windows_readback',copied_at:'invalid'}),/^Copied/);
console.log('11 Windows clipboard presentation assertions passed; no native clipboard touched');
