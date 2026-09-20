import Fuse from "fuse.js";

import { LANGS, pickLang } from "./i18n.js";
import {
  flagOf,
  isHlsStream,
  isInsecure,
  playableUrl,
  safeWebsite,
  stationKey,
} from "./utils.js";

/**
 * İki liste, aynı şema (bkz. data/README.md).
 *
 * Ayrı tutulmalarının sebebi: elle seçilmiş 35 istasyon 3.400'ün içinde
 * kaybolur. Kuratörlü liste açılışta yüklenir, dizin yalnız istenirse çekilir.
 */
// Adresler denenme sırasıyla: Pages dağıtımı data/'yı sitenin yanına koyuyor
// (web.yml `public/` ağacı), o yüzden önce aynı kökenli göreli yol — ağ
// koşulundan bağımsız, her zaman siteyle aynı yaşta. Bileşen başka bir sayfaya
// gömülüyse 404 olur ve mutlak adreslere düşülür: özel alan adı DNS
// taşımalarında kesintiye düşebiliyor; GitHub Pages adresi her koşulda çalışır
// (özel alan adı bağlanınca GitHub oraya yönlendirir).
const DATA_HOSTS = [
  "./data",
  "https://radyola.aripd.com/data",
  "https://aripdcom.github.io/radyola/data",
];

const SOURCES = {
  curated: {
    urls: DATA_HOSTS.map((h) => `${h}/stations.json`),
    label: "Curated",
  },
  directory: {
    urls: DATA_HOSTS.map((h) => `${h}/directory.json`),
    label: "Discover",
  },
  // Ağdan gelmez: kayıtlar tam hâliyle localStorage'da (bkz. _persistFavorites).
  favorites: {
    urls: [],
    label: "Favorites",
  },
};

/** Favori istasyonların localStorage anahtarı. */
const FAVORITES_KEY = "radyola.favorites.v1";

/** Ses düzeyinin localStorage anahtarı. */
const VOLUME_KEY = "radyola.volume.v1";

/** Dizinde ilk anda basılan satır sayısı; gerisi kaydırdıkça eklenir. */
const PAGE_SIZE = 60;

/** Tür şeridinde gösterilecek en fazla tür — dizinde 438 tür var. */
const MAX_GENRE_PILLS = 24;

/** Arama, tuş vuruşu başına değil bu gecikmeyle çalışır (ms). */
const SEARCH_DEBOUNCE = 150;

/* ── helpers ─────────────────────────────────────────────── */
function el(tag, cls, attrs) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (attrs) Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v));
  return e;
}

/* Saf yardımcılar utils.js'te, dil tablosu i18n.js'te — birim testleri
   onları hedefliyor (web/test/). */

/* localStorage gizli pencerede ya da veri engelli tarayıcıda fırlatabilir;
   kalıcılık bir kolaylık, yokluğu uygulamayı düşürmemeli. */
function storeRead(key) {
  try {
    return JSON.parse(localStorage.getItem(key));
  } catch {
    return null;
  }
}

function storeWrite(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* yok say */
  }
}

/* ── font ─────────────────────────────────────────────────── */
/**
 * Inter'i belge düzeyinde kaydeder. Gölge DOM stil dosyasına @font-face
 * yazmak yetmiyor: Chromium ve Firefox gölge stilindeki font tanımını belge
 * yazı kümesine işlemiyor, metin sessizce sistem yazısına düşüyor (Google
 * Fonts @import'lu eski kurulumda da böyleydi). FontFace API belge kümesine
 * doğrudan ekler; gömen sayfalar da ek iş yapmadan kazanır.
 *
 * Yol, CSS gibi belgeye göre çözülür — fonts/ dizini radyola-player.css'in
 * yanında taşınmalı (bkz. README).
 */
