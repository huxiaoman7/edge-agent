const chatEl = document.getElementById('chat');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('sendBtn');
const clearBtn = document.getElementById('clearBtn');
const sessionListEl = document.getElementById('sessionList');
const newSessionBtn = document.getElementById('newSessionBtn');
const composerEl = document.querySelector('.composer');
const catAvatarEl = document.querySelector('.brand .cat-icon');
const titleCatEl = document.querySelector('.title-cat');

const STORAGE_KEY = 'ascend310.sessions.v2';
let sessions = [];
try {
  const raw = localStorage.getItem(STORAGE_KEY);
  const parsed = raw ? JSON.parse(raw) : [];
  sessions = Array.isArray(parsed) ? parsed : [];
} catch (_err) {
  sessions = [];
}
let activeSessionId = sessions[0]?.id || null;
let catSmileTimer = null;
let titleCatRunTimer = null;

function scrollToLatest(scrollComposer = false) {
  requestAnimationFrame(() => {
    chatEl.scrollTop = chatEl.scrollHeight;
    if (scrollComposer && composerEl) {
      composerEl.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  });
}

function makeId() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  return `s_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function saveSessions() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

function makeSession() {
  const id = makeId();
  return {
    id,
    title: '新会话',
    createdAt: Date.now(),
    messages: [getDefaultAssistantMessage()]
  };
}

function getDefaultAssistantMessage() {
  return {
    role: 'assistant',
    content: '喵呜~ 我是喵酱，随时待命啦！你可以直接告诉我目标，例如：310P现在支持哪些模型啦？'
  };
}

function clearActiveSession() {
  if (sendBtn.disabled) return;
  const session = getActive();
  if (!session) return;
  session.title = '新会话';
  session.messages = [getDefaultAssistantMessage()];
  saveSessions();
  renderSessions();
  renderChat();
  inputEl.focus();
}

function triggerCatSmile() {
  if (!catAvatarEl) return;
  catAvatarEl.classList.add('is-smiling');
  catAvatarEl.classList.add('is-speaking');
  if (catSmileTimer) {
    clearTimeout(catSmileTimer);
  }
  catSmileTimer = setTimeout(() => {
    catAvatarEl.classList.remove('is-smiling');
    catAvatarEl.classList.remove('is-speaking');
    catSmileTimer = null;
  }, 900);
}

function triggerTitleCatRun() {
  if (!titleCatEl) return;
  titleCatEl.classList.remove('is-running');
  void titleCatEl.offsetWidth;
  titleCatEl.classList.add('is-running');
  if (titleCatRunTimer) {
    clearTimeout(titleCatRunTimer);
  }
  titleCatRunTimer = setTimeout(() => {
    titleCatEl.classList.remove('is-running');
    titleCatRunTimer = null;
  }, 1900);
}

function ensureSession() {
  if (!activeSessionId) {
    const s = makeSession();
    sessions.unshift(s);
    activeSessionId = s.id;
    saveSessions();
  }
}

function getActive() {
  ensureSession();
  return sessions.find(s => s.id === activeSessionId);
}

function renderSessions() {
  sessionListEl.innerHTML = '';
  sessions.forEach(s => {
    const btn = document.createElement('button');
    btn.className = 'session-item' + (s.id === activeSessionId ? ' active' : '');
    btn.textContent = s.title;
    btn.onclick = () => {
      activeSessionId = s.id;
      renderSessions();
      renderChat();
    };
    sessionListEl.appendChild(btn);
  });
}

function renderChat() {
  chatEl.innerHTML = '';
  const s = getActive();
  s.messages.forEach(m => appendMessage(m.role, m.content));
  scrollToLatest(false);
}

function appendMessage(role, content) {
  const wrap = document.createElement('div');
  wrap.className = `message ${role}`;
  const roleEl = document.createElement('div');
  roleEl.className = 'role';
  roleEl.textContent = role === 'user' ? '你' : '喵酱 🐾';
  const body = document.createElement('div');
  body.className = 'content';
  body.innerHTML = renderContent(content);
  wrap.appendChild(roleEl);
  wrap.appendChild(body);
  chatEl.appendChild(wrap);
  scrollToLatest(false);
  return wrap;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function parseTableRow(line) {
  const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '');
  return trimmed.split('|').map(cell => cell.trim());
}

function isTableSeparator(line) {
  const t = line.trim();
  return /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(t);
}

function renderContent(content) {
  const lines = String(content || '').split('\n');
  const blocks = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const hasPotentialHeader = line.includes('|');
    const hasSeparator = i + 1 < lines.length && isTableSeparator(lines[i + 1]);

    if (hasPotentialHeader && hasSeparator) {
      const headers = parseTableRow(line);
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].trim() && lines[i].includes('|')) {
        rows.push(parseTableRow(lines[i]));
        i += 1;
      }
      const thead = `<thead><tr>${headers.map(h => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead>`;
      const tbody = `<tbody>${rows
        .map(r => `<tr>${r.map(c => `<td>${escapeHtml(c)}</td>`).join('')}</tr>`)
        .join('')}</tbody>`;
      blocks.push(`<div class="table-wrap"><table class="msg-table">${thead}${tbody}</table></div>`);
      continue;
    }

    if (!line.trim()) {
      blocks.push('<div class="msg-gap"></div>');
    } else {
      blocks.push(`<p>${escapeHtml(line)}</p>`);
    }
    i += 1;
  }
  return blocks.join('');
}

function summarizeTitle(text) {
  return text.length > 20 ? text.slice(0, 20) + '...' : text;
}

async function send() {
  const text = inputEl.value.trim();
  if (!text) return;

  const session = getActive();
  if (session.title === '新会话') session.title = summarizeTitle(text);

  session.messages.push({ role: 'user', content: text });
  appendMessage('user', text);
  inputEl.value = '';
  scrollToLatest(true);
  saveSessions();
  renderSessions();

  const payload = {
    message: text,
    history: session.messages.slice(-12),
    top_k: 6,
    temperature: 0.2,
    mode: 'balanced',
    enable_remote: true,
  };

  sendBtn.disabled = true;
  sendBtn.textContent = '思考中...';
  const typingEl = appendMessage('assistant', 'thinking...');
  typingEl.classList.add('typing-message');

  try {
    const controller = new AbortController();
    const timeoutMs = 20000;
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    clearTimeout(timer);
    let data = null;
    try {
      data = await resp.json();
    } catch (_err) {
      data = null;
    }
    if (!resp.ok) {
      const detail = data?.error || `HTTP ${resp.status}`;
      throw new Error(detail);
    }
    if (!data) {
      throw new Error('服务返回格式异常');
    }
    if (data.error) throw new Error(data.error);

    typingEl.remove();
    session.messages.push({ role: 'assistant', content: data.answer });
    appendMessage('assistant', data.answer);
    scrollToLatest(true);

    saveSessions();
  } catch (err) {
    typingEl.remove();
    const isAbort = err?.name === 'AbortError';
    const msg = isAbort
      ? '请求超时：服务响应较慢，请稍后重试。'
      : `请求失败：${err.message || String(err)}`;
    session.messages.push({ role: 'assistant', content: msg });
    appendMessage('assistant', msg);
    scrollToLatest(true);
    saveSessions();
  } finally {
    sendBtn.disabled = false;
    sendBtn.textContent = '发送';
    inputEl.focus();
  }
}

newSessionBtn.onclick = () => {
  const s = makeSession();
  sessions.unshift(s);
  activeSessionId = s.id;
  saveSessions();
  renderSessions();
  renderChat();
  scrollToLatest(true);
};

sendBtn.onclick = send;
clearBtn.onclick = clearActiveSession;
if (catAvatarEl) {
  catAvatarEl.addEventListener('click', triggerCatSmile);
}
if (titleCatEl) {
  titleCatEl.addEventListener('click', triggerTitleCatRun);
}
inputEl.addEventListener('keydown', (e) => {
  // Enter 发送，Shift+Enter 换行
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});

ensureSession();
renderSessions();
renderChat();
scrollToLatest(true);
