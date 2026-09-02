import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const ACTIONS = ['idle', 'invoked', 'thinking', 'responding', 'task_complete'];
const MATERIAL_CHANNELS = ['plumage_primary', 'plumage_secondary', 'expression_crest',
  'expression_feather_tips', 'flame_accent'];
const REQUIRED_BONES = ['phoenix_root', 'body', 'head', 'wing_left', 'wing_right', 'tail'];

export function applyPresencePalette(root, palette, { requireAll = true } = {}) {
  const channels = palette && palette.channels;
  if (!root || !channels) throw new Error('Presence palette channels are required');
  const found = new Set();
  root.traverse(object => {
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    materials.filter(Boolean).forEach(material => {
      const channel = channels[material.name];
      if (!channel) return;
      found.add(material.name);
      if (material.color) material.color.set(channel.base);
      if (material.emissive) material.emissive.set(channel.emissive);
      if ('emissiveIntensity' in material) material.emissiveIntensity = channel.emissive_intensity;
      material.needsUpdate = true;
    });
  });
  const missing = MATERIAL_CHANNELS.filter(name => !found.has(name));
  if (requireAll && missing.length) throw new Error(`GLB lacks renderable Presence material channels: ${missing.join(', ')}`);
  return [...found];
}

function disposeMaterial(material) {
  if (!material) return;
  Object.values(material).forEach(value => {
    if (value && value.isTexture && typeof value.dispose === 'function') value.dispose();
  });
  if (typeof material.dispose === 'function') material.dispose();
}

export async function createRuntime({ canvas, assetUrl, assetContract, palette, motion, reducedMotion, onFailure, onSettled }) {
  if (!canvas || !assetUrl) throw new Error('Presence canvas and local GLB URL are required');
  const workshopStatic = assetContract === 'presence-workshop-static-1';
  if (!workshopStatic && assetContract !== 'presence-rig-1') throw new Error('Unsupported Presence asset contract');
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true,
    powerPreference: 'low-power', failIfMajorPerformanceCaveat: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(32, 1, 0.01, 100);
  camera.position.set(0, 0.6, 4.2);
  scene.add(new THREE.HemisphereLight(0xffddb0, 0x18243a, 2.2));
  const key = new THREE.DirectionalLight(0xffb05d, 3.1); key.position.set(2, 3, 4); scene.add(key);
  const gltf = await new GLTFLoader().loadAsync(assetUrl);
  const root = gltf.scene;
  const missingBones = REQUIRED_BONES.filter(name => !root.getObjectByName(name));
  if (!workshopStatic && missingBones.length) throw new Error(`GLB lacks required Presence bones: ${missingBones.join(', ')}`);
  const materialChannels = applyPresencePalette(root, palette, { requireAll: !workshopStatic });
  scene.add(root);
  const bounds = new THREE.Box3().setFromObject(root);
  if (bounds.isEmpty()) throw new Error('Presence GLB has no renderable bounds');
  const sphere = bounds.getBoundingSphere(new THREE.Sphere());
  if (!Number.isFinite(sphere.radius) || sphere.radius <= 0) throw new Error('Presence GLB has invalid renderable bounds');
  const distance = Math.max(0.1, sphere.radius / Math.tan(THREE.MathUtils.degToRad(camera.fov * 0.5)) * 1.2);
  camera.position.set(sphere.center.x, sphere.center.y, sphere.center.z + distance);
  camera.near = Math.max(0.001, distance - sphere.radius * 2.5);
  camera.far = distance + sphere.radius * 4;
  camera.lookAt(sphere.center);
  camera.updateProjectionMatrix();
  const clips = new Map(gltf.animations.map(clip => [clip.name, clip]));
  const missing = ACTIONS.filter(name => !clips.has(`presence.${name}`));
  if (!workshopStatic && missing.length) throw new Error(`GLB lacks required Presence actions: ${missing.join(', ')}`);
  const mixer = workshopStatic ? null : new THREE.AnimationMixer(root);
  const actions = workshopStatic ? new Map() : new Map(ACTIONS.map(name => [name, mixer.clipAction(clips.get(`presence.${name}`))]));
  let active = null, disposed = false, frames = 0, state = 'idle';
  const clock = new THREE.Clock();

  function resize() {
    const width = Math.max(1, canvas.clientWidth || 1), height = Math.max(1, canvas.clientHeight || 1);
    if (canvas.width !== Math.round(width * renderer.getPixelRatio()) || canvas.height !== Math.round(height * renderer.getPixelRatio())) {
      renderer.setSize(width, height, false); camera.aspect = width / height; camera.updateProjectionMatrix();
    }
  }
  function render() {
    if (disposed) return;
    resize();
    if (mixer && !reducedMotion && motion !== 'off') mixer.update(Math.min(clock.getDelta(), 0.05));
    renderer.render(scene, camera); frames += 1;
  }
  renderer.setAnimationLoop(render);
  if (mixer) mixer.addEventListener('finished', event => {
    if (event.action !== actions.get('idle') && typeof onSettled === 'function') onSettled();
  });

  function setState(next) {
    if (workshopStatic) { state = ACTIONS.includes(next) ? next : 'idle'; return state; }
    if (!actions.has(next)) next = 'idle';
    state = next;
    const action = actions.get(next);
    if (active !== action) {
      if (active) active.fadeOut(0.18);
      action.reset().fadeIn(reducedMotion ? 0 : 0.18).play();
      action.paused = reducedMotion || motion === 'off';
      if (next !== 'idle') { action.setLoop(THREE.LoopOnce, 1); action.clampWhenFinished = true; }
      else { action.setLoop(THREE.LoopRepeat, Infinity); action.clampWhenFinished = false; }
      active = action;
    }
    return state;
  }
  setState('idle');
  canvas.addEventListener('webglcontextlost', event => {
    event.preventDefault();
    if (typeof onFailure === 'function') onFailure('webgl_context_lost');
  });
  return {
    setState,
    health: () => ({ ready: !disposed, state, frames, width: canvas.width, height: canvas.height,
      renderer: 'three', assetLoaded: true, materialChannels,
      manifestationContract: assetContract, animated: !workshopStatic,
      boundsRadius: sphere.radius }),
    dispose() {
      if (disposed) return; disposed = true; renderer.setAnimationLoop(null);
      scene.traverse(object => {
        if (object.geometry) object.geometry.dispose();
        if (Array.isArray(object.material)) object.material.forEach(disposeMaterial); else disposeMaterial(object.material);
      });
      renderer.dispose();
    },
  };
}
