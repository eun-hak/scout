const form = document.querySelector('#candidate-form');
const list = document.querySelector('#candidate-list');
const template = document.querySelector('#candidate-template');
const message = document.querySelector('#form-message');
const statusFilter = document.querySelector('#status-filter');
const themeFilter = document.querySelector('#theme-filter');
const logout = document.querySelector('#logout');

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
  const statusSelect = node.querySelector('.status');
  const rightsSelect = node.querySelector('.rights');
  statusSelect.innerHTML = options(statuses, item.status);
  rightsSelect.innerHTML = options(rights, item.rights_status);
  statusSelect.addEventListener('change', () => updateCandidate(item.id, {status: statusSelect.value}));
  rightsSelect.addEventListener('change', () => updateCandidate(item.id, {rights_status: rightsSelect.value}));
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
logout.addEventListener('click', async () => {
  await fetch('/api/logout', {method: 'POST'});
  location.replace('/login');
});
loadCandidates().catch(error => list.innerHTML = `<div class="empty">${error.message}</div>`);
