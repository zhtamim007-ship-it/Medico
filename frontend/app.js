// AI YouTube Transcriber — frontend logic
// Pure vanilla JS. Talks to /api/* on the same origin.

const $ = (sel) => document.querySelector(sel);

const state = {
  video: null,         // {id, title, duration, channel, thumbnail, url}
  jobId: null,         // current job id
  transcript: null,    // last transcript payload
  audioUrl: null,      // /api/audio/<job>
  showTs: true,
  offline: false,      // true when the static preview is loaded without a backend
};

// ---------- helpers ----------

function fmtTime(secs) {
  secs = Math.max(0, Math.floor(secs || 0));
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

function toast(msg, kind = "") {
  const t = $("#toast");
  t.textContent = msg;
  t.className = `toast ${kind}`;
  t.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add("hidden"), 4500);
}

function setBusy(btn, busy, labelWhenBusy = "Working…") {
  if (!btn) return;
  const label = btn.querySelector(".btn-label");
  const sp = btn.querySelector(".btn-spinner");
  if (busy) {
    btn.dataset._label = label?.textContent || "";
    if (label) label.textContent = labelWhenBusy;
    if (sp) sp.classList.remove("hidden");
    btn.disabled = true;
  } else {
    if (label && btn.dataset._label) label.textContent = btn.dataset._label;
    if (sp) sp.classList.add("hidden");
    btn.disabled = false;
  }
}

function show(id) { $(`#${id}`).classList.remove("hidden"); }
function hide(id) { $(`#${id}`).classList.add("hidden"); }

// ---------- step 1: fetch video info ----------

$("#url-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = $("#url-input").value.trim();
  if (!url) return;

  // Static preview mode: no backend, can't actually fetch. Be loud about it.
  if (state.offline) {
    toast(
      "This is a static preview only — there's no backend at this URL. " +
        "Run ./start.sh locally (see the yellow banner above) to use the real app.",
      "error"
    );
    return;
  }

  const btn = $("#fetch-btn");
  setBusy(btn, true, "Fetching…");

  try {
    const r = await fetch("/api/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || "Failed to fetch video info");
    }
    const info = await r.json();
    state.video = info;
    renderInfo();
  } catch (err) {
    toast(err.message || String(err), "error");
  } finally {
    setBusy(btn, false);
  }
});

function renderInfo() {
  const v = state.video;
  if (!v) return;

  $("#info-thumbnail").src = v.thumbnail;
  $("#info-thumbnail").alt = v.title;
  $("#info-title").textContent = v.title;
  $("#info-channel").textContent = v.channel;
  $("#info-duration").textContent = fmtTime(v.duration);

  // Configure the dual range slider
  const startEl = $("#range-start");
  const endEl = $("#range-end");
  startEl.max = String(v.duration);
  endEl.max = String(v.duration);
  startEl.value = "0";
  endEl.value = String(v.duration);

  show("step-info");
  hide("step-result");
  updateRange();
  // smooth scroll
  setTimeout(() => $("#step-info").scrollIntoView({ behavior: "smooth", block: "start" }), 50);
}

// ---------- step 2: dual range slider ----------

function updateRange() {
  const startEl = $("#range-start");
  const endEl = $("#range-end");
  const total = Number(state.video?.duration || 0);
  let s = Number(startEl.value);
  let e = Number(endEl.value);
  if (s > e - 1 && e > 0) {  // keep at least 1s gap
    if (this === startEl) s = e - 1;
    else e = s + 1;
  }
  startEl.value = String(s);
  endEl.value = String(e);

  const pct1 = total ? (s / total) * 100 : 0;
  const pct2 = total ? (e / total) * 100 : 0;
  $("#track-fill").style.left = `${pct1}%`;
  $("#track-fill").style.width = `${Math.max(0, pct2 - pct1)}%`;

  $("#range-from").textContent = fmtTime(s);
  $("#range-to").textContent = fmtTime(e);
  const len = Math.max(0, e - s);
  $("#range-total").textContent = `(${fmtTime(len)} selected)`;
}

$("#range-start").addEventListener("input", updateRange);
$("#range-end").addEventListener("input", updateRange);

// Preset buttons
document.querySelectorAll(".range-presets button").forEach((b) => {
  b.addEventListener("click", () => {
    const dur = Number(state.video?.duration || 0);
    const k = b.dataset.preset;
    let s = 0, e = dur;
    if (k === "first60") e = Math.min(60, dur);
    else if (k === "last60") s = Math.max(0, dur - 60);
    else if (k === "first300") e = Math.min(300, dur);
    $("#range-start").value = String(s);
    $("#range-end").value = String(e);
    updateRange();
  });
});

