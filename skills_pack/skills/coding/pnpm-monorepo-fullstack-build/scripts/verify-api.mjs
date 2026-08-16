// Reusable end-to-end verification template for a running CipherSphere-style API.
// Run with: node /tmp/cs-verify.mjs
// Bash it against a live backend (default localhost:4000). Proves the whole
// auth -> E2EE messaging -> meetings -> remote-assist consent -> AI -> audit
// loop in one clean pass without shell-quoting/redaction pitfalls.
const BASE = process.env.BASE || 'http://localhost:4000/api/v1';

async function j(method, path, body, token) {
  const res = await fetch(BASE + path, {
    method,
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  return { status: res.status, json: await res.json().catch(() => null) };
}
const ok = (label, cond, extra = '') =>
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${label}${extra ? ` — ${extra}` : ''}`);

const USERS = [['alice_smoke', 'alice-secure-xyz-1'], ['bob_smoke', 'bob-secure-xyz-1']];

(async () => {
  const tok = {};
  for (const [u, p] of USERS) {
    const reg = await j('POST', '/auth/register', { username: u, password: p, displayName: u });
    if (reg.status === 409) { // already exists
      const l = await j('POST', '/auth/login', { username: u, password: p });
      tok[u] = l.json?.tokens?.accessToken;
    } else {
      tok[u] = reg.json?.tokens?.accessToken;
    }
  }

  // E2EE DM
  const conv = await j('POST', '/conversations', { type: 'dm', participantIds: [], encryption: 'e2ee' }, tok['alice_smoke']);
  ok('DM conversation created', conv.status === 201 && conv.json?.data?.encryption === 'e2ee');

  // Message (ciphertext; server must never store plaintext)
  const send = await j('POST', '/messages', { conversationId: conv.json?.data?.id, ciphertext: 'cipher-abc', iv: 'iv', type: 'text' }, tok['alice_smoke']);
  ok('Encrypted message sent', send.status === 201 && !!send.json?.data?.id);

  // Workspaces
  const ws = await j('GET', '/workspaces', null, tok['bob_smoke']);
  ok('Workspaces listed', ws.status === 200 && ws.json?.data?.length >= 1);

  // Meetings
  const meet = await j('POST', '/meetings', { title: 'Kickoff', e2ee: true }, tok['bob_smoke']);
  ok('Meeting created (E2EE)', meet.status === 201 && meet.json?.data?.e2ee === true);

  // Remote assist consent: request control, approve should DOWNGRADE to view-only
  const req = await j('POST', '/remote/request', { targetUsername: 'bob_smoke', requestedScopes: ['view', 'control_mouse'] }, tok['alice_smoke']);
  const appr = await j('POST', `/remote/sessions/${req.json?.data?.id}/respond`, { action: 'approve' }, tok['bob_smoke']);
  ok('Remote-consent downgraded to view-only',
    appr.status === 200 && appr.json?.data?.status === 'active' &&
    Array.isArray(appr.json?.data?.approvedScopes) && appr.json.data.approvedScopes.length === 1 &&
    appr.json.data.approvedScopes[0] === 'view');
  const stop = await j('POST', `/remote/sessions/${req.json?.data?.id}/stop`, {}, tok['bob_smoke']);
  ok('Emergency stop', stop.status === 200 && stop.json?.data?.stopped === true);

  // AI
  const chat = await j('POST', '/ai/chat', { message: 'hello' }, tok['bob_smoke']);
  ok('AI chat responds', chat.status === 200 && typeof chat.json?.data?.reply === 'string');

  // Audit
  const audit = await j('GET', '/audit', null, tok['alice_smoke']);
  ok('Audit log populated', audit.status === 200 && (audit.json?.meta?.total ?? 0) > 0, `${audit.json?.meta?.total} events`);

  console.log('\nDone.');
})();
