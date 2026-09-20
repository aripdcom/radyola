/**
 * Radyola — radio-browser.info Crawler
 *
 * radio-browser.info API'sinden radyo istasyonu verilerini çeker ve
 * "Keşfet" dizinini (data/directory.json) üretir.
 *
 * Kuratörlü listeye (data/stations.json) DOKUNMAZ — orası elle bakılan,
 * her platformun varsayılan olarak yüklediği kısa listedir. Bir crawl'ın
 * yan ürünü olarak yeniden üretilirse elle seçilen istasyonlar kaybolur.
 *
 * Kullanım:
 *   node crawler.js                         → Varsayılan ülke listesi
 *   node crawler.js --countries TR,BE,GB    → Belirli ülke kodları
 *   node crawler.js --all --min-votes 1000  → Tüm dünya, popüler istasyonlar
 *   node crawler.js --include-broken        → Bozuk istasyonları da al
 */

const https = require("https");
const http = require("http");
const fs = require("fs");
const path = require("path");

/* ── Configuration ──────────────────────────────────────────── */

const API_BASE = "https://de1.api.radio-browser.info";

// Radyola projesinde varsayılan ülkeler
const DEFAULT_COUNTRIES = ["TR", "BE", "GB", "RU", "GR", "DE", "FR", "NL", "US", "JP"];

// radio-browser'ın ham ülke adları uzun ve resmî ("The United Kingdom Of Great
// Britain And Northern Ireland"). Platformların bayrak sözlükleri kısa adı
// bekliyor, o yüzden ISO koddan kanonik kısa ada çeviriyoruz. Aşağıdaki tablo
// yalnızca Intl'in verdiğinden farklı bir etiket istediğimiz yerler için.
const COUNTRY_NAME_MAP = {
  TR: "Türkiye",
  BE: "Belgium",
  GB: "United Kingdom",
  RU: "Russia",
  GR: "Greece",
  DE: "Germany",
  FR: "France",
  NL: "Netherlands",
  US: "United States",
  JP: "Japan",
  IT: "Italy",
  ES: "Spain",
  BR: "Brazil",
  CA: "Canada",
  AU: "Australia",
  SE: "Sweden",
  NO: "Norway",
  DK: "Denmark",
  FI: "Finland",
  AT: "Austria",
  CH: "Switzerland",
  PT: "Portugal",
  PL: "Poland",
  CZ: "Czechia",
  IE: "Ireland",
  AR: "Argentina",
  MX: "Mexico",
  IN: "India",
  KR: "South Korea",
  ZA: "South Africa",
};

/* ── Country Names ─────────────────────────────────────────── */

const regionNames = (() => {
  try {
    return new Intl.DisplayNames(["en"], { type: "region" });
  } catch {
    return null; // ICU verisi yoksa (küçük Node derlemeleri) tabloya düşeriz
  }
})();

/**
 * ISO 3166-1 alpha-2 kodundan kısa, kanonik ülke adı üretir.
 * Sıra: elle tanımlı tablo → Intl.DisplayNames → API'nin ham adı → kodun kendisi.
 */
function countryName(code, rawName) {
  if (!code) return rawName || "";
  if (COUNTRY_NAME_MAP[code]) return COUNTRY_NAME_MAP[code];
  const display = regionNames ? regionNames.of(code) : null;
  // Intl bilinmeyen kodu olduğu gibi geri verir; o durumda ham ada düşelim.
  if (display && display !== code) return display;
  return rawName || code;
}

/* ── Genre Tags ────────────────────────────────────────────── */

// radio-browser etiketleri serbest metin: aynı tür beş ayrı yazımla geliyor,
// yanına frekans ("107.7 fm"), şehir adı ve yayıncı markası karışıyor. Ham
// hâlleriyle 3.4 binlik dizinde 1.365 farklı etiket çıkıyor ve bunların 833'ü
// tek bir istasyonda geçiyor — filtre olarak kullanılamaz. Aşağısı bunu toparlar.

/**
 * Yazım varyantlarını tek anahtarda birleştiren eşleştirme anahtarı.
 * "80's" / "#80s" / "80s" → "80s";  "Hip-hop" / "Hip hop" → "hiphop"
 */