// ---------- step 2 → 3: transcribe ----------

$("#transcribe-btn").addEventListener("click", async () => {
  if (!state.video) return;
  const s = Number($("#range-start").value);
  const e = Number($("#range-end").value);
  if (e <= s) { toast("End time must be after start time.", "error"); return; }

  const btn = $("#transcribe-btn");
  setBusy(btn, true, "Transcribing…");
  toast("Working on it — this can take a moment for long clips.", "");

  try {
    const r = await fetch("/api/transcribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: state.video.url,
        start: s,
        end: e,
        language: $("#lang-hint").value || null,
        prompt: $("#ctx-prompt").value.trim() || null,
      }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || "Transcription failed");
    }
    const data = await r.json();
    state.jobId = data.job_id;
    state.transcript = data;
    state.audioUrl = data.clip_url;
    renderResult();
  } catch (err) {
    toast(err.message || String(err), "error");
  } finally {
    setBusy(btn, false);
  }
});

// ---------- step 3: render result ----------

function renderResult() {
  const t = state.transcript;
  if (!t) return;

  // Meta pills
  const langName = (t.language || "auto").toUpperCase();
  $("#meta-lang").textContent = `lang: ${langName}` +
    (t.language_probability ? ` (${(t.language_probability * 100).toFixed(0)}%)` : "");
  $("#meta-elapsed").textContent = `took ${t.elapsed_sec ?? "?"}s · ${fmtTime(t.duration)}`;
  $("#meta-range").textContent = `range: ${fmtTime(t.start)} → ${fmtTime(t.end)}`;

  // Top badge
  const lb = $("#lang-badge");
  lb.textContent = langName;
  lb.classList.remove("hidden");

  // Audio overview
  const audio = $("#audio-player");
  audio.src = state.audioUrl;

  // Transcript
  drawTranscript();

  show("step-result");
  setTimeout(() => $("#step-result").scrollIntoView({ behavior: "smooth", block: "start" }), 50);
}

function drawTranscript() {
  const t = state.transcript;
  const wrap = $("#transcript");
  wrap.innerHTML = "";
  const segs = t.segments || [];
  $("#seg-count").textContent = `${segs.length} segment${segs.length === 1 ? "" : "s"}`;

  const tsVisible = state.showTs;
  for (const seg of segs) {
    const row = document.createElement("div");
    row.className = "seg";

    if (tsVisible) {
      const ts = document.createElement("span");
      ts.className = "ts";
      ts.textContent = fmtTime(seg.start);
      ts.title = "Jump audio here";
      ts.addEventListener("click", () => {
        const a = $("#audio-player");
        if (a.src) { a.currentTime = seg.start; a.play().catch(() => {}); }
      });
      row.appendChild(ts);
    }

    const txt = document.createElement("span");
    txt.className = "txt";
    txt.textContent = seg.text;
    row.appendChild(txt);

    wrap.appendChild(row);
  }
}

$("#show-ts").addEventListener("change", (e) => {
  state.showTs = e.target.checked;
  drawTranscript();
});

// ---------- refine / copy / download ----------

$("#refine-btn").addEventListener("click", async () => {
  if (!state.transcript) return;
  const btn = $("#refine-btn");
  setBusy(btn, true, "Refining…");
  toast("Refining transcript — AI is cleaning up misheard words, but keeping the meaning intact.", "");

  // Demo mode: simulate refine
  if (state.transcript.job_id === "demo") {
    await new Promise((r) => setTimeout(r, 1200));
    state.transcript.segments = state.transcript.segments.map((s, i) => ({
      ...s,
      text: i === 2
        ? "The long answer is, well, the model was trained on around 680,000 hours of multilingual audio — much of it dirty, real-world, in-the-wild material."
        : s.text,
    }));
    state.transcript.text = state.transcript.segments.map((s) => s.text).join(" ");
    drawTranscript();
    toast("Refined — meaning preserved, wording cleaned up.", "success");
    setBusy(btn, false, "✦ Refine with AI");
    return;
  }

  try {
    const r = await fetch("/api/refine", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: "segments",
        segments: state.transcript.segments,
        language: state.transcript.language,
      }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }));
      throw new Error(err.detail || "Refinement failed");
    }
    const data = await r.json();
    state.transcript.segments = data.segments;
    state.transcript.text = data.segments.map((s) => s.text).join(" ");
    drawTranscript();
    toast("Refined — meaning preserved, wording cleaned up.", "success");
  } catch (err) {
    toast(err.message || String(err), "error");
  } finally {
    setBusy(btn, false, "✦ Refine with AI");
  }
});

