const startScreen = document.getElementById("start-screen");
const appShell = document.getElementById("app-shell");
const tabNew = document.getElementById("tab-new");
const tabContinue = document.getElementById("tab-continue");
const titleForm = document.getElementById("title-form");
const titleInput = document.getElementById("title-input");
const continuePanel = document.getElementById("continue-panel");
const historyList = document.getElementById("history-list");
const backLink = document.getElementById("back-link");
const sessionTitle = document.getElementById("session-title");
const chat = document.getElementById("chat");
const ideaForm = document.getElementById("idea-form");
const ideaInput = document.getElementById("idea-input");
const sakuraLayer = document.getElementById("sakura-layer");

const idleMs = (window.APP_CONFIG?.idleSeconds || 20) * 1000;
let currentTitle = "";
let currentSessionId = "";
let lastActivityAt = Date.now();
let suggestInFlight = false;
let isComposing = false;

function addMessage(kind, text) {
  const el = document.createElement("article");
  el.className = `msg ${kind}`;
  el.textContent = text;
  chat.appendChild(el);
  chat.scrollTop = chat.scrollHeight;
}

function touchActivity() {
  lastActivityAt = Date.now();
}

function scatterNatureBurst() {
  const count = 30;
  for (let i = 0; i < count; i += 1) {
    const chip = document.createElement("span");
    const isLeaf = Math.random() < 0.45;
    chip.className = isLeaf ? "leaf" : "petal";
    chip.style.left = `${Math.random() * 100}vw`;
    chip.style.animationDuration = `${4 + Math.random() * 4}s`;
    chip.style.animationDelay = `${Math.random() * 0.45}s`;
    chip.style.transform = `rotate(${Math.random() * 360}deg)`;
    sakuraLayer.appendChild(chip);
    setTimeout(() => chip.remove(), 8600);
  }
}

function clearChat() {
  chat.innerHTML = "";
}

function switchStartMode(mode) {
  const isNew = mode === "new";
  tabNew.classList.toggle("active", isNew);
  tabContinue.classList.toggle("active", !isNew);
  tabNew.setAttribute("aria-selected", String(isNew));
  tabContinue.setAttribute("aria-selected", String(!isNew));
  titleForm.classList.toggle("hidden", !isNew);
  continuePanel.classList.toggle("hidden", isNew);
}

function enterBrainstorm(title, sessionId) {
  currentTitle = title;
  currentSessionId = sessionId;
  sessionTitle.textContent = `タイトル: ${currentTitle}`;
  startScreen.classList.add("hidden");
  appShell.classList.remove("hidden");
  touchActivity();
  ideaInput.focus();
}

function returnToStartScreen() {
  currentTitle = "";
  currentSessionId = "";
  clearChat();
  appShell.classList.add("hidden");
  startScreen.classList.remove("hidden");
  switchStartMode("new");
}

function renderHistoryList(sessions) {
  historyList.innerHTML = "";
  if (!sessions.length) {
    const empty = document.createElement("p");
    empty.className = "history-empty";
    empty.textContent = "保存済みの履歴はまだありません。";
    historyList.appendChild(empty);
    return;
  }

  sessions.forEach((s) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "history-item";
    button.innerHTML = `<span>${s.title}</span><small>${s.updated_at}</small>`;
    button.addEventListener("click", async () => {
      try {
        const data = await postJSON("/continue", { session_id: s.session_id });
        clearChat();
        enterBrainstorm(data.title, data.session_id);
        data.messages.forEach((m) => addMessage(m.kind, m.text));
      } catch (err) {
        alert(err.message);
      }
    });
    historyList.appendChild(button);
  });
}

async function loadSessions() {
  const res = await fetch("/sessions");
  if (!res.ok) {
    throw new Error("履歴一覧の取得に失敗しました");
  }
  const data = await res.json();
  renderHistoryList(data.sessions || []);
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "通信に失敗しました" }));
    throw new Error(err.detail || "エラーが発生しました");
  }
  return res.json();
}

async function sendIdea() {
  const text = ideaInput.value.trim();
  if (!text || !currentSessionId) {
    return;
  }

  ideaInput.value = "";
  touchActivity();
  addMessage("user", `あなた: ${text}`);

  try {
    const data = await postJSON("/idea", { session_id: currentSessionId, idea: text });
    addMessage("ai", `AI: ${data.message}`);
    if (data.sakura) {
      scatterNatureBurst();
    }
  } catch (err) {
    addMessage("suggest", `SYSTEM: ${err.message}`);
  } finally {
    ideaInput.focus();
  }
}

async function maybeSuggest() {
  if (!currentSessionId || suggestInFlight) {
    return;
  }
  const idleFor = Date.now() - lastActivityAt;
  if (idleFor < idleMs) {
    return;
  }

  suggestInFlight = true;
  try {
    const data = await postJSON("/suggest", { session_id: currentSessionId });
    addMessage("suggest", `AIの提案: ${data.message}`);
    touchActivity();
  } catch (err) {
    addMessage("suggest", `SYSTEM: ${err.message}`);
    touchActivity();
  } finally {
    suggestInFlight = false;
  }
}

titleForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const title = titleInput.value.trim();
  if (!title) {
    return;
  }

  try {
    const data = await postJSON("/start", { title });
    clearChat();
    enterBrainstorm(data.title, data.session_id);
    addMessage("ai", "AI: 準備OKです。どんどんアイデアを投げてください！");
  } catch (err) {
    alert(err.message);
  }
});

if (tabNew) {
  tabNew.addEventListener("click", () => {
    switchStartMode("new");
  });
}

if (tabContinue) {
  tabContinue.addEventListener("click", async () => {
    switchStartMode("continue");
    try {
      await loadSessions();
    } catch (err) {
      historyList.innerHTML = `<p class="history-empty">${err.message}</p>`;
    }
  });
}

// フォールバック: 何らかの理由で個別リスナーが効かない場合でも切り替えを拾う
document.querySelector(".mode-tabs")?.addEventListener("click", async (event) => {
  const target = event.target.closest("button");
  if (!target) {
    return;
  }
  if (target.id === "tab-new") {
    switchStartMode("new");
    return;
  }
  if (target.id === "tab-continue") {
    switchStartMode("continue");
    try {
      await loadSessions();
    } catch (err) {
      historyList.innerHTML = `<p class="history-empty">${err.message}</p>`;
    }
  }
});

backLink.addEventListener("click", async (event) => {
  event.preventDefault();
  returnToStartScreen();
  try {
    await loadSessions();
  } catch {
    // 戻る操作自体は失敗させない
  }
});

ideaForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await sendIdea();
});

ideaInput.addEventListener("input", touchActivity);
ideaInput.addEventListener("compositionstart", () => {
  isComposing = true;
});
ideaInput.addEventListener("compositionend", () => {
  isComposing = false;
  touchActivity();
});
ideaInput.addEventListener("keydown", async (event) => {
  // 日本語IME変換中のEnter(確定キー)では送信しない
  if (isComposing || event.isComposing || event.keyCode === 229) {
    return;
  }

  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    await sendIdea();
  }
});

setInterval(maybeSuggest, 1000);
