import { PhoenixPresenceController } from './presence-controller.js';

const surface = document.querySelector('#phoenix-presence');
const host = document.querySelector('#presence-render-host');
export const presenceController = surface && host ? new PhoenixPresenceController(surface, host) : null;

window.addEventListener('fawkes:connected', async event => {
  if (!presenceController) return;
  try {
    const response = await fetch('/api/presence', { headers: event.detail && event.detail.token ? { Authorization: `Bearer ${event.detail.token}` } : {} });
    if (!response.ok) throw new Error('Presence profile unavailable');
    await presenceController.mount(await response.json());
  } catch (error) {
    const profile = { record_type: 'phoenix_embodiment_profile', profile_id: 'presence:fallback',
      phoenix_instance_id: 'unavailable', profile_revision: 1,
      presentation_policy: { enabled: true, motion: 'off', reduced_motion: true },
      fallback: { accessible_name: 'Fawkes', message: error.message }, health: { status: 'failed', reason: error.message } };
    await presenceController.mount(profile);
  }
});
window.addEventListener('fawkes:presence-event', event => { if (presenceController) presenceController.event(event.detail); });
window.addEventListener('fawkes:message-submitting', event => {
  if (!presenceController || !presenceController.profile) return;
  const phrase = presenceController.profile.presentation_policy.invocation_phrase;
  const message = event.detail && event.detail.message;
  if (typeof message === 'string' && message.trim().toLocaleLowerCase() === phrase.toLocaleLowerCase()) presenceController.invoke();
});
window.FawkesPresence = { controller: presenceController, health: () => presenceController && presenceController.health() };