function tagKey(tag) {
  return tag
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "") // "México" → "mexico", "Müzik" → "muzik"
    .replace(/[\s\-_'’#.,!&/()\[\]]+/gu, "");
}

// Diller arası ve anlamsal birleştirmeler. Anahtar tagKey() çıktısıdır.
// Yalnızca yüksek güvenli eşlemeler — şüphede olan etiket olduğu gibi kalır,
// zaten frekans eşiğine takılırsa düşer.
const TAG_SYNONYMS = {
  // müzik
  muzik: "Music", музыка: "Music", музика: "Music",
  音乐: "Music", musica: "Music", musique: "Music", musik: "Music", muzyka: "Music",
  // haber
  haber: "News", haberler: "News", новости: "News", новини: "News",
  新闻: "News", nachrichten: "News", noticias: "News", notizie: "News",
  nouvelles: "News", actualites: "News",
  // tür karşılıkları
  рок: "Rock", поп: "Pop", turku: "Folk", halkmuzigi: "Folk",
  этно: "Folk", ретро: "Oldies", политика: "Politics", разговорное: "Talk",
  танцевальнаямузыка: "Dance", аудиокниги: "Audiobooks",
  // yaygın yazım birleştirmeleri
  hiphop: "Hip Hop", rnb: "R&B", randb: "R&B", top40: "Top 40",
  classicrock: "Classic Rock", hardrock: "Hard Rock", deephouse: "Deep House",
  chillout: "Chillout", easylistening: "Easy Listening",
  adultcontemporary: "Adult Contemporary", publicradio: "Public Radio",
  popmusic: "Pop", rockmusic: "Rock", classicalmusic: "Classical",
  folkmusic: "Folk", dancemusic: "Dance", electronicmusic: "Electronic",
};

// Tür değil, yayıncı/platform adı olan etiketler.
const NON_GENRE_TAGS = new Set(["mediaset", "tv", "hd", "am", "fm", "radio", "online", "livestream"]);

/**
 * Etiketin tür olmadığına karar verir.
 *
 * Eş anlamlı eşlemesinden SONRA çağrılmalı: "音乐" iki karakter ama
 * eşleme onu "Music" yaptığı için buraya hiç gelmez.
 */
function isNoiseTag(tag) {
  const t = tag.trim();
  if (t.length <= 2) return true;                                 // "Ff", "Us"
  if (t.length > 25) return true;                                 // etiket değil, cümle
  if (/^[\d\s.,]+$/.test(t)) return true;                         // "107.7", "95.1"
  if (/^https?:/i.test(t) || t.includes("://")) return true;      // etikete kaçmış akış adresi
  if (/^\d{2,4}\s*[.,]?\d*\s*(fm|am|mhz|khz)$/i.test(t)) return true; // "93.3 fm"
  if (NON_GENRE_TAGS.has(tagKey(t))) return true;
  return false;
}

/**
 * İstasyonun kendi şehri ya da ülkesi tür sayılmaz.
 * radio-browser'da "Aguascalientes", "Tirana" gibi etiketler bol.
 *
 * Tam eşitlik yetmiyor: konum "Ciudad de México" iken etiket "Ciudad mexico"
 * olarak geliyor. Bu yüzden etiketin BÜTÜN kelimeleri konumda geçiyorsa yer
 * adı sayıyoruz. Kapsama tek yönlü: "Mexico city" (city konumda yok) ve
 * "Türkü" (Türkiye'nin kelimesi değil) tür olarak kalır.
 */
function isOwnPlaceName(tag, station) {
  const words = (text) =>
    text
      .split(/[\s,]+/)
      .map(tagKey)
      .filter((w) => w.length >= 3);

  const tagWords = words(tag);
  if (tagWords.length === 0) return false;
  const placeWords = new Set(words(station.location));
  return tagWords.every((w) => placeWords.has(w));
}

/**
 * İstasyon adından yayıncı ailesini çıkarır: "181.FM - 80's Country" → "181.fm"
 *
 * Bir ağın tüm kanalları aynı önekle geliyor; tür etiketini kaç ayrı yayıncının
 * kullandığını sayabilmek için gerekiyor.
 */
function broadcasterFamily(title) {
  return tagKey(title.split(/[-–|:]/)[0]) || tagKey(title);
}

/**
 * Tüm crawl bittikten sonra tür alanlarını yeniden kurar.
 *
 * Frekans eşiği ancak bütün veri elde olunca uygulanabildiği için bu iş
 * istasyon bazında değil, toplu yapılıyor: önce her etiket normalize edilip
 * sayılıyor, sonra [minCount] altında kalanlar atılıyor.
 *
 * Görünen etiket olarak en sık rastlanan yazım seçilir — 1.365 etikete elle
 * isim vermek yerine veriye bakıyoruz.
 */
function finalizeGenres(stations, minCount) {
  const totals = new Map();    // tagKey → toplam görülme
  const labels = new Map();    // tagKey → Map<görünen yazım, kaç kez>
  const families = new Map();  // tagKey → Set<yayıncı ailesi>

  const cleanedPerStation = stations.map((station) => {
    const seen = new Set();
    const kept = [];
    for (const raw of station._meta.tags) {
      const synonym = TAG_SYNONYMS[tagKey(raw)];
      const tag = synonym || raw;
      if (isNoiseTag(tag) || isOwnPlaceName(tag, station)) continue;
      const key = tagKey(tag);
      if (!key || seen.has(key)) continue;
      seen.add(key);
      kept.push({ key, label: tag });
      totals.set(key, (totals.get(key) || 0) + 1);
      const family = families.get(key) || new Set();
      family.add(broadcasterFamily(station.title));
      families.set(key, family);
      const byLabel = labels.get(key) || new Map();
      byLabel.set(tag, (byLabel.get(tag) || 0) + 1);
      labels.set(key, byLabel);
    }
    return kept;
  });

  const canonical = new Map();
  for (const [key, byLabel] of labels) {
    const best = [...byLabel.entries()].sort((a, b) => b[1] - a[1])[0][0];
    canonical.set(key, best);
  }

  // Gerçek bir tür birden çok yayıncıda görünür. Tek yayıncıya sıkışmış etiket
  // marka ya da yer adıdır: "181.FM - …" ağının 34 kanalı "Waynesboro" (şehirleri)
  // etiketini taşıyor ve sırf sayıca eşiği geçiyordu.
  const isGenre = (key) =>
    totals.get(key) >= minCount && families.get(key).size >= 2;

  stations.forEach((station, i) => {
    const kept = cleanedPerStation[i].filter((t) => isGenre(t.key));
    station.genre = kept.slice(0, 3).map((t) => canonical.get(t.key)).join(" / ");
  });

  const surviving = [...totals.keys()].filter(isGenre).length;
  const brandLike = [...totals.keys()].filter(
    (k) => totals.get(k) >= minCount && families.get(k).size < 2
  ).length;
  return { surviving, discarded: totals.size - surviving, brandLike };
}

/* ── CLI Argument Parsing ──────────────────────────────────── */

function parseArgs() {
  const args = process.argv.slice(2);
  const config = {
    countries: DEFAULT_COUNTRIES,
    all: false,
    minVotes: 0,
    workingOnly: true,
    limit: 0, // 0 = no limit
    minTagCount: 3, // bu sayıdan az geçen tür etiketleri elenir
  };

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case "--countries":
        config.countries = args[++i].split(",").map((c) => c.trim().toUpperCase());
        break;
      case "--all":
        config.all = true;
        break;
      case "--min-votes":
        config.minVotes = parseInt(args[++i], 10) || 0;
        break;
      case "--working-only":
        config.workingOnly = true;
        break;
      case "--include-broken":
        config.workingOnly = false;
        break;
      case "--limit":
        config.limit = parseInt(args[++i], 10) || 0;
        break;
      case "--min-tag-count":
        config.minTagCount = parseInt(args[++i], 10) || 0;
        break;
      case "--help":
        console.log(`
Radyola Crawler - radio-browser.info'dan radyo istasyonları çeker

Kullanım:
  node crawler.js [seçenekler]

Seçenekler:
  --countries TR,BE,GB   Belirli ülke kodları (virgülle ayrılmış)
  --all                  Tüm dünya radyoları
  --min-votes N          Minimum oy sayısı (varsayılan: 0)
  --working-only         Sadece çalışan istasyonlar (varsayılan)
  --include-broken       Bozuk istasyonları da dahil et
  --limit N              Ülke başına maksimum istasyon sayısı
  --min-tag-count N      Bu sayıdan az geçen tür etiketlerini ele (varsayılan: 3)
  --help                 Bu yardım mesajını gösterir
`);
        process.exit(0);
    }
  }

  return config;
}

