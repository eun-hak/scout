const SERVER = 'http://127.0.0.1:8765';
const button = document.querySelector('#collect');
const status = document.querySelector('#status');

function pageMetadata() {
  const meta = selector => document.querySelector(selector)?.content?.trim() || '';
  const title = meta('meta[property="og:title"]') || meta('meta[name="twitter:title"]') || document.title;
  const description = meta('meta[property="og:description"]') || meta('meta[name="description"]') || meta('meta[name="twitter:description"]');
  const thumbnail = meta('meta[property="og:image"]') || meta('meta[name="twitter:image"]');
  let creator = meta('meta[name="author"]');
  if (!creator) {
    const instagram = title.match(/\(@([^)]+)\)/);
    const tiktok = title.match(/^([^|]+) on TikTok/i);
    const youtube = document.querySelector('ytd-channel-name a, #channel-name a')?.textContent?.trim();
    creator = instagram ? `@${instagram[1]}` : tiktok ? tiktok[1].trim() : youtube || '';
  }
  return {url: location.href, title, description, creator, thumbnail_url: thumbnail};
}

async function checkServer() {
  try {
    const response = await fetch(`${SERVER}/api/health`);
    if (!response.ok) throw new Error();
    status.textContent = '준비됨 · Instagram, TikTok, YouTube 페이지에서 사용하세요.';
    button.disabled = false;
  } catch {
    status.textContent = 'Source Scout 서버가 꺼져 있습니다. 먼저 로컬 앱을 실행하세요.';
    button.disabled = true;
  }
}

button.addEventListener('click', async () => {
  button.disabled = true;
  status.textContent = '페이지 정보를 읽는 중입니다.';
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    const [{result}] = await chrome.scripting.executeScript({target: {tabId: tab.id}, func: pageMetadata});
    const response = await fetch(`${SERVER}/api/candidates`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({...result, source: 'browser_extension', auto_analyze: true, rights_status: 'unknown'})
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || '등록에 실패했습니다.');
    status.textContent = `등록 완료 · ${body.theme} · ${body.total_score}점`;
  } catch (error) {
    status.textContent = error.message || '현재 페이지를 등록할 수 없습니다.';
  } finally {
    button.disabled = false;
  }
});

checkServer();
