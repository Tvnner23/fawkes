import { stateForEvent, validatePresenceProfile } from './presence-contract.js';
import { PhoenixPresenceFallback } from './presence-fallback.js';
import { PhoenixThreeRenderer } from './presence-renderer-three.js';

export class PhoenixPresenceController {
  constructor(surface, host) {
    this.surface = surface; this.host = host; this.profile = null; this.renderer = null;
    this.seen = new Set(); this.state = 'unavailable'; this.lastFailure = null;
    surface.addEventListener('click', () => this.invoke());
    surface.addEventListener('keydown', event => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); this.invoke(); }
    });
  }
  async mount(profile) {
    this.profile = validatePresenceProfile(profile);
    this.surface.setAttribute('aria-label', `${profile.fallback.accessible_name}. Activate to open Chat.`);
    if (!profile.presentation_policy.enabled) {
      this.surface.classList.add('presence-off'); this.renderer = new PhoenixPresenceFallback(this.host, () => this.returnIdle()).mount(profile, 'Presence is off.'); return;
    }
    this.surface.classList.remove('presence-off');
    if (profile.asset && profile.health && profile.health.status === 'live') {
      try { this.renderer = await new PhoenixThreeRenderer(this.host, code => this.fail(code), () => this.returnIdle()).mount(profile); this.setState('idle'); return; }
      catch (error) { this.lastFailure = error.message; }
    }
    this.renderer = new PhoenixPresenceFallback(this.host, () => this.returnIdle()).mount(profile, this.lastFailure || (profile.health && profile.health.reason));
    this.setState(profile.asset ? 'idle' : 'unavailable');
  }
  event(event) {
    if (!event || !event.event_id || !event.occurrence_id) return 'invalid';
    const identity = `${event.event_id}:${event.occurrence_id}`;
    if (this.seen.has(identity)) return 'duplicate'; this.seen.add(identity);
    const state = stateForEvent(event.event_id); if (state) this.setState(state); return state || 'ignored';
  }
  setState(state) {
    this.state = state; this.surface.dataset.presenceState = state;
    if (this.renderer) this.renderer.setState(state); return state;
  }
  invoke() {
    this.event({ event_id: 'presence.invoked', occurrence_id: `invoke-${Date.now()}` });
    const input = document.querySelector('#message'); if (input) input.focus();
    window.dispatchEvent(new CustomEvent('fawkes:presence-invoked', { detail: { phoenix_instance_id: this.profile && this.profile.phoenix_instance_id } }));
  }
  returnIdle() { this.event({ event_id: 'presence.returned_idle', occurrence_id: `settled-${Date.now()}` }); }
  fail(code) {
    this.lastFailure = code; if (this.renderer) this.renderer.dispose();
    this.renderer = new PhoenixPresenceFallback(this.host, () => this.returnIdle()).mount(this.profile, `3D Presence unavailable: ${code}`); this.setState('unavailable');
  }
  health() { return { profile_revision: this.profile && this.profile.profile_revision, state: this.state,
    failure: this.lastFailure, renderer: this.renderer ? this.renderer.health() : { ready: false } }; }
  dispose() { if (this.renderer) this.renderer.dispose(); }
}