$("#copy-btn").addEventListener("click", async () => {
  if (!state.transcript) return;
  const text = (state.transcript.segments || [])
    .map((s) => `${fmtTime(s.start)}  ${s.text}`)
    .join("\n");
  try {
    await navigator.clipboard.writeText(text);
    toast("Copied to clipboard.", "success");
  } catch {
    toast("Couldn't copy — your browser may block clipboard access.", "error");
  }
});

function downloadBlob(filename, content, mime = "text/plain;charset=utf-8") {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 0);
}

$("#download-txt-btn").addEventListener("click", () => {
  if (!state.transcript) return;
  const text = (state.transcript.segments || [])
    .map((s) => s.text)
    .join("\n");
  const safe = (state.video?.title || "transcript").replace(/[^\w\- ]+/g, "").slice(0, 60);
  downloadBlob(`${safe}.txt`, text);
});

$("#download-srt-btn").addEventListener("click", () => {
  if (!state.transcript) return;
  const fmtSrt = (secs) => {
    secs = Math.max(0, secs);
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = Math.floor(secs % 60);
    const ms = Math.floor((secs - Math.floor(secs)) * 1000);
    const pad = (n, w = 2) => String(n).padStart(w, "0");
    return `${pad(h)}:${pad(m)}:${pad(s)},${pad(ms, 3)}`;
  };
  const blocks = (state.transcript.segments || []).map((seg, i) =>
    `${i + 1}\n${fmtSrt(seg.start)} --> ${fmtSrt(seg.end)}\n${seg.text}\n`
  ).join("\n");
  const safe = (state.video?.title || "transcript").replace(/[^\w\- ]+/g, "").slice(0, 60);
  downloadBlob(`${safe}.srt`, blocks);
});

// ---------- boot ----------

(async function () {
  let backendOk = false;
  try {
    const r = await fetch("/api/health");
    if (r.ok) {
      backendOk = true;
      const h = await r.json();
      if (!h.openai_key_set) {
        toast("Heads up: OPENAI_API_KEY is not set on the server. Add it to backend/.env and restart.", "error");
      }
    }
  } catch { /* ignore */ }

  if (!backendOk) {
    // Static preview mode — show the banner and let the user play with the UI.
    state.offline = true;
    document.getElementById("offline-banner").classList.remove("hidden");
    const urlInput = document.getElementById("url-input");
    if (urlInput) urlInput.disabled = true;
    const fetchBtn = document.getElementById("fetch-btn");
    if (fetchBtn) fetchBtn.disabled = true;
  }
})();

// ---------- demo data (for the static preview) ----------

const DEMO_TRANSCRIPT = {
  job_id: "demo",
  clip_url: "",
  transcript_url: "",
  elapsed_sec: 4.7,
  language: "en",
  language_probability: 0.98,
  duration: 18.0,
  text: "Hey everyone — welcome back. Today we're going to look at how Whisper handles really noisy audio, and the short answer is, it handles it shockingly well. The long answer is, well, the model was trained on something like 680 thousand hours of multilingual audio, a lot of which is dirty, real-world, in-the-wild stuff. So when you throw a low-quality YouTube rip at it, it just… deals with it. We're also going to look at how to cut a precise segment with ffmpeg, and how the refine button can clean up misheard words without changing what the speaker actually said.",
  start: 0,
  end: 18,
  segments: [
    { start: 0.0, end: 2.8, text: "Hey everyone — welcome back." },
    { start: 2.8, end: 6.4, text: "Today we're going to look at how Whisper handles really noisy audio, and the short answer is, it handles it shockingly well." },
    { start: 6.4, end: 11.9, text: "The long answer is, well, the model was trained on something like 680 thousand hours of multilingual audio, a lot of which is dirty, real-world, in-the-wild stuff." },
    { start: 11.9, end: 15.2, text: "So when you throw a low-quality YouTube rip at it, it just… deals with it." },
    { start: 15.2, end: 18.0, text: "We're also going to look at how to cut a precise segment with ffmpeg, and how the refine button can clean up misheard words without changing what the speaker actually said." },
  ],
};

const DEMO_VIDEO = {
  id: "demo",
  title: "How Whisper handles noisy audio (demo)",
  duration: 18,
  channel: "Demo",
  thumbnail: "",
  url: "https://www.youtube.com/watch?v=demo",
};

document.getElementById("load-demo-btn").addEventListener("click", () => {
  state.video = DEMO_VIDEO;
  renderInfo();
  state.transcript = { ...DEMO_TRANSCRIPT };
  // No audio file in demo mode, but the UI still renders.
  state.audioUrl = null;
  renderResult();
  const audio = document.getElementById("audio-player");
  audio.removeAttribute("src");
  audio.load();
  toast("Demo data loaded — explore the UI. The audio player is disabled in static preview.", "");
});