/* ── HTTP Fetch Helper ─────────────────────────────────────── */

function fetchJSON(url) {
  return new Promise((resolve, reject) => {
    const client = url.startsWith("https") ? https : http;
    const req = client.get(
      url,
      {
        headers: {
          "User-Agent": "Radyola-Crawler/1.0 (https://github.com/aripdcom/radyola)",
          Accept: "application/json",
        },
      },
      (res) => {
        if (res.statusCode !== 200) {
          reject(new Error(`HTTP ${res.statusCode} for ${url}`));
          res.resume();
          return;
        }
        let data = "";
        res.on("data", (chunk) => (data += chunk));
        res.on("end", () => {
          try {
            resolve(JSON.parse(data));
          } catch (e) {
            reject(new Error(`JSON parse error: ${e.message}`));
          }
        });
      }
    );
    req.on("error", reject);
    req.setTimeout(30000, () => {
      req.destroy();
      reject(new Error(`Timeout for ${url}`));
    });
  });
}

/* ── Delay helper ──────────────────────────────────────────── */

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/* ── Fetch all countries ───────────────────────────────────── */

async function fetchAllCountryCodes() {
  console.log("📡 Tüm ülke kodları çekiliyor...");
  const countries = await fetchJSON(`${API_BASE}/json/countries`);
  return countries
    .filter((c) => c.stationcount > 0)
    .map((c) => c.iso_3166_1)
    .filter(Boolean);
}

