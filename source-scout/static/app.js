const form = document.querySelector('#candidate-form');
const list = document.querySelector('#candidate-list');
const template = document.querySelector('#candidate-template');
const message = document.querySelector('#form-message');
const statusFilter = document.querySelector('#status-filter');
const themeFilter = document.querySelector('#theme-filter');
const logout = document.querySelector('#logout');
const installButton = document.querySelector('#install-app');
const installGuideButton = document.querySelector('#install-app-guide');
const tokenList = document.querySelector('#token-list');
const newToken = document.querySelector('#new-token');
const sourceForm = document.querySelector('#source-form');
const sourceList = document.querySelector('#source-list');
const metaConnection = document.querySelector('#meta-connection');
const instagramSearchForm = document.querySelector('#instagram-search-form');
const instagramSearchMessage = document.querySelector('#instagram-search-message');
const instagramResults = document.querySelector('#instagram-results');
const instagramResultTemplate = document.querySelector('#instagram-result-template');
let installPrompt;
let instagramItems = [];
let videoPollTimer;

const initialFilters = new URLSearchParams(location.search);
if (initialFilters.get('status')) statusFilter.value = initialFilters.get('status');
if (initialFilters.get('theme')) themeFilter.value = initialFilters.get('theme');

function setInstallButtons(visible) {
  [installButton, installGuideButton].filter(Boolean).forEach(button => button.hidden = !visible);
}

const metaResult = new URLSearchParams(location.search).get('meta');
if (metaResult) {
  const messages = {
    connected:'Meta 계정 연결을 완료했습니다.',
    cancelled:'Meta 연결을 취소했습니다.',
    invalid_state:'Meta 연결 요청이 만료되었습니다. 다시 시도해주세요.',
    error:'Meta 연결 처리 중 오류가 발생했습니다.'
  };
  history.replaceState({}, '', location.pathname);
  setTimeout(() => alert(messages[metaResult] || 'Meta 연결 상태가 변경되었습니다.'), 0);
}

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
    const error = new Error(body.error);
    error.body = body;
    throw error;
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
  clearTimeout(videoPollTimer);
  if (data.items.some(item => ['queued', 'analyzing'].includes(item.video_analysis_status))) {
    videoPollTimer = setTimeout(() => loadCandidates().catch(() => undefined), 3500);
  }
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

async function loadMetaStatus() {
  const data = await api('/api/meta/status');
  instagramSearchForm.hidden = !data.connected;
  if (!data.configured) {
    metaConnection.innerHTML = '<p class="muted">서버에 Meta 앱 설정이 필요합니다.</p>';
    return;
  }
  if (!data.connected) {
    metaConnection.innerHTML = `<div class="meta-connection-row"><div><strong>Meta 계정이 연결되지 않았습니다.</strong><small>${escapeHtml(data.error || 'Facebook 페이지와 Instagram 프로페셔널 계정을 연결하세요.')}</small></div><a class="button" href="/api/meta/connect">Meta 계정 연결</a></div>`;
    return;
  }
  const connection = data.connection;
  metaConnection.innerHTML = `<div class="meta-connection-row"><div><strong>${escapeHtml(connection.page_name)}</strong><small>Instagram @${escapeHtml(connection.ig_username || '연결됨')} · 토큰은 화면에 표시되지 않습니다.</small></div><div class="connection-actions"><button class="text-button" id="disconnect-meta" type="button">연결 해제 및 토큰 삭제</button></div></div>`;
  document.querySelector('#disconnect-meta').addEventListener('click', disconnectMeta);
}

async function disconnectMeta() {
  if (!confirm('Meta 연결을 해제하고 서버에 저장된 토큰을 삭제할까요?')) return;
  await api('/api/meta/connection', {method:'DELETE'});
  instagramItems = [];
  instagramResults.innerHTML = '';
  instagramSearchMessage.textContent = 'Meta 연결과 저장된 토큰을 삭제했습니다.';
  await loadMetaStatus();
}

