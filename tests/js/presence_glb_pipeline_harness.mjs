import fs from 'node:fs';
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { applyPresencePalette } from '../../src/app/presence-three-entry.js';

if (!process.env.FAWKES_TEST_GLB) throw new Error('synthetic fixture path missing');
global.ProgressEvent ??= class ProgressEvent { constructor(type, values={}) { this.type=type; Object.assign(this, values); } };
const bytes = fs.readFileSync(process.env.FAWKES_TEST_GLB);
const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
const gltf = await new Promise((resolve, reject) => new GLTFLoader().parse(buffer, '', resolve, reject));
const palette = {channels: {
  plumage_primary: {role:'stable_rider_primary', base:'#112233', emissive:'#010203', emissive_intensity:0.25},
  plumage_secondary: {role:'stable_phoenix_secondary', base:'#445566', emissive:'#040506', emissive_intensity:0.5},
  expression_crest: {role:'transient_expression_crest', base:'#778899', emissive:'#070809', emissive_intensity:0.75},
  expression_feather_tips: {role:'transient_expression_feather_tips', base:'#aabbcc', emissive:'#0a0b0c', emissive_intensity:1.0},
  flame_accent: {role:'separable_flame_effect', base:'#ddeeff', emissive:'#ff3300', emissive_intensity:2.0},
}};
const channels = applyPresencePalette(gltf.scene, palette);
const clips = new Map(gltf.animations.map(clip => [clip.name, clip]));
const required = ['idle','invoked','thinking','responding','task_complete'];
if (required.some(name => !clips.has(`presence.${name}`))) throw new Error('fixture actions did not load');
const bones = ['phoenix_root','body','head','wing_left','wing_right','tail'];
if (bones.some(name => !gltf.scene.getObjectByName(name))) throw new Error('fixture semantic rig did not load');
const mixer = new THREE.AnimationMixer(gltf.scene);
const action = mixer.clipAction(clips.get('presence.invoked')).setLoop(THREE.LoopOnce, 1).play();
mixer.update(0.5);
const animated = Math.abs(gltf.scene.children[0].quaternion.y) > 0.01;
const materials = {};
gltf.scene.traverse(object => {
  const list = Array.isArray(object.material) ? object.material : [object.material];
  list.filter(Boolean).forEach(material => { materials[material.name] = {
    color: `#${material.color.getHexString()}`, emissive: `#${material.emissive.getHexString()}`,
    intensity: material.emissiveIntensity,
  }; });
});
console.log(JSON.stringify({fixture_only:true,mesh_loaded:gltf.scene.children.length>0,
  actions_loaded:clips.size===5,rig_loaded:true,animated,channels,materials}));