const FONT_URL = "./fonts/InterVariable.woff2";
function ensureInterFont() {
  try {
    const registered = [...document.fonts].some(
      (f) => f.family.replace(/["']/g, "") === "Inter"
    );
    if (registered) return;
    const face = new FontFace("Inter", `url(${FONT_URL}) format("woff2")`, {
      weight: "100 900",
      display: "swap",
    });
    document.fonts.add(face);
    face.load().catch(() => { /* yüklenemezse system-ui yedeği iş görür */ });
  } catch {
    /* FontFace API yoksa da uygulama yazısız kalmaz */
  }
}

/* ── CSS (loaded from external file into shadow DOM) ────── */
const CSS_PATH = "./radyola-player.css";

function createStyleLink() {
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = CSS_PATH;
  return link;
}

/* ── SVG icons ─────────────────────────── */
const SVG = {
  play: `<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>`,
  pause: `<svg viewBox="0 0 24 24"><path d="M6 4h4v16H6zm8 0h4v16h-4z"/></svg>`,
  search: `<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
  radio: `<svg viewBox="0 0 384 512"><path d="M73 39c-14.8-9.1-33.4-9.4-48.5-.9S0 62.6 0 80v352c0 17.4 9.4 33.4 24.5 41.9s33.7 8.1 48.5-.9L361 297c14.3-8.7 23-24.2 23-41s-8.7-32.2-23-41L73 39z"/></svg>`,
  extLink: `<svg viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`,
  vol: `<svg viewBox="0 0 24 24"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07" fill="none" stroke="currentColor" stroke-width="2"/></svg>`,
  prev: `<svg viewBox="0 0 24 24"><path d="M19 20L9 12l10-8v16zM5 4v16"/></svg>`,
  next: `<svg viewBox="0 0 24 24"><path d="M5 4l10 8-10 8V4zM19 4v16"/></svg>`,
  heart: `<svg viewBox="0 0 24 24"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>`,
  share: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="10.49" x2="15.42" y2="6.51"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/></svg>`,
  close: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
};

/* ══════════════════════════════════════════════════════════ */
/*  Web Component                                            */
/* ══════════════════════════════════════════════════════════ */
class AripdRadyola extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._source = "curated";
    this._lists = {};        // kaynak → istasyonlar (bir kez çekilir, bellekte kalır)
    this._fuse = null;       // arama indeksi; liste başına bir kez kurulur
    this._stations = [];
    this._filtered = [];
    this._rendered = 0;      // dizinde satırlar kaydırdıkça ekleniyor
    this._activeFilter = null;
    this._activeGenre = null;
    this._currentKey = null;
    this._currentStation = null;
    this._isPlaying = false;
    this._searchTimer = null;
    this._hls = null;        // aktif hls.js örneği (yalnız HLS çalarken)
    this._hlsToken = 0;      // geciken dinamik import eski istasyona bağlanmasın

    // Favoriler: anahtar → tam istasyon kaydı. Tam kayıt saklanır ki sekme,
    // 1,2 MB'lık dizin hiç inmeden de açılabilsin.
    this._favorites = new Map();
    const saved = storeRead(FAVORITES_KEY);
    if (Array.isArray(saved)) {
      saved.forEach((s) => {
        if (s && s.name && s.url) this._favorites.set(stationKey(s), s);
      });
    }
  }

  connectedCallback() {
    // Öznitelikler kurucuda henüz garanti değil; dil seçimi burada yapılır.
    this._t = LANGS[pickLang(this.getAttribute("lang"), navigator.language)];
    // #s=<istasyon anahtarı> derin bağlantısı: liste yüklenince seçilir
    // (çalınmaz — kullanıcı hareketi olmadan tarayıcı zaten izin vermez).
    const hash = location.hash.match(/^#s=(.+)$/);
    this._pendingLink = hash ? decodeURIComponent(hash[1]) : null;
    ensureInterFont();
    this._render();
    this._fetchData();
  }

  /* ── render skeleton ─────────────────────────── */
  _render() {
    const style = createStyleLink();
    const t = this._t;

    const root = el("div", "radyola-root");
    // Ekran okuyucular için dil, ev sahibi sayfaya dokunmadan bileşende işaretli.
    root.setAttribute("lang", t === LANGS.tr ? "tr" : "en");
    root.innerHTML = `
      <div class="ambient-bg"><div class="orb"></div><div class="orb"></div><div class="orb"></div></div>
      <div class="app">
        <header class="header">
          <div class="logo">${SVG.radio}<span>Radyola</span></div>
          <p>${t.tagline}</p>
        </header>
        <div class="source-toggle" id="sourceToggle" role="tablist" aria-label="${t.stationList}">
          <button class="source-btn active" data-source="curated" role="tab" aria-selected="true">${t.tabCurated}</button>
          <button class="source-btn" data-source="directory" role="tab" aria-selected="false">${t.tabDiscover}</button>
          <button class="source-btn" data-source="favorites" role="tab" aria-selected="false">${t.tabFavorites}</button>
        </div>
        <div class="search-wrap">
          ${SVG.search}
          <input type="text" placeholder="${t.searchCurated}" id="searchInput" aria-label="${t.searchAria}">
          <button class="search-clear" id="searchClear" aria-label="${t.clearSearch}" title="${t.clearSearch}">${SVG.close}</button>
        </div>
        <div class="locations" id="locationsBar"></div>
        <div class="locations" id="genresBar"></div>
        <div class="stations" id="stationList">
          <div class="loading"><div class="spinner"></div></div>
        </div>
      </div>
      <div class="player-bar" id="playerBar">
        <div class="player-inner">
          <div class="player-art">
            <div class="pulse-ring"></div>
            ${SVG.radio}
          </div>
          <div class="player-info">
            <div class="player-name" id="pName">${t.selectStation}</div>
            <div class="player-loc" id="pLoc">—</div>
          </div>
          <div class="player-controls">
            <button class="ctrl-btn" id="btnPrev" aria-label="${t.prevStation}">${SVG.prev}</button>
            <button class="ctrl-btn play-btn" id="btnPlay" aria-label="${t.playPause}">${SVG.play}</button>
            <button class="ctrl-btn" id="btnNext" aria-label="${t.nextStation}">${SVG.next}</button>
            <button class="ctrl-btn share-btn" id="btnShare" aria-label="${t.share}" title="${t.share}">${SVG.share}</button>
            <div class="vol-wrap">
              ${SVG.vol}
              <input type="range" class="vol-slider" id="volSlider" min="0" max="1" step="0.01" value="0.8" aria-label="${t.volume}">
            </div>
          </div>
        </div>
      </div>
    `;

    this.shadowRoot.appendChild(style);
    this.shadowRoot.appendChild(root);

    /* cache refs */
    this._audio = document.createElement("audio");
    // Ölü yayına tıklayan kullanıcı aksi hâlde hiçbir şey görmüyor: play()
    // sözü sessizce reddediliyor, çubuk "çalıyor" gibi kalıyordu.
    this._audio.addEventListener("error", () => {
      if (!this._audio.error) return;
      // http-only akış https'e yükseltilerek denendi (bkz. playableUrl);
      // sunucu TLS konuşmuyorsa buraya düşer — asıl nedeni söyle.
      const insecure = this._currentStation && isInsecure(this._currentStation.url);
      this._streamFailed(insecure ? this._t.errHttp : undefined);
    });
    this._audio.addEventListener("stalled", () => {
      if (this._isPlaying) this._elBar.classList.add("is-buffering");
    });
    this._audio.addEventListener("playing", () => {
      this._elBar.classList.remove("is-buffering");
      this._setMediaSessionState("playing");
    });
    this._setupMediaSession();
    this._elList = this.shadowRoot.getElementById("stationList");
    this._elLocs = this.shadowRoot.getElementById("locationsBar");
    this._elGenres = this.shadowRoot.getElementById("genresBar");
    this._elSearch = this.shadowRoot.getElementById("searchInput");
    this._elToggle = this.shadowRoot.getElementById("sourceToggle");
    this._elBar = this.shadowRoot.getElementById("playerBar");
    this._elPName = this.shadowRoot.getElementById("pName");
    this._elPLoc = this.shadowRoot.getElementById("pLoc");
    this._btnPlay = this.shadowRoot.getElementById("btnPlay");
    this._btnPrev = this.shadowRoot.getElementById("btnPrev");
    this._btnNext = this.shadowRoot.getElementById("btnNext");
    this._btnShare = this.shadowRoot.getElementById("btnShare");
    this._volSlider = this.shadowRoot.getElementById("volSlider");
    this._elClear = this.shadowRoot.getElementById("searchClear");

    /* events */
    this._elSearch.addEventListener("input", () => {
      this._elClear.classList.toggle("visible", this._elSearch.value.length > 0);
      this._onSearch();
    });
    this._elSearch.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this._elSearch.value) {
        this._clearSearch();
        e.stopPropagation();
      }
    });
    this._elClear.addEventListener("click", () => {
      this._clearSearch();
      this._elSearch.focus();
    });
    this._btnShare.addEventListener("click", () => this._shareStation());
    this._elToggle.addEventListener("click", (e) => {
      const btn = e.target.closest(".source-btn");
      if (btn) this._setSource(btn.dataset.source);
    });
    this._btnPlay.addEventListener("click", () => this._togglePlay());
    this._btnPrev.addEventListener("click", () => this._skip(-1));
    this._btnNext.addEventListener("click", () => this._skip(1));
    this._volSlider.addEventListener("input", (e) => {
      this._audio.volume = parseFloat(e.target.value);
      storeWrite(VOLUME_KEY, this._audio.volume);
    });

    // "/" aramaya odaklanır — bir metin alanına yazılmıyorsa. Shadow DOM'da
    // hedefi document.activeElement değil composedPath verir.
    this._onDocKey = (e) => {
      if (e.key !== "/" || e.ctrlKey || e.metaKey || e.altKey) return;
      const t = e.composedPath()[0];
      const typing =
        t instanceof HTMLElement &&
        (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
      if (typing) return;
      e.preventDefault();
      this._elSearch.focus();
    };
    document.addEventListener("keydown", this._onDocKey);

    const savedVol = storeRead(VOLUME_KEY);
    this._audio.volume =
      typeof savedVol === "number" && savedVol >= 0 && savedVol <= 1 ? savedVol : 0.8;
    this._volSlider.value = String(this._audio.volume);
  }

  /* ── data ─────────────────────────── */
  /** Adresleri sırayla dener; ilk başarılı JSON yanıtı kazanır. */
  async _fetchFirstReachable(urls) {
    let lastError;
    for (const url of urls) {
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
      } catch (err) {
        lastError = err;
      }
    }
    throw lastError;
  }

  async _fetchData(source = this._source) {
    // Favoriler her seferinde localStorage'daki haritadan kurulur — ağ yok,
    // bayat kopya yok (kalp eklenip çıkarıldıkça harita değişiyor).
    if (source === "favorites") {
      const favs = [...this._favorites.values()].map((s) => ({ ...s }));
      favs.forEach((s) => {
        s.flag = flagOf(s.countryCode);
        s.id = stationKey(s);
        s.search = `${s.name} ${s.location} ${s.genre}`;
      });
      this._lists.favorites = favs;
      if (this._source === source) this._useList(source);
      return;
    }

    // Daha önce çekilmişse ağa çıkma: kaynak geçişi anında olsun.
    if (this._lists[source]) {
      this._useList(source);
      return;
    }

    this._elList.innerHTML = `<div class="loading"><div class="spinner"></div></div>`;
    try {
      const json = await this._fetchFirstReachable(SOURCES[source].urls);

      const stations = json
        .map((r) => ({
          name: r.title || "",
          url: r.url || "",
          website: r.website || "",
          location: r.location || "",
          countryCode: r.countryCode || "",
          flag: flagOf(r.countryCode),
          genre: r.genre || "",
          votes: r.votes || 0,
          // Dizin crawler'ı akış biçimini de yazıyor; satır rozetlerinde
          // gösterilir. Kuratörlü listede bu alanlar yok — boş kalır.
          codec: r.codec && r.codec !== "UNKNOWN" ? r.codec : "",
          bitrate: r.bitrate || 0,
          hls: r.hls === true,
        }))
        .filter((s) => s.name && s.url.startsWith("http"));

      // Kuratörlü listenin sırası elle verilmiş, korunur. Dizin rastgele
      // sırada geliyor; oy en anlamlı sıralama ölçütü.
      if (source === "directory") stations.sort((a, b) => b.votes - a.votes);

      stations.forEach((s) => {
        s.id = stationKey(s);
        s.search = `${s.name} ${s.location} ${s.genre}`;
      });

      this._lists[source] = stations;
      if (this._source === source) this._useList(source);
    } catch (err) {
      if (this._source !== source) return;
      this._elList.innerHTML = `<div class="empty-state">${this._t.loadFailed}</div>`;
      const retry = el("button", "retry-btn");
      retry.textContent = this._t.retry;
      retry.addEventListener("click", () => this._fetchData(source));
      this._elList.firstElementChild.appendChild(retry);
    }
  }

  /** Çekilmiş bir listeyi ekrana bağlar: filtre şeritlerini ve arama indeksini kurar. */
  _useList(source) {
    this._stations = this._lists[source];
    // Fuse indeksi her tuş vuruşunda değil, liste başına bir kez kurulur —
    // 3.400 kayıtta yeniden indekslemek aramayı hissedilir şekilde yavaşlatıyordu.
    this._fuse = new Fuse(this._stations, {
      keys: ["name", "location", "genre"],
      threshold: 0.35,
      ignoreLocation: true,
    });
    this._buildLocations();
    this._buildGenres();
    this._applyFilters();
    this._resolvePendingLink();
  }

  /**
   * Derin bağlantı: #s=<anahtar> istasyonu bulununca duraklatılmış seçilir.
   * Kuratörlü listede yoksa dizin arka planda bir kez çekilir (görünüm
   * değişmez; _fetchData sonucu yalnız aktif kaynaksa ekrana bağlar).
   */
  _resolvePendingLink() {
    if (!this._pendingLink) return;
    const id = this._pendingLink;
    const s = this._findStation(id);
    if (s) {
      this._pendingLink = null;
      this._playStation(id, { autoplay: false });
      return;
    }
    if (!this._lists.directory && !this._linkDirectoryRequested) {
      this._linkDirectoryRequested = true;
      this._fetchData("directory").then(() => this._resolvePendingLink());
    }
  }

  /** Curated ↔ Discover geçişi. */
  _setSource(source) {
    if (this._source === source) return;
    this._source = source;
    this._activeFilter = null;
    this._activeGenre = null;
    this._elSearch.value = "";
    this._elToggle.querySelectorAll(".source-btn").forEach((b) => {
      const active = b.dataset.source === source;
      b.classList.toggle("active", active);
      b.setAttribute("aria-selected", String(active));
    });
    this._elClear.classList.remove("visible");
    this._elSearch.placeholder = {
      curated: this._t.searchCurated,
      directory: this._t.searchDirectory,
      favorites: this._t.searchFavorites,
    }[source];
    this._fetchData(source);
  }

  _clearSearch() {
    this._elSearch.value = "";
    this._elClear.classList.remove("visible");
    this._applyFilters();
  }

  /* ── location filter pills ─────────────────────────── */
  _buildLocations() {
    this._elLocs.innerHTML = "";
    const map = {};
    this._stations.forEach((s) => {
      const country = s.location.split(",").pop().trim();
      if (country) map[country] = (map[country] || 0) + 1;
    });

    // "All" pill
    const allPill = el("button", "loc-pill active");
    allPill.textContent = "All";
    allPill.addEventListener("click", () => {
      this._activeFilter = null;
      this._applyFilters();
      this._elLocs.querySelectorAll(".loc-pill").forEach((p) => p.classList.remove("active"));
      allPill.classList.add("active");
    });
    this._elLocs.appendChild(allPill);

    Object.keys(map).sort().forEach((country) => {
      const pill = el("button", "loc-pill");
      pill.textContent = country;
      pill.addEventListener("click", () => {
        this._activeFilter = country;
        this._applyFilters();
        this._elLocs.querySelectorAll(".loc-pill").forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
      });
      this._elLocs.appendChild(pill);
    });
  }

  /* ── genre filter pills ─────────────────────────── */
  _buildGenres() {
    this._elGenres.innerHTML = "";
    const counts = {};
    this._stations.forEach((s) => {
      if (s.genre) {
        s.genre.split("/").forEach((g) => {
          const gt = g.trim();
          if (gt) counts[gt] = (counts[gt] || 0) + 1;
        });
      }
    });

    // Dizinde 438 tür var; hepsini şeride basmak onu kullanılmaz hâle getirir.
    const map = {};
    Object.entries(counts)
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, MAX_GENRE_PILLS)
      .forEach(([g, n]) => (map[g] = n));

    const allPill = el("button", "loc-pill active");
    allPill.textContent = "All Genres";
    allPill.addEventListener("click", () => {
      this._activeGenre = null;
      this._applyFilters();
      this._elGenres.querySelectorAll(".loc-pill").forEach((p) => p.classList.remove("active"));
      allPill.classList.add("active");
    });
    this._elGenres.appendChild(allPill);

    Object.keys(map).sort().forEach((genre) => {
      const pill = el("button", "loc-pill");
      pill.textContent = genre;
      pill.addEventListener("click", () => {
        this._activeGenre = genre;
        this._applyFilters();
        this._elGenres.querySelectorAll(".loc-pill").forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
      });
      this._elGenres.appendChild(pill);
    });
  }

  _applyFilters() {
    const query = this._elSearch.value.trim();

    // Arama önce: hazır indeks üzerinden çalışıp sonucu daraltıyoruz. Böylece
    // her tuş vuruşunda 3.400 kayıt yeniden indekslenmiyor.
    let list = query.length > 0
      ? this._fuse.search(query).map((r) => r.item)
      : this._stations;

    if (this._activeFilter) {
      list = list.filter((s) => s.location.includes(this._activeFilter));
    }
    if (this._activeGenre) {
      list = list.filter((s) => s.genre && s.genre.includes(this._activeGenre));
    }

    this._filtered = list;
    this._renderList();
  }

  _onSearch() {
    // Dizinde her harfte arama çalıştırmak gereksiz iş; kullanıcı durunca çalışsın.
    clearTimeout(this._searchTimer);
    this._searchTimer = setTimeout(() => this._applyFilters(), SEARCH_DEBOUNCE);
  }

  /* ── render station list ─────────────────────────── */
  /**
   * Listeyi baştan çizer.
   *
   * Dizinde 3.400 kayıt var; hepsini DOM'a basmak sayfayı dondurur. İlk sayfa
   * çizilir, gerisi listenin sonundaki gözcü görünür oldukça eklenir.
   */
  _renderList() {
    this._elList.innerHTML = "";
    this._rendered = 0;

    if (this._filtered.length === 0) {
      const msg =
        this._source === "favorites" && this._stations.length === 0
          ? this._t.noFavorites
          : this._t.noStations;
      this._elList.innerHTML = `<div class="empty-state">${msg}</div>`;
      return;
    }

    this._renderMore();
  }

  _renderMore() {
    const slice = this._filtered.slice(this._rendered, this._rendered + PAGE_SIZE);
    this._rendered += slice.length;
    this._appendRows(slice);

    this._sentinel?.remove();
    this._sentinel = null;
    if (this._rendered >= this._filtered.length) return;

    // Gözcü görününce bir sayfa daha ekle.
    this._sentinel = el("div", "list-sentinel");
    this._elList.appendChild(this._sentinel);
    this._observer ??= new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) this._renderMore();
    });
    this._observer.disconnect();
    this._observer.observe(this._sentinel);
  }

  _appendRows(stations) {
    stations.forEach((s) => {
      // Satır gerçek bir düğme değil (içinde kalp ve site bağlantısı var,
      // düğme içinde düğme geçersiz olurdu) — klavye için role+tabindex+keydown.
      const row = el("div", "station" + (s.id === this._currentKey ? " playing" : ""), {
        role: "button",
        tabindex: "0",
      });
      row.dataset.id = s.id;
      row.setAttribute("aria-label", this._t.playLabel(s.name));

      // "AAC · 128 kbps" — dizin verisinde var, kuratörlü listede boş.
      const quality = [s.codec, s.bitrate ? `${s.bitrate} kbps` : ""]
        .filter(Boolean)
        .join(" · ");

      row.innerHTML = `
        <div class="station-icon">
          <svg class="play-ico" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
          <div class="eq-bars"><div class="eq-bar"></div><div class="eq-bar"></div><div class="eq-bar"></div><div class="eq-bar"></div></div>
        </div>
        <div class="station-info">
          <div class="station-name">${s.flag ? `<span class="station-flag">${s.flag}</span>` : ""}${this._esc(s.name)}</div>
          <div class="station-meta">
            <span class="station-loc">${this._esc(s.location)}</span>
            ${s.genre ? `<span class="station-genre">${this._esc(s.genre)}</span>` : ""}
            ${quality ? `<span class="station-quality">${this._esc(quality)}</span>` : ""}
            ${isInsecure(s.url) ? `<span class="station-http" title="${this._t.httpTitle}">HTTP</span>` : ""}
          </div>
        </div>
      `;

      const fav = el("button", "station-fav" + (this._favorites.has(s.id) ? " active" : ""), {
        "aria-pressed": String(this._favorites.has(s.id)),
        title: this._t.favorite,
      });
      fav.setAttribute("aria-label", this._t.favLabel(s.name));
      fav.innerHTML = SVG.heart;
      fav.addEventListener("click", (e) => {
        e.stopPropagation();
        this._toggleFavorite(s, fav);
      });
      row.appendChild(fav);

      // Website bağlantısı HTML string'ine gömülmez: _esc tırnak kaçırmıyor,
      // veri kaynağı da topluluk düzenlemesine açık — href'ten öznitelik
      // enjeksiyonu mümkün olurdu. setAttribute bu sınıf hatayı yapısal kapatır.
      const site = safeWebsite(s.website);
      if (site) {
        const ext = el("a", "station-ext", {
          href: site, target: "_blank", rel: "noopener", title: this._t.website,
        });
        ext.innerHTML = SVG.extLink;
        row.appendChild(ext);
      }

      row.addEventListener("click", (e) => {
        if (e.target.closest(".station-ext, .station-fav")) return;
        this._playStation(s.id);
      });
      row.addEventListener("keydown", (e) => {
        // Kalbin/bağlantının üzerindeki Enter kendi işini yapsın.
        if (e.target !== row || (e.key !== "Enter" && e.key !== " ")) return;
        e.preventDefault();
        this._playStation(s.id);
      });
      this._elList.appendChild(row);
    });
  }

  /* ── favorites ─────────────────────────── */
  _toggleFavorite(s, btn) {
    const key = stationKey(s);
    const nowActive = !this._favorites.has(key);
    if (nowActive) {
      // id/search türetilebilir alanlar, saklamaya değmez.
      const { id, search, ...record } = s;
      this._favorites.set(key, record);
    } else {
      this._favorites.delete(key);
    }
    storeWrite(FAVORITES_KEY, [...this._favorites.values()]);
    btn.classList.toggle("active", nowActive);
    btn.setAttribute("aria-pressed", String(nowActive));
    // Favoriler sekmesi açıkken kalbi kaldırılan satır listeden de düşsün.
    if (this._source === "favorites" && !nowActive) this._fetchData("favorites");
  }

  /* ── playback ─────────────────────────── */
  /** Önce aktif listede, sonra yüklü öbür listelerde arar (derin bağlantı
      dizinden bir istasyonu, görünüm kuratörlüyken seçebilir). */
  _findStation(id) {
    return (
      this._stations.find((st) => st.id === id) ||
      Object.values(this._lists)
        .flat()
        .find((st) => st.id === id)
    );
  }

  _playStation(id, { autoplay = true } = {}) {
    const s = this._findStation(id);
    if (!s) return;

    this._currentKey = id;
    this._currentStation = s;
    this._teardownStream();
    this._isPlaying = autoplay;

    if (autoplay) {
      const src = playableUrl(s.url);
      // Safari HLS'i doğal çözer; Chrome/Firefox'un <audio>'su çözemez, MSE
      // üzerinden hls.js gerekir.
      if (isHlsStream(s) && !this._audio.canPlayType("application/vnd.apple.mpegurl")) {
        this._playHls(src);
      } else {
        this._audio.src = src;
        this._audio.load();
        this._audio.play().catch(() => {});
      }
    }
    // autoplay=false: derin bağlantıyla gelinen istasyon çubukta hazır bekler;
    // kullanıcı çal deyince _togglePlay akışı sıfırdan kurar. Tarayıcılar
    // kullanıcı hareketi olmadan sesi zaten başlatmaz.

    // Adres çubuğu hep çalanı gösterir — kopyalanan bağlantı istasyonu taşır.
    // replaceState: her istasyon geçmişe ayrı kayıt olmasın.
    history.replaceState(null, "", "#s=" + encodeURIComponent(s.id));

    this._elPName.textContent = s.name;
    this._elPLoc.textContent = s.genre ? `${s.location}  ·  ${s.genre}` : s.location;
    this._elPLoc.classList.remove("error");
    document.title = `${s.name} — Radyola`;
    this._btnPlay.innerHTML = autoplay ? SVG.pause : SVG.play;
    this._elBar.classList.add("visible");
    this._elBar.classList.toggle("is-playing", autoplay);

    this._updateMediaSessionMetadata(s);
    this._setMediaSessionState(autoplay ? "playing" : "paused");
    this._highlightPlaying();
  }

  /** Çalan (ya da seçili) istasyonun bağlantısını paylaş: yerel paylaşım
      menüsü varsa o, yoksa panoya kopyala + kısa geri bildirim. */
  async _shareStation() {
    const s = this._currentStation;
    if (!s) return;
    const url = location.href;
    if (navigator.share) {
      navigator.share({ title: `${s.name} — Radyola`, url }).catch(() => {});
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
    } catch {
      return; // pano izni yok: sessizce vazgeç
    }
    clearTimeout(this._shareTimer);
    const original = this._elPLoc.textContent;
    this._elPLoc.textContent = this._t.linkCopied;
    this._shareTimer = setTimeout(() => {
      if (this._elPLoc.textContent === this._t.linkCopied) {
        this._elPLoc.textContent = original;
      }
    }, 1600);
  }

  /** Önceki akışı söker: hls.js örneği, kaynak, bekleyen import bağlanması. */
  _teardownStream() {
    this._hlsToken++;
    if (this._hls) {
      this._hls.destroy();
      this._hls = null;
    }
    this._audio.pause();
    this._audio.removeAttribute("src");
  }

  /**
   * hls.js ilk HLS istasyonuna kadar indirilmez: dinamik import, esbuild
   * `splitting` ile ayrı bir parça üretiyor; MP3/AAC dinleyen kullanıcı
   * kitaplığın bedelini hiç ödemiyor.
   */
  async _playHls(src) {
    const token = this._hlsToken;
    let Hls;
    try {
      ({ default: Hls } = await import("hls.js"));
    } catch {
      this._streamFailed(this._t.errHlsLoad);
      return;
    }
    // Import beklerken kullanıcı başka istasyona geçtiyse buna bağlanma.
    if (token !== this._hlsToken) return;
    if (!Hls.isSupported()) {
      this._streamFailed(this._t.errHlsUnsupported);
      return;
    }
    this._hls = new Hls();
    this._hls.on(Hls.Events.ERROR, (_event, data) => {
      if (data.fatal) this._streamFailed();
    });
    this._hls.loadSource(src);
    this._hls.attachMedia(this._audio);
    this._audio.play().catch(() => {});
  }

  /** Akış açılamadı: çubuğu duraklat ve nedenini söyle. */
  _streamFailed(message) {
    if (!this._currentKey) return;
    this._isPlaying = false;
    this._btnPlay.innerHTML = SVG.play;
    this._elBar.classList.remove("is-playing", "is-buffering");
    this._elPLoc.textContent = message || this._t.errGeneric;
    this._elPLoc.classList.add("error");
    this._setMediaSessionState("paused");
    this._highlightPlaying();
  }

  /* ── Media Session API ─────────────────────────── */
  /**
   * Tarayıcının medya arayüzüne bağlanır: klavye medya tuşları, kulaklık
   * tuşları ve telefonda kilit ekranı/bildirim kontrolleri.
   */
  _setupMediaSession() {
    if (!("mediaSession" in navigator)) return;
    const on = (action, handler) => {
      // Tarayıcı tanımadığı eylemde fırlatır; desteklenenler yeter.
      try { navigator.mediaSession.setActionHandler(action, handler); } catch { /* yok say */ }
    };
    on("play", () => this._togglePlay());
    on("pause", () => this._togglePlay());
    on("previoustrack", () => this._skip(-1));
    on("nexttrack", () => this._skip(1));
  }

  _updateMediaSessionMetadata(s) {
    if (!("mediaSession" in navigator)) return;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: s.name,
      artist: s.genre ? `${s.location} · ${s.genre}` : s.location,
      album: "Radyola",
    });
  }

  _setMediaSessionState(state) {
    if ("mediaSession" in navigator) navigator.mediaSession.playbackState = state;
  }

  /**
   * Çalan satırı işaretler.
   *
   * Listeyi baştan çizmiyoruz: dizinde kullanıcı yüzlerce satır kaydırmış
   * olabilir, yeniden çizim onu başa atardı.
   */
  _highlightPlaying() {
    this._elList.querySelectorAll(".station").forEach((row) => {
      row.classList.toggle("playing", row.dataset.id === this._currentKey);
    });
  }

  _togglePlay() {
    if (!this._currentKey) return;
    // Derin bağlantıyla duraklatılmış seçildiyse kaynak henüz bağlı değil:
    // ilk "çal" akışı sıfırdan kurar (HLS/https yükseltme yolları dahil).
    if (!this._audio.currentSrc && !this._hls) {
      this._playStation(this._currentKey);
      return;
    }
    if (this._audio.paused) {
      this._audio.play().catch(() => {});
      this._isPlaying = true;
      this._btnPlay.innerHTML = SVG.pause;
      this._elBar.classList.add("is-playing");
      this._setMediaSessionState("playing");
    } else {
      this._audio.pause();
      this._isPlaying = false;
      this._btnPlay.innerHTML = SVG.play;
      this._elBar.classList.remove("is-playing");
      this._setMediaSessionState("paused");
    }
    this._highlightPlaying();
  }

  _skip(dir) {
    if (this._filtered.length === 0) return;
    const curFilterIdx = this._filtered.findIndex((s) => s.id === this._currentKey);
    let next = curFilterIdx + dir;
    if (next < 0) next = this._filtered.length - 1;
    if (next >= this._filtered.length) next = 0;
    this._playStation(this._filtered[next].id);
  }

  _esc(str) {
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
  }

  disconnectedCallback() {
    this._teardownStream();
    clearTimeout(this._searchTimer);
    clearTimeout(this._shareTimer);
    this._observer?.disconnect();
    document.removeEventListener("keydown", this._onDocKey);
  }
}

customElements.define("aripd-radyola", AripdRadyola);

/* ── Auto dark mode (host page) ─────────────────────────── */
;(function () {
  const h = document.querySelector("html");
  if (h.getAttribute("data-bs-theme") === "auto") {
    function updateTheme() {
      h.setAttribute("data-bs-theme",
        window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
      );
    }
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", updateTheme);
    updateTheme();
  }
})();