/* ── Fetch stations for a country ──────────────────────────── */

async function fetchStationsByCountry(countryCode, config) {
  const params = new URLSearchParams({
    order: "clickcount",
    reverse: "true",
    hidebroken: config.workingOnly ? "true" : "false",
  });

  if (config.limit > 0) {
    params.set("limit", config.limit.toString());
  }

  const url = `${API_BASE}/json/stations/bycountrycodeexact/${countryCode}?${params}`;
  const stations = await fetchJSON(url);

  // Filter by minimum votes
  return stations.filter((s) => s.votes >= config.minVotes);
}

/* ── Transform to Radyola format ───────────────────────────── */

function transformStation(station) {
  // Build location: "City, Country" or just "Country"
  // state boşluk dizisi olabiliyor; trim etmezsek " , United States" üretiyor.
  const city = (station.state || "").trim();
  const country = countryName(station.countrycode, station.country);
  const location = city ? `${city}, ${country}` : country;

  // Ham etiketler _meta'da taşınır; tür alanı crawl bitince finalizeGenres()
  // tarafından kurulur — frekans eşiği ancak bütün veri elde olunca uygulanabiliyor.
  // Ayraç yalnız virgül değil: "R&b/urban", "Alternative / indie" gibi etiketler
  // tek parça gelirse tür alanının kendi ayracıyla ("/") çakışıp faseti bozuyor.
  const tags = (station.tags || "")
    .split(/[,/;|]/)
    .map((t) => t.trim())
    .filter(Boolean)
    .map((t) => t.charAt(0).toUpperCase() + t.slice(1));

  return {
    // Radyola ortak alanları — data/stations.json ile aynı şema
    date: new Date().toISOString().split("T")[0],
    title: station.name.trim(),
    url: station.url_resolved || station.url,
    website: station.homepage || "",
    location: location,
    // Bayrak emoji'si ada değil koda bakılarak türetilsin diye: her platform
    // iki harfi regional indicator'a çevirebiliyor, 164 satırlık ad tablosu gerekmiyor.
    countryCode: station.countrycode || "",
    genre: "", // finalizeGenres() dolduruyor

    // Extended fields (JSON only)
    _meta: {
      tags,
      stationuuid: station.stationuuid,
      countrycode: station.countrycode,
      language: station.language || "",
      codec: station.codec || "",
      bitrate: station.bitrate || 0,
      votes: station.votes || 0,
      clickcount: station.clickcount || 0,
      favicon: station.favicon || "",
      geo_lat: station.geo_lat,
      geo_long: station.geo_long,
      hls: station.hls === 1,
      lastcheckok: station.lastcheckok === 1,
      ssl_error: station.ssl_error === 1,
    },
  };
}

