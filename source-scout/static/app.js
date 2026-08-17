const form = document.querySelector('#candidate-form');
const list = document.querySelector('#candidate-list');
const template = document.querySelector('#candidate-template');
const message = document.querySelector('#form-message');
const statusFilter = document.querySelector('#status-filter');
const themeFilter = document.querySelector('#theme-filter');
const logout = document.querySelector('#logout');
const installButton = document.querySelector('#install-app');
const tokenList = document.querySelector('#token-list');
const newToken = document.querySelector('#new-token');
const sourceForm = document.querySelector('#source-form');
const sourceList = document.querySelector('#source-list');
let installPrompt;

const statuses = {
  new: '새 후보', reviewing: '검토 중', permission_needed: '허락 필요', approved: '승인', rejected: '제외'
};
const rights = {
  unknown: '미확인', contact_needed: '연락 필요', requested: '허락 요청함', permitted: '사용 허락',
  licensed: '라이선스', public_domain: '퍼블릭 도메인', denied: '사용 불가'
};

document.querySelectorAll('input[type="range"]').forEach(input => {
  input.addEventListener('input', () => input.nextElementSibling.value = input.value);
});

function options(values, selected) {
  return Object.entries(values).map(([value, label]) =>
    `<option value="${value}" ${value === selected ? 'selected' : ''}>${label}</option>`
  ).join('');
}

async function api(path, options = {}) {
  const response = await fetch(path, {headers: {'Content-Type': 'application/json'}, ...options});
  if (response.status === 401) {
    location.replace('/login');
    throw new Error('로그인이 필요합니다.');
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({error: '요청에 실패했습니다.'}));
    throw new Error(body.error);
  }
  return response.status === 204 ? null : response.json();
}

async function loadCandidates() {
  const params = new URLSearchParams();
  if (statusFilter.value) params.set('status', statusFilter.value);
  if (themeFilter.value) params.set('theme', themeFilter.value);
  const data = await api(`/api/candidates?${params}`);
  renderStats(data.items);
  list.innerHTML = '';
  if (!data.items.length) {
    list.innerHTML = '<div class="empty">아직 조건에 맞는 후보가 없습니다.</div>';
    return;
  }
  data.items.forEach(renderCandidate);
}

async function loadTokens() {
  const data = await api('/api/mobile-tokens');
  tokenList.innerHTML = data.items.length ? data.items.map(item => `
    <div class="token-row"><div><strong>${escapeHtml(item.label)}</strong><small>생성 ${item.created_at}${item.last_used_at ? ` · 최근 사용 ${item.last_used_at}` : ''}${item.revoked_at ? ' · 폐기됨' : ''}</small></div>
    ${item.revoked_at ? '' : `<button class="text-button" data-revoke-token="${item.id}" type="button">폐기</button>`}</div>`).join('') : '<p class="muted">등록된 모바일 기기가 없습니다.</p>';
}

async function loadSources() {
  const data = await api('/api/discovery-sources');
  sourceList.innerHTML = data.items.length ? data.items.map(item => `
    <div class="token-row"><div><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.theme)} · ${escapeHtml(item.feed_url)}${item.last_checked_at ? ` · 확인 ${item.last_checked_at}` : ''}${item.last_error ? ` · 오류 ${escapeHtml(item.last_error)}` : ''}</small></div>
    <div><button class="text-button" data-run-source="${item.id}" type="button">지금 확인</button><button class="text-button" data-delete-source="${item.id}" type="button">삭제</button></div></div>`).join('') : '<p class="muted">등록된 자동 탐색 소스가 없습니다.</p>';
}

function escapeHtml(value) {
  const div = document.createElement('div');
  div.textContent = value || '';
  return div.innerHTML;
}

function renderStats(items) {
  const approved = items.filter(item => item.status === 'approved').length;
  const rightsPending = items.filter(item => ['unknown', 'contact_needed', 'requested'].includes(item.rights_status)).length;
  const average = items.length ? Math.round(items.reduce((sum, item) => sum + item.total_score, 0) / items.length) : 0;
  document.querySelector('#stats').innerHTML = `
    <div><small>표시 후보</small><strong>${items.length}</strong></div>
    <div><small>권리 확인 대기</small><strong>${rightsPending}</strong></div>
    <div><small>제작 승인</small><strong>${approved}</strong></div>
    <div><small>평균 점수</small><strong>${average}</strong></div>`;
}

