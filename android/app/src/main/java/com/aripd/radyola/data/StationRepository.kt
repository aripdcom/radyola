package com.aripd.radyola.data

import android.content.Context
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * Uzaktan çekilen listeler. Şemaları aynı, rolleri değil.
 *
 * Kullanıcının kendi listesi burada yok — o yereldir, [UserListStore] tutar.
 */
enum class StationSource(val urls: List<String>, internal val cacheName: String) {
    /** Kuratörlü liste. Yalnız ilk açılış tohumu ve "yeni kanallara bak" için. */
    CURATED(dataUrls("stations.json"), "stations.json"),

    /** radio-browser'dan derlenen ~3.400 istasyon. Keşfet modunda çekilir. */
    DIRECTORY(dataUrls("directory.json"), "directory.json")
}

/**
 * Veri dosyasının adresleri, denenme sırasıyla.
 *
 * Özel alan adı DNS taşımalarında kesintiye düşebiliyor (GitLab → GitHub
 * geçişinde düştü ve uygulama gömülü yedeğe kaldı). GitHub Pages adresi bu
 * yüzden her kaynağın yedeği: site oradan yayınlanıyor ve özel alan adı
 * bağlandığında GitHub onu yönlendiriyor — yani bu adres hiçbir
 * yapılandırmada ölmüyor.
 */
private fun dataUrls(file: String) = listOf(
    "https://radyola.aripd.com/data/$file",
    "https://aripdcom.github.io/radyola/data/$file"
)

/** Ekranda gösterilen liste. */
enum class ListMode {
    /** Kullanıcının kendi listesi — tohumdan başlar, sonra ona aittir. */
    MY_LIST,

    /** Keşfet dizini. */
    DISCOVER
}

/**
 * İstasyon listelerini ortak JSON kaynağından çeker, diske önbelleğe alır.
 *
 * Kaynak tüm platformlarda (macOS / Linux / Windows / web) ortaktır;
 * şema `data/README.md` içinde tanımlı.
 */
class StationRepository(context: Context) {

    private val filesDir = context.filesDir

    /**
     * İstenen listeyi döndürür.
     *
     * Sıra: ağ → disk önbelleği → gömülü varsayılanlar. Ağdan başarılı çekim
     * önbelleği tazeler; böylece uçak modunda da son bilinen liste açılır.
     * Gömülü yedek yalnız kuratörlü liste için anlamlı — Keşfet'te boş dönülür.
     */
    suspend fun load(source: StationSource): List<RadioStation> = withContext(Dispatchers.IO) {
        fetchWithRetry(source)?.also { writeCache(source, it) }
            ?: readCache(source)
            ?: if (source == StationSource.CURATED) FALLBACK_STATIONS else emptyList()
    }

    /** Yalnızca diskteki önbelleği okur — açılışta anında liste göstermek için. */
    suspend fun cached(source: StationSource): List<RadioStation>? = withContext(Dispatchers.IO) {
        readCache(source)
    }

    /**
     * Ağ denemesini kısa bir beklemeyle bir kez tekrarlar.
     *
     * Telefon uykudan yeni uyandığında Wi-Fi birkaç saniye hazır olmuyor; tek
     * denemede yedek listeye düşmek yerine bir şans daha veriyoruz.
     */
    private suspend fun fetchWithRetry(source: StationSource): List<RadioStation>? {
        fetchFirstReachable(source)?.let { return it }
        delay(RETRY_DELAY_MS)
        return fetchFirstReachable(source)
    }

    /** Kaynağın adreslerini sırayla dener; ilk başarılı yanıt kazanır. */
    private fun fetchFirstReachable(source: StationSource): List<RadioStation>? =
        source.urls.firstNotNullOfOrNull { url -> fetchFromNetwork(source, url) }

