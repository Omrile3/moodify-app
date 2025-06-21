const backendUrl = "https://moodify-backend-uj8d.onrender.com";
const sessionId = generateSessionId();

window.handleBotReply = function (msg) {
  appendUserMessage(msg, true);
  showTypingIndicator();

  fetch(`${backendUrl}/command`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, command: msg })
  })
    .then(res => res.json())
    .then(data => {
      const resp = data.response || "<span style='color:orange'>Sorry, I didn't get that. Try a different preference or reset.</span>";
      const delay = calculateTypingDelay(resp);
      setTimeout(() => {
        hideTypingIndicator();
        appendBotMessage(resp);
        updatePreferencesPanel();
      }, delay);
    })
    .catch(error => {
      console.error("API error:", error);
      hideTypingIndicator();
      appendBotMessage("<span style='color:red'>⚠️ Sorry, I lost connection to Moodify. Please check your internet or try again.</span>");
      updatePreferencesPanel();
    });
};

window.sendMessage = function () {
  const inputField = document.getElementById("user-input");
  const message = inputField.value.trim();
  if (!message) return;

  appendUserMessage(message);
  inputField.value = "";

  const preferences = {
    session_id: sessionId,
    artist_or_song: message
  };

  showTypingIndicator();

  fetch(`${backendUrl}/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(preferences)
  })
    .then(res => res.json())
    .then(data => {
      const resp = data.response || "<span style='color:orange'>I didn't understand. Tell me your mood, genre, or artist!</span>";
      const delay = calculateTypingDelay(resp);
      setTimeout(() => {
        hideTypingIndicator();
        appendBotMessage(resp);
        updatePreferencesPanel();
      }, delay);
    })
    .catch(error => {
      console.error("API error:", error);
      hideTypingIndicator();
      appendBotMessage("<span style='color:red'>⚠️ Sorry, I lost connection to Moodify. Please check your internet or try again.</span>");
      updatePreferencesPanel();
    });
};

window.onload = () => {
  document.getElementById("chat-box").innerHTML = "";
  fetch(`${backendUrl}/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, artist_or_song: "hi" })
  })
    .then(res => res.json())
    .then(data => {
      appendBotMessage(data.response || "Welcome! Tell me your mood, artist, or genre.");
      updatePreferencesPanel();
    })
    .catch(error => {
      console.error("API error:", error);
      appendBotMessage("<span style='color:red'>⚠️ Sorry, I lost connection to Moodify.</span>");
      updatePreferencesPanel();
    });
};

function generateSessionId() {
  // Use window.crypto for true uniqueness, fallback to random
  if (window.crypto && window.crypto.getRandomValues) {
    return 'sess-' + Array.from(window.crypto.getRandomValues(new Uint8Array(8))).map(b => b.toString(16).padStart(2, '0')).join('');
  }
  return 'sess-' + Math.random().toString(36).substring(2, 10);
}

document.getElementById("user-input").addEventListener("keypress", function (event) {
  if (event.key === "Enter") {
    event.preventDefault();
    sendMessage();
  }
});

function appendUserMessage(msg, isButton) {
  const chatBox = document.getElementById("chat-box");
  if (isButton) {
    chatBox.innerHTML += `<p><strong>You:</strong> <span class="user-btn-msg">${msg}</span></p>`;
  } else {
    chatBox.innerHTML += `<p><strong>You:</strong> ${msg}</p>`;
  }
  chatBox.scrollTop = chatBox.scrollHeight;
}

function appendBotMessage(msgOrObj) {
  const chatBox = document.getElementById("chat-box");
  let msg = msgOrObj;
  let spotifyUrl = null;

  if (typeof msgOrObj === "object" && msgOrObj !== null) {
    msg = msgOrObj.response || msgOrObj.text || "";
    if (msgOrObj.spotify_url) spotifyUrl = msgOrObj.spotify_url;
  } else {
    const spotifyMatch = msg && msg.match(/https:\/\/open\.spotify\.com\/track\/([a-zA-Z0-9]{22})/);
    if (spotifyMatch) {
      spotifyUrl = `https://open.spotify.com/track/${spotifyMatch[1]}`;
    }
  }

  // Remove any invalid/empty Spotify URLs
  if (
    spotifyUrl &&
    (
      !/track\/[a-zA-Z0-9]{22}$/.test(spotifyUrl) ||
      spotifyUrl.endsWith('/track/none') ||
      spotifyUrl.endsWith('/track/')
    )
  ) {
    spotifyUrl = null;
  }

  // Remove any 'Listen on Spotify' hyperlink if embedding
  let cleanMsg = msg.replace(/<a [^>]+>(Listen on Spotify)?<\/a>/ig, '').replace(/https:\/\/open\.spotify\.com\/track\/[a-zA-Z0-9]+/g, '');

  let html = `<p class="green-response"><strong>Moodify:</strong> ${cleanMsg}</p>`;

  // Only embed if valid track id
  if (spotifyUrl) {
    const idMatch = spotifyUrl.match(/track\/([a-zA-Z0-9]{22})/);
    if (idMatch && idMatch[1] && idMatch[1].toLowerCase() !== "none") {
      html += `
        <div class="spotify-embed">
          <iframe style="border-radius:12px;margin-top:4px;" src="https://open.spotify.com/embed/track/${idMatch[1]}" width="100%" height="80" frameborder="0" allow="autoplay; clipboard-write; encrypted-media; picture-in-picture" allowfullscreen></iframe>
        </div>
      `;
    }
  }

  chatBox.innerHTML += html;
  chatBox.scrollTop = chatBox.scrollHeight;

  setTimeout(activateAllBackendButtons, 0);
}

