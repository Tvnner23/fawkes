// One resident, one rendering surface. Navigation never remounts the model.
// Positions/preferences contain no chat content and never leave the browser.
export function mountResident(surface, controller) {
  const dialog = document.querySelector('#resident-actions');
  const input = document.querySelector('#message');
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  let view = 'chat', priorFocus = null, animation = null, frame = null, last = null;
  let reply = null, typing = false, step = 0;
  const perches = new Map();
  const emit = (name, detail) => window.dispatchEvent(new CustomEvent(name, { detail }));
  const detail = document.querySelector('#detail-panel');
  const auth = document.querySelector('#auth');
  function position() {
    frame = null;
    if (document.hidden || surface.classList.contains('presence-off')) return;
    if (!auth.classList.contains('hidden')) { surface.style.visibility = 'hidden'; return; }
    const inDetail = !detail.classList.contains('hidden');
    const page = inDetail ? detail.querySelector('.detail-sheet') : document.querySelector(`#${view}-view`);
    if (!page || page.classList.contains('hidden')) return;
    const bounds = page.getBoundingClientRect();
    const viewport = window.visualViewport;
    const top = Math.max(bounds.top, viewport ? viewport.offsetTop : 0);
    const bottom = Math.min(bounds.bottom, viewport ? viewport.offsetTop + viewport.height : innerHeight);
    const size = surface.getBoundingClientRect();
    if (bottom - top < size.height) { surface.style.visibility = 'hidden'; return; }
    surface.style.visibility = '';
    let target = inDetail ? 'detail' : view;
    const remembered = perches.get(target);
    let y = top + (remembered ? remembered.offset : 8);
    if (!inDetail && view === 'chat') {
      if (typing || document.activeElement === input) { target = 'chat:composer'; y = input.getBoundingClientRect().top - 12; }
      else if (reply && reply.isConnected) {
        const box = reply.getBoundingClientRect();
        const list = document.querySelector('#messages').getBoundingClientRect();
        if (box.top >= list.top && box.top + size.height <= list.bottom) { target = 'chat:reply'; y = box.top; }
      }
    }
    y = Math.max(top + 4, Math.min(y, bottom - size.height - 4));
    const x = Math.max(bounds.left, Math.min(bounds.right - size.width - 4, innerWidth - size.width - 4));
    // Stable logical identities only; never retain DOM from a replaced page.
    perches.set(target, { offset: y - top });
    const moving = last && (Math.abs(last.x - x) + Math.abs(last.y - y) > 8);
    if (animation) animation.cancel();
    surface.style.left = `${x}px`; surface.style.top = `${y}px`;
    surface.dataset.perch = target;
    const policy = controller.profile && controller.profile.presentation_policy;
    if (moving && !reduced.matches && policy && !policy.reduced_motion && policy.motion !== 'off' && surface.animate) {
      // Flight stays inside the reserved side rail, never over controls/text.
      const lift = (++step % 3) * 2 + 5;
      animation = surface.animate([{ transform: `translateY(${last.y - y}px)` },
        { transform: `translateY(${(last.y - y) / 2 - lift}px)` }, { transform: 'translateY(0)' }],
        { duration: 280 + step % 3 * 45, easing: 'ease-in-out' });
      if (controller.renderer && controller.renderer.runtime && controller.renderer.runtime.react) controller.renderer.runtime.react(step);
    }
    last = { x, y };
  }
  function schedule() { if (!frame) frame = requestAnimationFrame(position); }
  function lookToward(x, y) {
    const runtime = controller.renderer && controller.renderer.runtime;
    if (!runtime || !runtime.look || document.hidden) return;
    const box = surface.getBoundingClientRect();
    runtime.look(Math.max(-1, Math.min(1, (x - box.left - box.width / 2) / innerWidth)),
      Math.max(-1, Math.min(1, (y - box.top - box.height / 2) / innerHeight)));
  }
  document.addEventListener('pointerdown', event => lookToward(event.clientX, event.clientY), { passive: true });
  document.addEventListener('focusin', event => { const box = event.target.getBoundingClientRect(); lookToward(box.left + box.width / 2, box.top + box.height / 2); });
  surface.addEventListener('pointerdown', () => { priorFocus = document.activeElement; }, { passive: true });
  document.addEventListener('focusin', event => { if (event.target !== surface && !dialog.contains(event.target)) priorFocus = event.target; });
  window.addEventListener('fawkes:presence-invoked', () => {
    if (!dialog.open) { dialog.showModal(); dialog.querySelector('button').focus({ preventScroll: true }); }
  });
  dialog.addEventListener('close', () => { if (priorFocus && priorFocus.isConnected) priorFocus.focus({ preventScroll: true }); priorFocus = null; });
  dialog.addEventListener('click', event => {
    const button = event.target.closest('[data-resident-action]');
    if (!button) { if (event.target === dialog) dialog.close(); return; }
    const action = button.dataset.residentAction;
    const returnFocus = priorFocus;
    if (action !== 'close') priorFocus = null;
    dialog.close();
    if (action === 'settings') emit('fawkes:navigate', { view: 'settings' });
    if (action === 'requests') emit('fawkes:open-requests', { returnFocus });
    if (action === 'project' || action === 'memory') emit('fawkes:draft-starter', {
      text: action === 'project' ? 'Continue our project. Use our accessible conversation context; ask me if the next step is unclear.' : 'Show me what you remember, respecting my Memory and recording settings.' });
  });
  input.addEventListener('focus', () => { typing = true; schedule(); });
  input.addEventListener('input', () => { typing = document.activeElement === input; schedule(); });
  input.addEventListener('blur', () => { typing = false; schedule(); });
  window.addEventListener('fawkes:view-changed', event => { view = event.detail.view; schedule(); });
  window.addEventListener('fawkes:message-added', event => { if (event.detail.role === 'assistant') reply = event.detail.node; schedule(); });
  window.addEventListener('fawkes:connected', schedule);
  new MutationObserver(schedule).observe(surface, { attributes: true, attributeFilter: ['class'] });
  new MutationObserver(schedule).observe(detail, { attributes: true, attributeFilter: ['class'] });
  new MutationObserver(schedule).observe(auth, { attributes: true, attributeFilter: ['class'] });
  new ResizeObserver(schedule).observe(document.querySelector('.shell'));
  document.addEventListener('scroll', schedule, { capture: true, passive: true });
  window.addEventListener('resize', schedule, { passive: true });
  if (window.visualViewport) {
    const fit = () => { document.documentElement.style.setProperty('--app-height', `${window.visualViewport.height}px`); schedule(); };
    window.visualViewport.addEventListener('resize', fit, { passive: true });
    window.visualViewport.addEventListener('scroll', schedule, { passive: true }); fit();
  }
  document.addEventListener('visibilitychange', () => { if (animation) animation.cancel(); if (!document.hidden) schedule(); });
  reduced.addEventListener('change', () => { if (animation) animation.cancel(); schedule(); });
  schedule();
  return { perches, schedule };
}
