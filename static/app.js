/**
 * Resurrection Agent — Web Chatbot Frontend
 * Handles chat, session management, persona display, and export.
 */

const API_BASE = '';  // Same origin
let sessionId = null;
let personaData = null;

// ── DOM Elements ────────────────────────────────────────

const chatArea = document.getElementById('chat-area');
const chatScroller = document.getElementById('chat-scroller');
const userInput = document.getElementById('user-input');
const btnSend = document.getElementById('btn-send');
const btnAbout = document.getElementById('btn-about');
const btnExport = document.getElementById('btn-export');
const btnExportSidebar = document.getElementById('btn-export-sidebar');
const btnNewSession = document.getElementById('btn-new-session');
const aboutPanel = document.getElementById('about-panel');
const btnCloseAbout = document.getElementById('btn-close-about');
const btnMobileMenu = document.getElementById('btn-mobile-menu');
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebar-overlay');

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
        `<button class="bg-surface-container-low hover:bg-surface-container-high text-secondary hover:text-primary border border-outline-variant/20 px-4 py-2 rounded-full text-xs font-medium transition-all flex items-center gap-2" onclick="sendSuggestion('${s.replace(/'/g, "\\'")}')"><span class="text-primary/60">💡</span> ${escapeHtml(s)}</button>`
    ).join('');

    chatArea.innerHTML = `
        <div class="relative group welcome-card mt-12 mb-24">
            <div class="absolute -left-12 top-4 w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center text-primary border border-primary/20 hidden md:flex">
                <span class="material-symbols-outlined text-base" data-icon="history_edu">history_edu</span>
            </div>
            <div class="bg-surface-container-highest/20 rounded-3xl p-8 relative overflow-hidden backdrop-blur-sm border border-outline-variant/5 text-center">
                <div class="vellum-grain absolute inset-0 pointer-events-none"></div>
                <h2 class="font-headline text-3xl leading-relaxed text-primary letterpress mb-4">${escapeHtml(name)}</h2>
                <div class="font-headline text-xl leading-relaxed text-on-surface mb-8 italic">
                    "${escapeHtml(greeting)}"
                </div>
                <div class="flex flex-wrap gap-2 justify-center mt-6 border-t border-outline-variant/10 pt-6">
                    ${suggestionsHtml}
                </div>
            </div>
        </div>
    `;
}

// ── Mobile Sidebar ──────────────────────────────────────

function toggleMenu() {
    const isClosed = sidebar.classList.contains('-translate-x-full');
    if (isClosed) {
        sidebar.classList.remove('-translate-x-full');
        sidebarOverlay.classList.remove('hidden');
    } else {
        sidebar.classList.add('-translate-x-full');
        sidebarOverlay.classList.add('hidden');
    }
}

