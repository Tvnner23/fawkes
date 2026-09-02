export class PhoenixPresenceFallback {
  constructor(host, onSettled) { this.host = host; this.state = 'unavailable'; this.onSettled = onSettled;
    host.addEventListener('animationend', () => { if (this.state !== 'idle' && this.state !== 'unavailable' && this.onSettled) this.onSettled(); }); }
  mount(profile, reason) {
    this.host.replaceChildren();
    const mark = document.createElement('span'); mark.className = 'presence-fallback-mark'; mark.setAttribute('aria-hidden', 'true'); mark.textContent = '✦';
    const copy = document.createElement('span'); copy.className = 'presence-fallback-copy';
    const name = document.createElement('strong'); name.textContent = profile.fallback.accessible_name;
    const detail = document.createElement('small'); detail.textContent = reason || profile.fallback.message || '3D Presence is unavailable.';
    copy.append(name, detail); this.host.append(mark, copy); this.host.dataset.renderer = 'fallback';
    this.host.dataset.visible = 'true'; return this;
  }
  setState(state) { this.state = state; this.host.dataset.presenceState = state; return state; }
  health() { return { ready: true, renderer: 'fallback', visible: true, state: this.state }; }
  dispose() {}
}