function activateAllBackendButtons() {
  const buttons = document.querySelectorAll('button[onclick^="window.handleBotReply"]');
  buttons.forEach(btn => {
    if (!btn.dataset.patched) {
      const cmdMatch = btn.getAttribute('onclick').match(/window\.handleBotReply\(['"](.+?)['"]\)/);
      if (cmdMatch) {
        btn.onclick = function () { window.handleBotReply(cmdMatch[1]); };
        btn.dataset.patched = "true";
      }
    }
  });
}

function showTypingIndicator() {
  const chatBox = document.getElementById("chat-box");
  const typing = document.createElement("p");
  typing.id = "typing-indicator";
  typing.innerHTML = `<em>Moodify is typing...</em>`;
  chatBox.appendChild(typing);
  chatBox.scrollTop = chatBox.scrollHeight;
}

function hideTypingIndicator() {
  const typing = document.getElementById("typing-indicator");
  if (typing) typing.remove();
}

function calculateTypingDelay(text) {
  if (!text) return 500;
  const wordCount = text.replace(/<[^>]+>/g, '').split(" ").length;
  const delayPerWord = 90; // a bit faster for UX
  return Math.min(2200, wordCount * delayPerWord + 350);
}

window.resetSession = function () {
  showTypingIndicator();
  fetch(`${backendUrl}/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId })
  })
    .then(res => res.json())
    .then(data => {
      window.location.reload();
    })
    .catch(error => {
      hideTypingIndicator();
      appendBotMessage("<span style='color:red'>⚠️ Sorry, something went wrong while resetting your session.</span>");
      console.error("Reset error:", error);
      document.getElementById("pref-genre").innerText = '—';
      document.getElementById("pref-mood").innerText = '—';
      document.getElementById("pref-tempo").innerText = '—';
      document.getElementById("pref-artist").innerText = '—';
      document.getElementById("user-input").value = "";
      updateProgressBar(0);
    });
};

function updatePreferencesPanel() {
  fetch(`${backendUrl}/session/${sessionId}`)
    .then(res => res.json())
    .then(data => {
      const genre = data.genre ? capitalize(data.genre) : (data.no_pref_genre ? '—' : '—');
      const mood = data.mood ? capitalize(data.mood) : (data.no_pref_mood ? '—' : '—');
      const tempo = data.tempo ? capitalize(data.tempo) : (data.no_pref_tempo ? '—' : '—');
      const artist = data.artist_or_song ? capitalize(data.artist_or_song) : (data.no_pref_artist_or_song ? '—' : '—');

      document.getElementById("pref-genre").innerText = genre;
      document.getElementById("pref-mood").innerText = mood;
      document.getElementById("pref-tempo").innerText = tempo;
      document.getElementById("pref-artist").innerText = artist;

      let filled = 0;
      if (data.genre || data.no_pref_genre) filled += 1;
      if (data.mood || data.no_pref_mood) filled += 1;
      if (data.tempo || data.no_pref_tempo) filled += 1;
      if (data.artist_or_song || data.no_pref_artist_or_song) filled += 1;

      updateProgressBar(filled);
    })
    .catch(() => {
      document.getElementById("pref-genre").innerText = '—';
      document.getElementById("pref-mood").innerText = '—';
      document.getElementById("pref-tempo").innerText = '—';
      document.getElementById("pref-artist").innerText = '—';
      updateProgressBar(0);
    });
}

function updateProgressBar(filled) {
  const percent = (filled / 4) * 100;
  const fillEl = document.getElementById("progress-bar-fill");
  const labelEl = document.getElementById("progress-label");
  fillEl.style.width = percent + "%";
  labelEl.textContent = `Preferences: ${filled}/4 filled`;
}

function capitalize(s) {
  if (typeof s !== "string") return s;
  return s.length > 0 ? s[0].toUpperCase() + s.slice(1) : s;
}