function renderCandidate(item) {
  const node = template.content.cloneNode(true);
  const article = node.querySelector('.candidate');
  article.dataset.id = item.id;
  const thumbnail = node.querySelector('.candidate-thumb');
  if (item.thumbnail_url) {
    thumbnail.src = item.thumbnail_url;
    thumbnail.alt = `${item.title} 썸네일`;
    thumbnail.hidden = false;
  }
  node.querySelector('.score-ring strong').textContent = item.total_score;
  node.querySelector('.platform').textContent = item.platform;
  node.querySelector('.theme').textContent = item.theme;
  node.querySelector('h3').textContent = item.title;
  node.querySelector('a').href = item.url;
  node.querySelector('.meta').textContent = `${item.creator || '원작자 미확인'} · ${rights[item.rights_status]}`;
  node.querySelector('.notes').textContent = item.notes || '메모 없음';
  if (item.analysis_summary) {
    const analysis = document.createElement('p');
    analysis.className = 'analysis';
    analysis.textContent = `자동 제안 · ${item.analysis_summary}`;
    node.querySelector('.notes').after(analysis);
  }
  if (item.analysis_status && item.analysis_status !== 'pending') {
    const detail = document.createElement('div');
    detail.className = `analysis-status ${item.analysis_status}`;
    const labels = {metadata_only:'메타데이터만 분석', complete:'영상 분석 완료', failed:'분석 실패'};
    let ideas = [];
    try { ideas = JSON.parse(item.script_ideas || '[]'); } catch { ideas = item.script_ideas ? [item.script_ideas] : []; }
    detail.innerHTML = `<strong>${labels[item.analysis_status] || escapeHtml(item.analysis_status)}</strong><span>${escapeHtml(item.analysis_detail)}</span>${ideas.length ? `<ol>${ideas.map(idea => `<li>${escapeHtml(idea)}</li>`).join('')}</ol>` : ''}`;
    node.querySelector('.candidate-controls').before(detail);
  }
  const statusSelect = node.querySelector('.status');
  const rightsSelect = node.querySelector('.rights');
  statusSelect.innerHTML = options(statuses, item.status);
  rightsSelect.innerHTML = options(rights, item.rights_status);
  statusSelect.addEventListener('change', () => updateCandidate(item.id, {status: statusSelect.value}));
  rightsSelect.addEventListener('change', () => updateCandidate(item.id, {rights_status: rightsSelect.value}));
  node.querySelector('.analyze').addEventListener('click', async () => {
    await api(`/api/candidates/${item.id}/analyze`, {method:'POST'});
    await loadCandidates();
  });
  node.querySelector('.delete').addEventListener('click', async () => {
    if (!confirm('이 후보를 삭제할까요?')) return;
    await api(`/api/candidates/${item.id}`, {method: 'DELETE'});
    loadCandidates();
  });
  list.appendChild(node);
}

async function updateCandidate(id, payload) {
  try {
    await api(`/api/candidates/${id}`, {method: 'PATCH', body: JSON.stringify(payload)});
    await loadCandidates();
  } catch (error) {
    alert(error.message);
    await loadCandidates();
  }
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  message.textContent = '저장 중...';
  const payload = Object.fromEntries(new FormData(form));
  try {
    await api('/api/candidates', {method: 'POST', body: JSON.stringify(payload)});
    form.reset();
    document.querySelectorAll('input[type="range"]').forEach(input => input.nextElementSibling.value = input.value);
    message.textContent = '후보를 저장했습니다.';
    await loadCandidates();
  } catch (error) {
    message.textContent = error.message;
  }
});

[statusFilter, themeFilter].forEach(filter => filter.addEventListener('change', loadCandidates));
document.querySelector('#create-token').addEventListener('click', async () => {
  const label = prompt('기기 이름을 입력하세요.', '내 휴대폰');
  if (!label) return;
  const created = await api('/api/mobile-tokens', {method:'POST', body:JSON.stringify({label})});
  newToken.hidden = false;
  newToken.textContent = created.token;
  await navigator.clipboard?.writeText(created.token).catch(() => undefined);
  alert('토큰을 클립보드에 복사했습니다. 이 값은 다시 표시되지 않습니다.');
  loadTokens();
});
tokenList.addEventListener('click', async event => {
  const id = event.target.dataset.revokeToken;
  if (!id || !confirm('이 기기 토큰을 폐기할까요?')) return;
  await api(`/api/mobile-tokens/${id}`, {method:'DELETE'});
  loadTokens();
});
sourceForm.addEventListener('submit', async event => {
  event.preventDefault();
  await api('/api/discovery-sources', {method:'POST', body:JSON.stringify(Object.fromEntries(new FormData(sourceForm)))});
  sourceForm.reset();
  loadSources();
});
sourceList.addEventListener('click', async event => {
  const runId = event.target.dataset.runSource;
  const deleteId = event.target.dataset.deleteSource;
  if (runId) {
    event.target.disabled = true;
    const result = await api(`/api/discovery-sources/${runId}/run`, {method:'POST'});
    alert(`신규 ${result.created}개 · 중복 ${result.duplicates}개 · 오류 ${result.errors}개`);
    await Promise.all([loadSources(), loadCandidates()]);
  }
  if (deleteId && confirm('이 탐색 소스를 삭제할까요?')) {
    await api(`/api/discovery-sources/${deleteId}`, {method:'DELETE'});
    loadSources();
  }
});
window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault();
  installPrompt = event;
  installButton.hidden = false;
});
installButton.addEventListener('click', async () => {
  await installPrompt?.prompt();
  installPrompt = null;
  installButton.hidden = true;
});
logout.addEventListener('click', async () => {
  await fetch('/api/logout', {method: 'POST'});
  location.replace('/login');
});
loadCandidates().catch(error => list.innerHTML = `<div class="empty">${error.message}</div>`);
loadTokens().catch(() => undefined);
loadSources().catch(() => undefined);
navigator.serviceWorker?.register('/service-worker.js');
