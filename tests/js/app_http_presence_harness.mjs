const base = process.env.FAWKES_TEST_BASE_URL;
const token = process.env.FAWKES_TEST_TOKEN;
const viewport = process.env.FAWKES_TEST_VIEWPORT;
if (!base || !token) throw new Error('Presence HTTP harness configuration missing');
const response = await fetch(`${base}/api/presence`, { headers: { Authorization: `Bearer ${token}` } });
if (!response.ok) throw new Error(`Presence API failed: ${response.status}`);
const profile = await response.json();

class ClassList { constructor(){this.values=new Set();} add(v){this.values.add(v);} remove(v){this.values.delete(v);} contains(v){return this.values.has(v);} }
class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};this.listeners={};this.classList=new ClassList();this.attributes={};this.textContent='';this.focused=false;}
  addEventListener(type,fn){(this.listeners[type] ||= []).push(fn);} dispatchEvent(event){(this.listeners[event.type]||[]).forEach(fn=>fn(event));}
  replaceChildren(...items){this.children=items;} append(...items){this.children.push(...items);} setAttribute(k,v){this.attributes[k]=String(v);} focus(){this.focused=true;}
}
const input=new Element('textarea');
global.document={createElement:tag=>new Element(tag),querySelector:selector=>selector==='#message'?input:null};
global.CustomEvent=class{constructor(type,options={}){this.type=type;this.detail=options.detail;}};
global.window={dispatchEvent(){},FawkesThreeRuntime:null};
const { PhoenixPresenceController } = await import('../../src/app/static/presence-controller.js');
const surface=new Element('button'), host=new Element('span');
const controller=new PhoenixPresenceController(surface,host); await controller.mount(profile);
controller.event({event_id:'presence.request_processing_started',occurrence_id:'http-request'});
const thinking=controller.health().state;
surface.dispatchEvent({type:'keydown',key:'Enter',preventDefault(){}});
console.log(JSON.stringify({viewport,owner:profile.phoenix_instance_id,health:profile.health.status,
  renderer:host.dataset.renderer,visible:host.dataset.visible==='true',thinking:thinking==='thinking',
  invoked:controller.health().state==='invoked',chat_focused:input.focused,three_dimensional_verified:false}));