if (btnMobileMenu && sidebar && sidebarOverlay) {
    btnMobileMenu.addEventListener('click', toggleMenu);
    sidebarOverlay.addEventListener('click', toggleMenu);
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
            <h3 class="text-primary text-sm uppercase tracking-widest mb-2 font-bold">Major Works</h3>
            <ul class="list-disc list-inside text-sm text-secondary space-y-1">${works.map(w => `<li>${escapeHtml(w)}</li>`).join('')}</ul>
        `;
    } else {
        worksEl.innerHTML = '';
    }

    document.getElementById('about-disclaimer').textContent =
        personaData.disclaimer || '';

    aboutPanel.classList.remove('opacity-0', 'pointer-events-none');
}

btnAbout.addEventListener('click', renderAbout);
btnCloseAbout.addEventListener('click', () => aboutPanel.classList.add('opacity-0', 'pointer-events-none'));
aboutPanel.addEventListener('click', (e) => {
    if (e.target === aboutPanel) aboutPanel.classList.add('opacity-0', 'pointer-events-none');
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
    const div = document.createElement('div');
    if (role === 'user') {
        div.className = "flex justify-end w-full";
        div.innerHTML = `
            <div class="max-w-[85%] bg-surface-container-high/40 border border-outline-variant/10 px-6 py-4 rounded-2xl backdrop-blur-md">
                <p class="text-on-surface-variant font-light leading-relaxed">${escapeHtml(text)}</p>
            </div>
        `;
    } else {
        // Simple error or fallback
        div.innerHTML = `<div class="text-error bg-error-container/20 p-4 rounded-xl text-center text-sm">${escapeHtml(text)}</div>`;
    }
    chatArea.appendChild(div);
    scrollToBottom();
}

function appendAssistantMessage(data) {
    const div = document.createElement('div');
    div.className = 'relative group mb-8';

    const answerMode = data.answer_mode || 'elaborated';
    const quotePrimary = data.quote_primary || '';
    const citations = data.citations || [];

    // ── Quote-primary block (always shown if present) ──
    let quoteBlockHtml = '';
    if (quotePrimary) {
        // Find first citation source label for attribution
        const firstCit = citations[0];
        const attribution = firstCit
            ? `${firstCit.book || ''}${firstCit.chapter ? ', ' + firstCit.chapter : ''}${firstCit.page_number ? ', p. ' + firstCit.page_number : ''}`
            : '';

        quoteBlockHtml = `
            <div class="font-headline text-xl md:text-2xl leading-relaxed text-on-surface letterpress mb-6 border-l-4 border-primary/60 pl-6 py-2 italic">
                "${escapeHtml(quotePrimary)}"
                ${attribution ? `<span class="block text-xs not-italic text-primary/70 mt-2 font-body tracking-widest uppercase">${escapeHtml(attribution)}</span>` : ''}
            </div>
        `;
    }

    // ── Answer text (framing in direct_quote mode, full prose in elaborated mode) ──
    let answerHtml = '';
    if (answerMode === 'elaborated' || !quotePrimary) {
        // Elaborated: render full answer_text as prose paragraphs
        const paragraphs = (data.answer_text || '').split('\n').filter(p => p.trim() !== '');
        if (paragraphs.length > 0) {
            answerHtml = `<div class="space-y-4 font-body text-secondary leading-relaxed opacity-90 mb-6">${paragraphs.map(p => `<p>${escapeHtml(p)}</p>`).join('')}</div>`;
        }
    } else if (answerMode === 'direct_quote' && data.answer_text && data.answer_text.trim()) {
        // Direct-quote framing text (e.g. attribution sentence): subtle, below the pull-quote
        answerHtml = `<p class="text-xs text-secondary/60 font-body italic mb-4">${escapeHtml(data.answer_text)}</p>`;
    }

    // ── Citation cards ──
    const citationCardsHTML = citations.map((c, i) => {
        const ref = [c.book, c.chapter].filter(Boolean).join(', ');
        const page = c.page_number ? `p. ${c.page_number}` : '';
        const quote = c.quote || '';

        return `
            <div class="mt-4 p-4 bg-surface-container-highest/50 border border-primary/20 rounded-xl">
                <span class="block text-[0.6rem] uppercase tracking-widest text-primary font-bold mb-1">Primary Source [${i+1}]</span>
                ${quote ? `<span class="block text-sm italic font-headline leading-snug text-secondary-fixed">"${escapeHtml(quote)}"</span>` : ''}
                <span class="block text-[0.6rem] text-primary/60 mt-2 text-right">${escapeHtml(ref)} ${page}</span>
            </div>
        `;
    }).join('');

    // ── Follow-up chip ──
    let followUpHtml = '';
    if (data.follow_up) {
        followUpHtml = `
            <div class="mt-8 pt-6 border-t border-outline-variant/10">
                <p class="text-sm text-primary mb-3">💡 Explore further:</p>
                <button class="bg-surface-container border border-outline-variant/20 px-4 py-2 rounded-xl text-xs font-medium hover:bg-surface-container-high text-secondary transition-all" onclick="sendSuggestion('${data.follow_up.replace(/'/g, "\\'")}')">
                    ${escapeHtml(data.follow_up)}
                </button>
            </div>
        `;
    }

    div.innerHTML = `
        <div class="absolute -left-12 top-4 w-8 h-8 rounded-full bg-primary/10 items-center justify-center text-primary border border-primary/20 hidden md:flex">
            <span class="material-symbols-outlined text-base" data-icon="history_edu">history_edu</span>
        </div>
        <div class="bg-surface-container-highest/20 rounded-3xl p-6 md:p-8 relative overflow-hidden backdrop-blur-sm border border-outline-variant/5">
            <div class="vellum-grain absolute inset-0 pointer-events-none"></div>
            ${quoteBlockHtml}
            ${answerHtml}
            ${citations.length > 0 ? `<div class="border-t border-outline-variant/10 pt-4"><p class="text-xs uppercase tracking-widest text-secondary/60 mb-2 font-bold">Documented References</p>${citationCardsHTML}</div>` : ''}
            ${followUpHtml}
            ${data.closing ? `<div class="mt-4 text-xs italic text-secondary/50 text-right">${escapeHtml(data.closing)}</div>` : ''}
        </div>
    `;

    chatArea.appendChild(div);
    scrollToBottom();
}

// ── Typing Indicator ────────────────────────────────────

function showTyping() {
    const div = document.createElement('div');
    div.className = 'relative group opacity-50 mb-8';
    div.id = 'typing';
    div.innerHTML = `
        <div class="absolute -left-12 top-4 w-8 h-8 rounded-full bg-surface-container-highest/50 items-center justify-center text-secondary border border-outline-variant/10 hidden md:flex">
            <span class="material-symbols-outlined text-base animate-pulse" data-icon="auto_stories">auto_stories</span>
        </div>
        <div class="bg-surface-container-low border border-dashed border-outline-variant/20 rounded-3xl p-6 md:p-8">
            <div class="flex gap-2">
                <div class="w-2 h-2 rounded-full bg-primary/40 animate-bounce [animation-delay:-0.3s]"></div>
                <div class="w-2 h-2 rounded-full bg-primary/40 animate-bounce [animation-delay:-0.15s]"></div>
                <div class="w-2 h-2 rounded-full bg-primary/40 animate-bounce"></div>
            </div>
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

async function handleExport() {
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
}

if (btnExport) btnExport.addEventListener('click', handleExport);
if (btnExportSidebar) btnExportSidebar.addEventListener('click', handleExport);

// ── New Session ─────────────────────────────────────────

btnNewSession.addEventListener('click', () => {
    sessionId = null;
    chatArea.innerHTML = '';
    renderWelcome();
    if (window.innerWidth < 768) {
        toggleMenu(); // close mobile menu when choosing new session
    }
});

// ── Input Handling ──────────────────────────────────────

function autoResize() {
    userInput.style.height = 'auto';
    userInput.style.height = Math.min(userInput.scrollHeight, 120) + 'px';
}

userInput.addEventListener('input', () => {
    autoResize();
    btnSend.disabled = userInput.value.trim().length === 0;
});

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
        if (chatScroller) {
            chatScroller.scrollTo({
                top: chatScroller.scrollHeight,
                behavior: 'smooth'
            });    
        } else {
            window.scrollTo({
                top: document.body.scrollHeight,
                behavior: 'smooth'
            });
        }
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
