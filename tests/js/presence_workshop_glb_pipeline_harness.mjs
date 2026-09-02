import fs from 'node:fs';
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { applyPresencePalette } from '../../src/app/presence-three-entry.js';

if (!process.env.FAWKES_TEST_GLB) throw new Error('workshop GLB path missing');
global.ProgressEvent ??= class ProgressEvent { constructor(type, values={}) { this.type=type; Object.assign(this, values); } };
global.self ??= globalThis;
global.createImageBitmap ??= async () => ({width: 1, height: 1, close() {}});
const bytes = fs.readFileSync(process.env.FAWKES_TEST_GLB);
const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
const gltf = await new Promise((resolve, reject) => new GLTFLoader().parse(buffer, '', resolve, reject));
const bounds = new THREE.Box3().setFromObject(gltf.scene);
const sphere = bounds.getBoundingSphere(new THREE.Sphere());
if (bounds.isEmpty() || !Number.isFinite(sphere.radius) || sphere.radius <= 0) throw new Error('workshop GLB has invalid runtime bounds');
let meshes = 0, skinnedMeshes = 0, materials = 0;
gltf.scene.traverse(object => {
  if (object.isMesh) meshes += 1;
  if (object.isSkinnedMesh) skinnedMeshes += 1;
  const list = Array.isArray(object.material) ? object.material : [object.material];
  materials += list.filter(Boolean).length;
});
const channels = applyPresencePalette(gltf.scene, {channels: {}}, {requireAll: false});
console.log(JSON.stringify({workshop_only:true, mesh_loaded:meshes > 0, meshes, skinned_meshes:skinnedMeshes,
  materials, animations:gltf.animations.map(clip => clip.name), palette_channels_applied:channels,
  bounds:{min:bounds.min.toArray(), max:bounds.max.toArray(), radius:sphere.radius},
  runtime_parse:true}));
