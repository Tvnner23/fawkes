export class PhoenixThreeRenderer {
  constructor(host, onFailure, onSettled) { this.host = host; this.onFailure = onFailure; this.onSettled = onSettled; this.runtime = null; }
  async mount(profile) {
    if (!profile.asset || !profile.asset.url) throw new Error('No validated local Phoenix GLB is installed');
    if (!window.FawkesThreeRuntime || typeof window.FawkesThreeRuntime.createRuntime !== 'function') throw new Error('Three.js Presence runtime is unavailable');
    const canvas = document.createElement('canvas'); canvas.className = 'presence-canvas'; canvas.setAttribute('aria-hidden', 'true');
    this.host.replaceChildren(canvas); this.host.dataset.renderer = 'three';
    this.runtime = await window.FawkesThreeRuntime.createRuntime({ canvas, assetUrl: profile.asset.url,
      assetContract: profile.asset.rig_contract_version,
      palette: profile.palette,
      motion: profile.presentation_policy.motion, reducedMotion: profile.presentation_policy.reduced_motion,
      onFailure: this.onFailure, onSettled: this.onSettled });
    this.host.dataset.visible = 'true'; return this;
  }
  setState(state) { return this.runtime ? this.runtime.setState(state) : 'unavailable'; }
  health() { return this.runtime ? this.runtime.health() : { ready: false, renderer: 'three' }; }
  dispose() { if (this.runtime) this.runtime.dispose(); this.runtime = null; }
}
