class ClassList { constructor() { this.values = new Set(); } add(v) { this.values.add(v); } remove(v) { this.values.delete(v); } contains(v) { return this.values.has(v); } }
class Element {
  constructor(tag='div') { this.tagName=tag; this.children=[]; this.dataset={}; this.listeners={}; this.classList=new ClassList(); this.attributes={}; this.textContent=''; this.focused=false; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  dispatchEvent(event) { (this.listeners[event.type] || []).forEach(fn => fn(event)); }
  replaceChildren(...items) { this.children=items; }
  append(...items) { this.children.push(...items); }
  setAttribute(k,v) { this.attributes[k]=String(v); }
  focus() { this.focused=true; }
}
const input = new Element('textarea');
global.document = { createElement: tag => new Element(tag), querySelector: selector => selector === '#message' ? input : null };
const windowEvents=[];
global.CustomEvent = class { constructor(type, options={}) { this.type=type; this.detail=options.detail; } };
global.window = { dispatchEvent: event => windowEvents.push(event), FawkesThreeRuntime: null };
const { PhoenixPresenceController } = await import('../../src/app/static/presence-controller.js');
const surface = new Element('button'), host = new Element('span');
const controller = new PhoenixPresenceController(surface, host);
const profile = { record_type:'phoenix_embodiment_profile', profile_id:'presence:one', phoenix_instance_id:'one', profile_revision:1,
  presentation_policy:{enabled:true,motion:'subtle',reduced_motion:false,invocation_phrase:'Hey Fawkes'},
  fallback:{accessible_name:'Fawkes is present',message:'Development body unavailable'}, health:{status:'unavailable',reason:'No GLB'}, asset:null };
await controller.mount(profile);
if (host.dataset.renderer !== 'fallback' || host.dataset.visible !== 'true') throw new Error('truthful visible fallback did not mount');
controller.event({event_id:'presence.request_processing_started',occurrence_id:'request-1'});
if (controller.health().state !== 'thinking') throw new Error('thinking lifecycle did not map');
if (controller.event({event_id:'presence.request_processing_started',occurrence_id:'request-1'}) !== 'duplicate') throw new Error('duplicate event was replayed');
surface.dispatchEvent({type:'keydown',key:'Enter',preventDefault(){}});
if (!input.focused || controller.health().state !== 'invoked') throw new Error('keyboard invocation did not reach Chat');
if (!windowEvents.some(event => event.type === 'fawkes:presence-invoked')) throw new Error('invocation event missing');
const offSurface=new Element('button'), offHost=new Element('span'), offController=new PhoenixPresenceController(offSurface,offHost);
await offController.mount({...profile,presentation_policy:{...profile.presentation_policy,enabled:false,motion:'off',reduced_motion:true}});
if (!offSurface.classList.contains('presence-off')) throw new Error('Presence Off did not hide surface');
console.log(JSON.stringify({fallback_visible:true,thinking:true,duplicate_suppressed:true,keyboard_invoked:true,presence_off:true}));
