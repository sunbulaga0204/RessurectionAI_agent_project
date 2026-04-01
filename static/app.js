/**
 * Resurrection Agent — Web Chatbot Frontend
 * Handles chat, session management, persona display, and export.
 */

const API_BASE = '';  // Same origin
let sessionId = null;
let personaData = null;

// ── DOM Elements ────────────────────────────────────────

const chatArea = document.getElementById('chat-area');
const userInput = document.getElementById('user-input');
const btnSend = document.getElementById('btn-send');
const btnAbout = document.getElementById('btn-about');
const btnExport = document.getElementById('btn-export');
const btnNewSession = document.getElementById('btn-new-session');
const aboutPanel = document.getElementById('about-panel');
const btnCloseAbout = document.getElementById('btn-close-about');

// ── Initialize ──────────────────────────────────────────

async function init() {
    try {
        const res = await fetch(`${API_BASE}/api/persona`);
        personaData = await res.json();
        renderHeader();
        renderWelcome();
    } catch (e) {
        console.error('Failed to load persona:', e);
        document.getElementById('persona-name').textContent = 'Resurrection Agent';
        renderWelcome();
    }
}

function renderHeader() {
    if (!personaData) return;
    document.getElementById('persona-name').textContent =
        personaData.name_display || personaData.name || 'Persona';
    document.getElementById('persona-era').textContent =
        personaData.era || '';
    document.title = `${personaData.name_display || 'Resurrection Agent'} — Historical Persona`;
}

function renderWelcome() {
    const name = personaData?.name_display || 'Historical Figure';
    const greeting = personaData?.greeting || 'Greetings. How may I be of assistance?';

    const suggestions = [
        'What were your key observations during your fieldwork?',
        'How do you distinguish between custom and law?',
        'What is your assessment of the educational institutions you studied?',
    ];

    const suggestionsHtml = suggestions.map(s =>
        `<button class="suggestion-chip" onclick="sendSuggestion('${s.replace(/'/g, "\\'")}')">${s}</button>`
    ).join('');

    chatArea.innerHTML = `
        <div class="welcome-card">
            <div class="welcome-icon">🎭</div>
            <h2 class="welcome-title">${escapeHtml(name)}</h2>
            <p class="welcome-greeting">"${escapeHtml(greeting)}"</p>
            <div class="welcome-suggestions">
                ${suggestionsHtml}
            </div>
        </div>
    `;
}

// ── About Panel ─────────────────────────────────────────

function renderAbout() {
    if (!personaData) return;

    document.getElementById('about-name').textContent =
        personaData.name_display || personaData.name || '';
    document.getElementById('about-meta').textContent =
        [personaData.era, personaData.field].filter(Boolean).join(' · ');
    document.getElementById('about-bio').textContent =
        personaData.bio_summary || '';

    const worksEl = document.getElementById('about-works');
    const works = personaData.major_works || [];
    if (works.length > 0) {
        worksEl.innerHTML = `
            <h3>Major Works</h3>
            <ul>${works.map(w => `<li>${escapeHtml(w)}</li>`).join('')}</ul>
        `;
    } else {
        worksEl.innerHTML = '';
    }

    document.getElementById('about-disclaimer').textContent =
        personaData.disclaimer || '';

    aboutPanel.classList.add('visible');
}

btnAbout.addEventListener('click', renderAbout);
btnCloseAbout.addEventListener('click', () => aboutPanel.classList.remove('visible'));
aboutPanel.addEventListener('click', (e) => {
    if (e.target === aboutPanel) aboutPanel.classList.remove('visible');
});

// ── Chat Logic ──────────────────────────────────────────

