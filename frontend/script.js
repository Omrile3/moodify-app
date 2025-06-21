const backendUrl = "https://moodify-app-mcic.onrender.com"; // Change if your backend URL differs!
const chatEl = document.getElementById("chat");
const inputForm = document.getElementById("inputForm");
const userInput = document.getElementById("userInput");
const sendBtn = document.getElementById("sendBtn");
const resetBtn = document.getElementById("resetBtn");
const loadingEl = document.getElementById("loading");

function generateSessionId() {
  return (
    localStorage.getItem("moodify_session_id") ||
    (() => {
      const id = Math.random().toString(36).slice(2) + Date.now().toString(36);
      localStorage.setItem("moodify_session_id", id);
      return id;
    })()
  );
}
const sessionId = generateSessionId();

function appendMsg(text, sender = "bot") {
  const msg = document.createElement("div");
  msg.className = `msg ${sender}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = text.replace(/\n/g, "<br>");
  msg.appendChild(bubble);
  chatEl.appendChild(msg);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function setLoading(isLoading) {
  loadingEl.style.display = isLoading ? "block" : "none";
  sendBtn.disabled = isLoading;
  userInput.disabled = isLoading;
}

inputForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = userInput.value.trim();
  if (!text) return;
  appendMsg(text, "user");
  userInput.value = "";
  setLoading(true);
  try {
    const resp = await fetch(`${backendUrl}/command`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message: text })
    });
    const data = await resp.json();
    appendMsg(data.response, "bot");
  } catch (err) {
    appendMsg("⚠️ There was a problem connecting to Moodify. Please try again.", "bot");
  }
  setLoading(false);
});

resetBtn.addEventListener("click", async () => {
  setLoading(true);
  try {
    const resp = await fetch(`${backendUrl}/reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId })
    });
    const data = await resp.json();
    appendMsg("<span style='color:#4f46e5;font-weight:bold;'>[Preferences reset]</span> " + data.response, "bot");
  } catch (err) {
    appendMsg("⚠️ Could not reset preferences.", "bot");
  }
  setLoading(false);
});

// Animated dots for "Thinking..."
let dots = 0;
setInterval(() => {
  if (!loadingEl) return;
  dots = (dots + 1) % 4;
  loadingEl.querySelector(".dots").textContent = ".".repeat(dots);
}, 500);

// Initial bot message
window.addEventListener("DOMContentLoaded", () => {
  appendMsg("Hey there! 👋 I'm Moodify, your smart music assistant. Let's find your perfect song!<br>What genre are you in the mood for?");
});
