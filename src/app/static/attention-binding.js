(function(root) {
'use strict';
function canonicalAttentionIdentity(attention) {
  const binding=attention.protocol_binding||{};
  return {attention_id:attention.attention_id,campaign_id:attention.campaign_id,invocation_id:attention.invocation_id,rider_id:binding.rider_id||'tanner',recipient_sha256:binding.recipient_sha256||null,approval_binding_kind:binding.approval_binding_kind||null,approval_binding_sha256:binding.approval_binding_sha256||null,review_package_id:binding.review_package_id||null,review_package_record_sha256:binding.review_package_record_sha256||null,reviewer_worker_id:binding.reviewer_worker_id||null,reviewer_identity_sha256:binding.reviewer_identity_sha256||null,reviewer_invocation_id:binding.reviewer_invocation_id||null,candidate_snapshot_id:binding.candidate_snapshot_id||null,candidate_record_sha256:binding.candidate_record_sha256||null,mutation_digest_sha256:binding.mutation_digest_sha256||binding.workspace_changes_sha256||null,exact_change_evidence_sha256:binding.exact_change_evidence_sha256||null,authorized_scope_sha256:binding.authorized_scope_sha256||binding.allowed_scope_sha256||null,method:binding.method||null,item_id:binding.item_id||null,action_digest:binding.approved_action_sha256||null,protocol_binding_sha256:attention.protocol_binding_sha256||null,expires_at:attention.expires_at||null,decision_nonce:attention.decision_nonce||null};
}

function canonicalAttentionIdentityMatches(attention, expected, expectedAuthorityBindingSha256) {
  if (!attention || !expected) return false;
  return exactIdentityFields(canonicalAttentionIdentity(attention), expected)
    && typeof expectedAuthorityBindingSha256 === 'string'
    && attention.authority_binding_sha256 === expectedAuthorityBindingSha256;
}

function exactIdentityFields(actual, expected) {
  if (!actual || !expected || typeof actual !== 'object' || typeof expected !== 'object'
      || Array.isArray(actual) || Array.isArray(expected)) return false;
  const keys=Object.keys(expected);
  return Object.keys(actual).length === keys.length && keys.every(key =>
    Object.prototype.hasOwnProperty.call(actual,key)
    && (expected[key] === null || typeof expected[key] === 'string')
    && actual[key] === expected[key]);
}

function canonicalDecisionIdentityMatches(decision, expected, expectedAuthorityBindingSha256, choice) {
  if (!decision || !expected || decision.attention_id !== expected.attention_id
      || decision.campaign_id !== expected.campaign_id
      || decision.invocation_id !== expected.invocation_id
      || decision.choice !== choice
      || decision.protocol_binding_sha256 !== expected.protocol_binding_sha256
      || decision.authority_binding_sha256 !== expectedAuthorityBindingSha256
      || typeof decision.decision_id !== 'string' || !decision.decision_id
      || typeof decision.record_sha256 !== 'string' || !decision.record_sha256
      || decision.creates_continuing_authority !== false) return false;
  const binding=decision.authority_binding||{};
  return exactIdentityFields(binding, expected);
}

function requireCanonicalDecisionResult(result, expected, expectedAuthorityBindingSha256, choice) {
  if (!result || !canonicalAttentionIdentityMatches(result.attention, expected, expectedAuthorityBindingSha256)
      || !canonicalDecisionIdentityMatches(result.decision, expected, expectedAuthorityBindingSha256, choice)) {
    throw Object.assign(new Error('Fawkes returned a mismatched decision lifecycle. The page was refreshed without trusting it.'),
      {code:'decision_response_mismatch',status:409});
  }
  return result;
}

function canonicalFailureDecisionResult(result, expected, expectedAuthorityBindingSha256, choice) {
  if (!result || !canonicalAttentionIdentityMatches(
      result.attention, expected, expectedAuthorityBindingSha256)) return null;
  if (result.decision != null && !canonicalDecisionIdentityMatches(
      result.decision, expected, expectedAuthorityBindingSha256, choice)) return null;
  return {attention:result.attention,decision:result.decision||null};
}


const api = {canonicalAttentionIdentity, canonicalAttentionIdentityMatches, canonicalDecisionIdentityMatches, requireCanonicalDecisionResult, canonicalFailureDecisionResult};
root.FawkesAttentionBinding = api;
if (typeof module === 'object' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
