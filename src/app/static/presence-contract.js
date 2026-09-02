export const PRESENCE_STATES = Object.freeze(['idle', 'invoked', 'thinking', 'responding', 'task_complete', 'unavailable']);

export function validatePresenceProfile(profile) {
  if (!profile || profile.record_type !== 'phoenix_embodiment_profile') throw new Error('Invalid Presence profile');
  if (!profile.phoenix_instance_id || !profile.profile_id || profile.profile_revision < 1) throw new Error('Presence ownership or revision is missing');
  if (!profile.presentation_policy || typeof profile.presentation_policy.enabled !== 'boolean') throw new Error('Presence policy is missing');
  if (!['off', 'subtle', 'expressive'].includes(profile.presentation_policy.motion)) throw new Error('Presence motion policy is invalid');
  if (!profile.fallback || !profile.fallback.accessible_name) throw new Error('Presence fallback is missing');
  return profile;
}

export function stateForEvent(eventId) {
  return ({
    'presence.invoked': 'invoked',
    'presence.request_processing_started': 'thinking',
    'presence.response_displayed': 'responding',
    'presence.returned_idle': 'idle',
    'task.research_completed': 'task_complete',
  })[eventId] || null;
}