/* ── CSV Export ─────────────────────────────────────────────── */

function escapeCSV(str) {
  if (!str) return "";
  if (str.includes(",") || str.includes('"') || str.includes("\n")) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function toCSV(stations) {
  const header = "date,title,url,website,location,genre";
  const rows = stations.map(
    (s) =>
      [s.date, s.title, s.url, s.website, s.location, s.genre].map(escapeCSV).join(",")
  );
  return [header, ...rows].join("\n");
}

/* ── Main ──────────────────────────────────────────────────── */

async function main() {
  const config = parseArgs();
  const outputDir = path.join(__dirname, "output");
  const dataDir = path.join(__dirname, "..", "data");

  // Create output directory
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }
  if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
  }

  console.log("╔══════════════════════════════════════════╗");
  console.log("║   📻 Radyola — Radio Browser Crawler     ║");
  console.log("╚══════════════════════════════════════════╝");
  console.log();

  // Determine which countries to crawl
  let countries = config.countries;
  if (config.all) {
    countries = await fetchAllCountryCodes();
    console.log(`🌍 ${countries.length} ülke bulundu\n`);
  }

  const allStations = [];
  const stats = { total: 0, countries: 0, withGenre: 0, withCoords: 0 };

  for (let i = 0; i < countries.length; i++) {
    const code = countries[i];
    const label = countryName(code);

    process.stdout.write(
      `[${i + 1}/${countries.length}] 🔍 ${label} (${code})...`
    );

    try {
      const stations = await fetchStationsByCountry(code, config);
      const transformed = stations.map(transformStation);
      allStations.push(...transformed);

      const withGenre = transformed.filter((s) => s._meta.tags.length > 0).length;
      const withCoords = transformed.filter(
        (s) => s._meta.geo_lat && s._meta.geo_long
      ).length;

      stats.total += transformed.length;
      stats.countries++;
      stats.withGenre += withGenre;
      stats.withCoords += withCoords;

      console.log(
        ` ✅ ${transformed.length} istasyon (${withGenre} genre, ${withCoords} koordinat)`
      );
    } catch (err) {
      console.log(` ❌ Hata: ${err.message}`);
    }

    // Be polite to the API
    if (i < countries.length - 1) {
      await delay(500);
    }
  }

  console.log();
  console.log("═══════════════════════════════════════════");
  console.log(`📊 Toplam: ${stats.total} istasyon, ${stats.countries} ülke`);
  console.log(`🏷️  Genre bilgisi olan: ${stats.withGenre}`);
  console.log(`📍 Koordinatı olan: ${stats.withCoords}`);
  console.log("═══════════════════════════════════════════");

  // Remove duplicates by stream URL
  const uniqueMap = new Map();
  allStations.forEach((s) => {
    const key = s.url.toLowerCase();
    // Tür alanı bu aşamada henüz boş; etiketi olan kaydı tercih ediyoruz.
    if (!uniqueMap.has(key) || (uniqueMap.get(key)._meta.tags.length === 0 && s._meta.tags.length > 0)) {
      uniqueMap.set(key, s);
    }
  });
  const uniqueStations = [...uniqueMap.values()];
  console.log(`🔄 Tekrar edenler kaldırıldı: ${allStations.length} → ${uniqueStations.length}`);

  // Sort by country then by clickcount (desc)
  uniqueStations.sort((a, b) => {
    if (a.location < b.location) return -1;
    if (a.location > b.location) return 1;
    return (b._meta.clickcount || 0) - (a._meta.clickcount || 0);
  });

  // ── Tür etiketlerini toparla ──
  const tagStats = finalizeGenres(uniqueStations, config.minTagCount);
  const withGenre = uniqueStations.filter((s) => s.genre).length;
  console.log(
    `🏷️  Tür etiketleri: ${tagStats.surviving} tür kaldı, ${tagStats.discarded} elendi ` +
      `(${config.minTagCount} kezden az geçen + ${tagStats.brandLike} marka/yer adı)`
  );
  console.log(
    `    Türü olan istasyon: ${withGenre}/${uniqueStations.length} ` +
      `(%${Math.round((100 * withGenre) / uniqueStations.length)})`
  );

  // ── Write CSV (Radyola Google Sheets format) ──
  const csvData = toCSV(uniqueStations);
  const csvPath = path.join(outputDir, "stations.csv");
  fs.writeFileSync(csvPath, "\uFEFF" + csvData, "utf8"); // BOM for Excel compatibility
  console.log(`\n📄 CSV kaydedildi: ${csvPath}`);

  // ── Write full JSON (with all metadata) ──
  const jsonData = JSON.stringify(uniqueStations, null, 2);
  const jsonPath = path.join(outputDir, "stations.json");
  fs.writeFileSync(jsonPath, jsonData, "utf8");
  console.log(`📄 JSON kaydedildi: ${jsonPath}`);

  // ── Write published directory (data/directory.json) ──
  // Uygulamaların "Keşfet" modunda çektiği dosya. Ham _meta'nın tamamı değil,
  // yalnızca kalite sinyalleri taşınır: sıralama ve "bozukları gizle" için
  // gereken alanlar bunlar, gerisi dosyayı gereksiz şişiriyor.
  const directory = uniqueStations.map(({ _meta, ...rest }) => ({
    ...rest,
    votes: _meta.votes,
    bitrate: _meta.bitrate,
    codec: _meta.codec,
    hls: _meta.hls,
    lastCheckOk: _meta.lastcheckok,
  }));
  const directoryPath = path.join(dataDir, "directory.json");
  fs.writeFileSync(directoryPath, JSON.stringify(directory, null, 2) + "\n", "utf8");
  console.log(`📄 Keşfet dizini kaydedildi: ${directoryPath}`);

  // ── Write per-country files ──
  const byCountry = {};
  uniqueStations.forEach((s) => {
    const code = s._meta.countrycode;
    if (!byCountry[code]) byCountry[code] = [];
    byCountry[code].push(s);
  });

  const countriesDir = path.join(outputDir, "countries");
  if (!fs.existsSync(countriesDir)) {
    fs.mkdirSync(countriesDir, { recursive: true });
  }

  for (const [code, stations] of Object.entries(byCountry)) {
    const countryCSV = toCSV(stations);
    fs.writeFileSync(path.join(countriesDir, `${code}.csv`), "\uFEFF" + countryCSV, "utf8");
    fs.writeFileSync(
      path.join(countriesDir, `${code}.json`),
      JSON.stringify(stations, null, 2),
      "utf8"
    );
  }
  console.log(`📁 Ülke bazlı dosyalar: ${countriesDir}`);

  // ── Summary report ──
  console.log("\n╔══════════════════════════════════════════╗");
  console.log("║   ✅ Crawl tamamlandı!                    ║");
  console.log("╚══════════════════════════════════════════╝");
  console.log(
    "\nℹ️  data/stations.json (kuratörlü liste) değiştirilmedi — elle bakılır."
  );
  console.log("\nÜlke bazlı dağılım:");
  Object.entries(byCountry)
    .sort((a, b) => b[1].length - a[1].length)
    .forEach(([code, stations]) => {
      const name = countryName(code);
      const bar = "█".repeat(Math.ceil(stations.length / 20));
      console.log(`  ${code} ${name.padEnd(20)} ${String(stations.length).padStart(5)} ${bar}`);
    });
}

main().catch((err) => {
  console.error("\n❌ Fatal error:", err.message);
  process.exit(1);
});