function renderInstagramResults(items) {
  instagramResults.innerHTML = '';
  if (!items.length) {
    instagramResults.innerHTML = '<div class="empty">이 해시태그의 공개 검색 결과가 없습니다.</div>';
    return;
  }
  items.forEach((item, index) => {
    const node = instagramResultTemplate.content.cloneNode(true);
    const image = node.querySelector('img');
    image.src = item.thumbnail_url;
    image.alt = `${item.username || 'Instagram 게시자'} 공개 게시물 미리보기`;
    image.addEventListener('error', () => image.hidden = true);
    node.querySelector('.instagram-creator').textContent = item.username ? `@${item.username}` : '게시자 정보 없음';
    node.querySelector('.instagram-type').textContent = item.media_type || 'MEDIA';
    node.querySelector('.instagram-caption').textContent = item.caption || '캡션 없음';
    node.querySelector('.instagram-engagement').textContent = `좋아요 ${item.like_count} · 댓글 ${item.comments_count} · ${item.timestamp || '게시일 미상'}`;
    node.querySelector('a').href = item.permalink;
    node.querySelector('.save-instagram-result').addEventListener('click', event => saveInstagramCandidate(index, event.target));
    instagramResults.appendChild(node);
  });
}

async function saveInstagramCandidate(index, button) {
  const item = instagramItems[index];
  button.disabled = true;
  button.textContent = '저장 중...';
  try {
    await api('/api/candidates', {method:'POST', body:JSON.stringify({
      url:item.permalink,
      title:(item.caption || `Instagram @${item.username} 공개 게시물`).slice(0, 120),
      creator:item.username ? `@${item.username}` : '',
      description:item.caption,
      thumbnail_url:item.thumbnail_url,
      rights_status:'unknown',
      status:'new',
      source:'instagram_api',
      auto_analyze:true
    })});
    button.textContent = '후보 저장됨';
    await loadCandidates();
  } catch (error) {
    button.disabled = false;
    button.textContent = error.message.includes('이미') ? '이미 저장됨' : '다시 저장';
  }
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
  renderVideoIdeas(node, item);
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

function renderVideoIdeas(node, item) {
  const state = node.querySelector('.video-state');
  const fileInput = node.querySelector('.video-file');
  const uploadButton = node.querySelector('.upload-video');
  const analyzeButton = node.querySelector('.analyze-video');
  const progress = node.querySelector('.video-progress');
  const progressText = progress.querySelector('p');
  const ideaList = node.querySelector('.idea-list');
  const labels = {not_uploaded:'영상 없음', ready:'분석 준비', queued:'대기 중', analyzing:'분석 중', complete:'추천 완료', failed:'다시 시도'};
  const status = item.video_analysis_status || 'not_uploaded';
  state.textContent = labels[status] || status;
  state.className = `video-state ${status}`;
  analyzeButton.hidden = !item.video_uploaded || ['queued', 'analyzing'].includes(status);
  analyzeButton.textContent = status === 'failed' || status === 'complete' ? '다시 추천' : '아이디어 추천';
  if (item.video_filename) {
    node.querySelector('.video-file-label').childNodes[0].textContent = `교체 · ${item.video_filename.slice(0, 28)} `;
    uploadButton.textContent = '교체';
  }
  if (['queued', 'analyzing'].includes(status)) {
    progress.hidden = false;
    progressText.textContent = item.video_analysis_detail || '영상을 분석하고 있습니다.';
  } else if (status === 'failed') {
    progress.hidden = false;
    progress.classList.add('failed');
    progressText.textContent = item.video_analysis_detail || '분석에 실패했습니다.';
  }
  let result = {};
  try { result = JSON.parse(item.video_analysis_json || '{}'); } catch { result = {}; }
  if (result.summary) {
    const summary = document.createElement('p');
    summary.className = 'video-summary';
    summary.textContent = `영상 관찰 · ${result.summary}`;
    ideaList.appendChild(summary);
  }
  (result.ideas || []).forEach((idea, index) => {
    const card = document.createElement('article');
    card.className = 'idea-card';
    const segments = (idea.recommended_segments || []).map(segment => `${formatTime(segment.start)}–${formatTime(segment.end)} ${segment.purpose}`).join(' · ');
    card.innerHTML = `<div class="idea-card-top"><span>IDEA ${index + 1} · ${escapeHtml(idea.angle)}</span><strong>${Math.max(0, Math.min(100, Number(idea.score) || 0))}점</strong></div><h4>${escapeHtml(idea.title)}</h4><p>${escapeHtml(idea.one_line_pitch)}</p><details><summary>구성과 추천 구간 보기</summary><div class="idea-detail"><b>훅 방향</b><ul>${(idea.hook_ideas || []).map(value => `<li>${escapeHtml(value)}</li>`).join('')}</ul><b>전개</b><ol>${(idea.story_flow || []).map(value => `<li>${escapeHtml(value)}</li>`).join('')}</ol>${segments ? `<b>추천 구간</b><p>${escapeHtml(segments)}</p>` : ''}${(idea.research_needed || []).length ? `<b>추가 조사</b><p>${escapeHtml(idea.research_needed.join(', '))}</p>` : ''}</div></details>`;
    ideaList.appendChild(card);
  });
  uploadButton.addEventListener('click', async () => {
    const file = fileInput.files[0];
    if (!file) { fileInput.click(); return; }
    if (file.size > 60 * 1024 * 1024) { alert('영상은 최대 60MB까지 업로드할 수 있습니다.'); return; }
    uploadButton.disabled = true;
    uploadButton.textContent = '업로드 중…';
    const body = new FormData(); body.append('video', file);
    try {
      const response = await fetch(`/api/candidates/${item.id}/video`, {method:'POST', body});
      if (response.status === 401) { location.replace('/login'); return; }
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || '영상 업로드에 실패했습니다.');
      await loadCandidates();
    } catch (error) { alert(error.message); uploadButton.disabled = false; uploadButton.textContent = '업로드'; }
  });
  analyzeButton.addEventListener('click', async () => {
    analyzeButton.disabled = true;
    try { await api(`/api/candidates/${item.id}/video-analysis`, {method:'POST'}); await loadCandidates(); }
    catch (error) { alert(error.message); analyzeButton.disabled = false; }
  });
}

