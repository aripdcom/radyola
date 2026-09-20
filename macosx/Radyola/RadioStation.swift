import Foundation

// ──────────────────────────────────────────────
// Veri Modeli
// ──────────────────────────────────────────────

/// JSON URL — kanal listesi buradan çekilir
/// Kanal listesinin adresleri, denenme sırasıyla. Özel alan adı DNS
/// taşımalarında kesintiye düşebiliyor; GitHub Pages adresi her koşulda
/// çalışır (özel alan adı bağlanınca GitHub oraya yönlendirir).
let stationsJSONURLs = [
    "https://radyola.aripd.com/data/stations.json",
    "https://aripdcom.github.io/radyola/data/stations.json",
]

/// JSON decode için yardımcı struct
private struct StationJSON: Codable {
    let title: String
    let url: String
    let website: String?
    let location: String?
    let genre: String?
}

/// Ülke adından bayrak emoji'sine eşleme
private let countryFlags: [String: String] = [
    "türkiye": "🇹🇷", "turkey": "🇹🇷",
    "belgium": "🇧🇪",
    "united kingdom": "🇬🇧", "uk": "🇬🇧",
    "greece": "🇬🇷",
    "russia": "🇷🇺",
    "spain": "🇪🇸",
    "united states": "🇺🇸", "usa": "🇺🇸",
    "france": "🇫🇷",
    "germany": "🇩🇪",
    "netherlands": "🇳🇱",
    "italy": "🇮🇹",
    "japan": "🇯🇵",
    "portugal": "🇵🇹",
    "ireland": "🇮🇪",
    "canada": "🇨🇦",
    "australia": "🇦🇺",
    "austria": "🇦🇹",
    "switzerland": "🇨🇭",
    "sweden": "🇸🇪",
    "norway": "🇳🇴",
    "denmark": "🇩🇰",
    "finland": "🇫🇮",
    "poland": "🇵🇱",
    "czech republic": "🇨🇿",
    "hungary": "🇭🇺",
    "romania": "🇷🇴",
    "bulgaria": "🇧🇬",
    "croatia": "🇭🇷",
    "serbia": "🇷🇸",
    "brazil": "🇧🇷",
    "argentina": "🇦🇷",
    "mexico": "🇲🇽",
    "india": "🇮🇳",
    "china": "🇨🇳",
    "south korea": "🇰🇷",
]

/// Bir radyo istasyonunu temsil eder.
struct RadioStation: Identifiable, Equatable {
    let id: UUID
    let title: String
    let url: String
    let location: String
    let genre: String

    init(title: String, url: String, location: String = "", genre: String = "") {
        self.id = UUID()
        self.title = title
        self.url = url
        self.location = location
        self.genre = genre
    }

    /// Konum string'inden ülke bayrağı emoji'si çıkarır.
    var flag: String {
        guard !location.isEmpty else { return "📻" }
        let parts = location.split(separator: ",")
        let country = parts.last?.trimmingCharacters(in: .whitespaces).lowercased() ?? ""
        return countryFlags[country] ?? "📻"
    }

    /// Konum string'inden şehir adını çıkarır.
    var city: String {
        guard !location.isEmpty else { return "" }
        let parts = location.split(separator: ",")
        return parts.first.map { String($0).trimmingCharacters(in: .whitespaces) } ?? ""
    }

    /// Konum string'inden ülke adını çıkarır.
    var country: String {
        guard !location.isEmpty else { return "Diğer" }
        let parts = location.split(separator: ",")
        return parts.last.map { String($0).trimmingCharacters(in: .whitespaces) } ?? "Diğer"
    }

    /// Menü etiketi: "🇹🇷  Açık Radyo  [Eclectic]  (İstanbul)"
    var menuLabel: String {
        var label = "\(flag)  \(title)"
        if !genre.isEmpty { label += "  [\(genre)]" }
        if !city.isEmpty { label += "  (\(city))" }
        return label
    }

    static func == (lhs: RadioStation, rhs: RadioStation) -> Bool {
        lhs.title == rhs.title && lhs.url == rhs.url
    }
}

// ──────────────────────────────────────────────
// JSON Fetch
// ──────────────────────────────────────────────

/// JSON kaynağından kanal listesini çeker ve parse eder.
func fetchStations() async -> [RadioStation] {
    for urlString in stationsJSONURLs {
        guard let url = URL(string: urlString) else { continue }
        do {
            var request = URLRequest(url: url, timeoutInterval: 10)
            request.setValue("Radyola/1.0", forHTTPHeaderField: "User-Agent")
            let (data, response) = try await URLSession.shared.data(for: request)
            if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
                print("radyola: \(urlString) HTTP \(http.statusCode), sıradaki denenecek")
                continue
            }
            let items = try JSONDecoder().decode([StationJSON].self, from: data)
            let stations = items.compactMap { item -> RadioStation? in
                guard !item.title.isEmpty, !item.url.isEmpty else { return nil }
                return RadioStation(title: item.title, url: item.url, location: item.location ?? "", genre: item.genre ?? "")
            }
            if !stations.isEmpty { return stations }
        } catch {
            print("radyola: \(urlString) alınamadı (\(error)), sıradaki denenecek")
        }
    }
    print("radyola: hiçbir veri adresine ulaşılamadı — fallback kullanılıyor")
    return fallbackStations()
}

/// İnternet bağlantısı yoksa kullanılacak varsayılan istasyonlar.
func fallbackStations() -> [RadioStation] {
    [
        RadioStation(title: "Açık Radyo", url: "https://stream.34bit.net/ar.mp3",
                     location: "İstanbul, Türkiye", genre: "Eclectic"),
        RadioStation(title: "VRT Klara", url: "http://icecast-servers.vrtcdn.be/klara-high.mp3",
                     location: "Brussels, Belgium", genre: "Classical"),
        RadioStation(title: "BBC Radio 1", url: "http://lsn.lv/bbcradio.m3u8?station=bbc_radio_one&bitrate=96000",
                     location: "London, United Kingdom", genre: "Pop / Dance"),
        RadioStation(title: "Radio Panik", url: "https://streaming.domainepublic.net/radiopanik.mp3",
                     location: "Brussels, Belgium", genre: "Alternative"),
    ]
}

/// İstasyonları ülkeye göre gruplar. Sıralama: orijinal JSON sırası korunur.
func groupStationsByCountry(_ stations: [RadioStation]) -> [(country: String, stations: [RadioStation])] {
    var groups: [(String, [RadioStation])] = []
    var seen: [String: Int] = [:]

    for station in stations {
        let country = station.country
        if let idx = seen[country] {
            groups[idx].1.append(station)
        } else {
            seen[country] = groups.count
            groups.append((country, [station]))
        }
    }
    return groups
}