    private fun fetchFromNetwork(source: StationSource, url: String): List<RadioStation>? {
        return try {
            val connection = (URL(url).openConnection() as HttpURLConnection).apply {
                connectTimeout = 10_000
                readTimeout = 20_000
                instanceFollowRedirects = true
                setRequestProperty("User-Agent", "Radyola-Android/1.0")
                setRequestProperty("Accept", "application/json")
                setRequestProperty("Accept-Encoding", "gzip")
            }
            val body = try {
                if (connection.responseCode != HttpURLConnection.HTTP_OK) {
                    Log.w(TAG, "${source.name}: beklenmeyen yanıt HTTP ${connection.responseCode}")
                    return null
                }
                val stream = if (connection.contentEncoding.equals("gzip", ignoreCase = true)) {
                    java.util.zip.GZIPInputStream(connection.inputStream)
                } else {
                    connection.inputStream
                }
                stream.bufferedReader().use { it.readText() }
            } finally {
                connection.disconnect()
            }
            parseStations(body).takeIf { it.isNotEmpty() }
        } catch (e: Exception) {
            Log.w(TAG, "${source.name}: liste çekilemedi, önbelleğe düşülüyor", e)
            null
        }
    }

    private fun readCache(source: StationSource): List<RadioStation>? = try {
        val file = File(filesDir, source.cacheName)
        if (!file.exists()) null
        else parseStations(file.readText()).takeIf { it.isNotEmpty() }
    } catch (e: Exception) {
        Log.w(TAG, "${source.name}: önbellek okunamadı", e)
        null
    }

    /**
     * Önbelleği kaynakla aynı şemada yazar — böylece [readCache] ile
     * [fetchFromNetwork] aynı ayrıştırıcıyı paylaşır.
     */
    private fun writeCache(source: StationSource, stations: List<RadioStation>) {
        try {
            val array = JSONArray()
            stations.forEach { station ->
                array.put(
                    JSONObject()
                        .put(FIELD_TITLE, station.name)
                        .put(FIELD_URL, station.url)
                        .put(FIELD_WEBSITE, station.website)
                        .put(FIELD_LOCATION, station.location)
                        .put(FIELD_COUNTRY_CODE, station.countryCode)
                        .put(FIELD_GENRE, station.genre)
                        .put(FIELD_VOTES, station.votes)
                )
            }
            File(filesDir, source.cacheName).writeText(array.toString())
        } catch (e: Exception) {
            Log.w(TAG, "${source.name}: önbellek yazılamadı", e)
        }
    }

    private companion object {
        const val TAG = "StationRepository"
        const val RETRY_DELAY_MS = 1_500L
    }
}

private const val FIELD_TITLE = "title"
private const val FIELD_URL = "url"
private const val FIELD_WEBSITE = "website"
private const val FIELD_LOCATION = "location"
private const val FIELD_COUNTRY_CODE = "countryCode"
private const val FIELD_GENRE = "genre"
private const val FIELD_VOTES = "votes"

/**
 * JSON dizisini istasyon listesine çevirir.
 *
 * Adı veya çalınabilir bir adresi olmayan kayıtlar atlanır — tek bozuk kayıt
 * yüzünden listenin tamamını kaybetmemek için ayrıştırma kayıt bazında toleranslı.
 */
internal fun parseStations(json: String): List<RadioStation> {
    val array = JSONArray(json)
    val stations = ArrayList<RadioStation>(array.length())
    for (i in 0 until array.length()) {
        val item = array.optJSONObject(i) ?: continue
        val name = item.optString(FIELD_TITLE).trim()
        val url = item.optString(FIELD_URL).trim()
        if (name.isEmpty() || !url.startsWith("http")) continue
        stations.add(
            RadioStation(
                name = name,
                url = url,
                website = item.optString(FIELD_WEBSITE).trim(),
                location = item.optString(FIELD_LOCATION).trim(),
                countryCode = item.optString(FIELD_COUNTRY_CODE).trim(),
                genre = item.optString(FIELD_GENRE).trim(),
                votes = item.optInt(FIELD_VOTES, 0)
            )
        )
    }
    return stations
}