async function sendMessage(query) {
    if (!query.trim()) return;

    // Remove welcome card on first message
    const welcome = chatArea.querySelector('.welcome-card');
    if (welcome) welcome.remove();

    // Add user message
    appendMessage('user', query);
    userInput.value = '';
    autoResize();
    btnSend.disabled = true;

    // Show typing indicator
    showTyping();

    try {
        const res = await fetch(`${API_BASE}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, session_id: sessionId }),
        });

        const data = await res.json();
        sessionId = data.session_id;

        hideTyping();
        appendAssistantMessage(data);

    } catch (e) {
        hideTyping();
        appendMessage('assistant', 'An error occurred. Please try again.');
        console.error('Chat error:', e);
    }

    btnSend.disabled = false;
    scrollToBottom();
}

function sendSuggestion(text) {
    userInput.value = text;
    sendMessage(text);
}

function appendMessage(role, text) {
    const icon = role === 'user' ? '👤' : '🎭';
    const div = document.createElement('div');
    div.className = `message ${role}`;
    div.innerHTML = `
        <div class="message-avatar">${icon}</div>
        <div class="message-body">
            <div class="message-text">${escapeHtml(text)}</div>
        </div>
    `;
    chatArea.appendChild(div);
    scrollToBottom();
}

function appendAssistantMessage(data) {
    const div = document.createElement('div');
    div.className = 'message assistant';

    let bodyHtml = `<div class="message-text">${escapeHtml(data.answer_text || '')}</div>`;

    // Citations
    const citations = data.citations || [];
    if (citations.length > 0) {
        let citHtml = '<div class="citations">';
        citations.forEach((c, i) => {
            const ref = [c.book, c.chapter].filter(Boolean).join(', ');
            const page = c.page_number ? `p. ${c.page_number}` : '';
            const quote = c.quote || '';

            citHtml += `
                <div class="citation-card" onclick="this.classList.toggle('expanded')">
                    <div class="citation-header">
                        <span class="citation-badge">${i + 1}</span>
                        <span class="citation-ref">${escapeHtml(ref)}</span>
                        ${page ? `<span class="citation-page">📄 ${escapeHtml(page)}</span>` : ''}
                    </div>
                    ${quote ? `<div class="citation-quote">"${escapeHtml(quote)}"</div>` : ''}
                </div>
            `;
        });
        citHtml += '</div>';
        bodyHtml += citHtml;
    }

    // Follow-up
    if (data.follow_up) {
        bodyHtml += `<div class="follow-up">💡 ${escapeHtml(data.follow_up)}</div>`;
    }

    // Closing
    if (data.closing) {
        bodyHtml += `<div class="message-text" style="font-style:italic; opacity:0.7; padding:8px 18px; font-size:0.85rem;">${escapeHtml(data.closing)}</div>`;
    }

    div.innerHTML = `
        <div class="message-avatar">🎭</div>
        <div class="message-body">${bodyHtml}</div>
    `;
    chatArea.appendChild(div);
    scrollToBottom();
}

// ── Typing Indicator ────────────────────────────────────

function showTyping() {
    const div = document.createElement('div');
    div.className = 'typing-indicator';
    div.id = 'typing';
    div.innerHTML = `
        <div class="message-avatar" style="background:var(--accent-gold-dim);border:1px solid var(--accent-gold);width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:16px;">🎭</div>
        <div class="typing-dots">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>
    `;
    chatArea.appendChild(div);
    scrollToBottom();
}

function hideTyping() {
    const el = document.getElementById('typing');
    if (el) el.remove();
}

// ── Export ───────────────────────────────────────────────

btnExport.addEventListener('click', async () => {
    if (!sessionId) {
        alert('No conversation to export yet.');
        return;
    }

    try {
        const res = await fetch(`${API_BASE}/api/export`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, format: 'markdown' }),
        });

        const text = await res.text();

        // Trigger download
        const blob = new Blob([text], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `conversation_${sessionId}.md`;
        a.click();
        URL.revokeObjectURL(url);

    } catch (e) {
        console.error('Export error:', e);
        alert('Failed to export conversation.');
    }
});

// ── New Session ─────────────────────────────────────────

btnNewSession.addEventListener('click', () => {
    sessionId = null;
    renderWelcome();
});

// ── Input Handling ──────────────────────────────────────

function autoResize() {
    userInput.style.height = 'auto';
    userInput.style.height = Math.min(userInput.scrollHeight, 120) + 'px';
}

userInput.addEventListener('input', autoResize);

userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage(userInput.value);
    }
});

btnSend.addEventListener('click', () => sendMessage(userInput.value));

// ── Utilities ───────────────────────────────────────────

function scrollToBottom() {
    requestAnimationFrame(() => {
        chatArea.scrollTop = chatArea.scrollHeight;
    });
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ── Boot ────────────────────────────────────────────────

init();