function formatTime(seconds) {
  const value = Math.max(0, Math.round(Number(seconds) || 0));
  return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`;
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
instagramSearchForm.addEventListener('submit', async event => {
  event.preventDefault();
  const hashtag = new FormData(instagramSearchForm).get('hashtag');
  instagramSearchMessage.className = 'search-message';
  instagramSearchMessage.textContent = `#${hashtag} 검색 중...`;
  instagramResults.innerHTML = '';
  try {
    const data = await api('/api/meta/hashtag-search', {method:'POST', body:JSON.stringify({hashtag})});
    instagramItems = data.items;
    instagramSearchMessage.textContent = `#${data.hashtag} 공개 게시물 ${data.count}개를 찾았습니다. 발견은 재사용 허락을 의미하지 않습니다.`;
    renderInstagramResults(data.items);
  } catch (error) {
    instagramItems = [];
    if (error.body?.review_required) {
      instagramSearchMessage.className = 'search-message review-required';
      instagramSearchMessage.textContent = 'Meta 연결은 정상입니다. 공개 해시태그 검색은 Instagram Public Content Access 앱 검수 승인 후 활성화됩니다.';
    } else {
      instagramSearchMessage.textContent = error.message;
    }
  }
});
window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault();
  installPrompt = event;
  setInstallButtons(true);
});
async function promptInstall() {
  if (!installPrompt) return;
  await installPrompt.prompt();
  installPrompt = null;
  setInstallButtons(false);
}
[installButton, installGuideButton].filter(Boolean).forEach(button => button.addEventListener('click', promptInstall));
logout.addEventListener('click', async () => {
  await fetch('/api/logout', {method: 'POST'});
  location.replace('/login');
});
loadCandidates().catch(error => list.innerHTML = `<div class="empty">${error.message}</div>`);
loadTokens().catch(() => undefined);
loadSources().catch(() => undefined);
loadMetaStatus().catch(error => metaConnection.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`);
navigator.serviceWorker?.register('/service-worker.js');
