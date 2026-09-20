# Radyola

[![Android](https://github.com/aripdcom/radyola/actions/workflows/android.yml/badge.svg)](https://github.com/aripdcom/radyola/actions/workflows/android.yml)
[![Web](https://github.com/aripdcom/radyola/actions/workflows/web.yml/badge.svg)](https://github.com/aripdcom/radyola/actions/workflows/web.yml)
[![Linux](https://github.com/aripdcom/radyola/actions/workflows/linux.yml/badge.svg)](https://github.com/aripdcom/radyola/actions/workflows/linux.yml)
[![Windows](https://github.com/aripdcom/radyola/actions/workflows/windows.yml/badge.svg)](https://github.com/aripdcom/radyola/actions/workflows/windows.yml)
[![macOS](https://github.com/aripdcom/radyola/actions/workflows/macos.yml/badge.svg)](https://github.com/aripdcom/radyola/actions/workflows/macos.yml)
[![Yayın denetimi](https://github.com/aripdcom/radyola/actions/workflows/stream-check.yml/badge.svg)](https://github.com/aripdcom/radyola/actions/workflows/stream-check.yml)

Çoklu platform internet radyo çalar uygulaması.

## Platformlar

| Platform | Teknoloji | Ses Motoru | Tray/Menü |
|---|---|---|---|
| 🍎 macOS | Swift, SwiftUI | AVFoundation | MenuBarExtra |
| 🐧 Linux | Python, GTK4, Libadwaita | GStreamer | D-Bus StatusNotifierItem |
| 🪟 Windows | Python, pystray, Pillow | pygame (SDL2) | Win32 System Tray |
| 🤖 Android | Kotlin, Jetpack Compose | Media3 (ExoPlayer) | MediaSession bildirimi |
| 🌐 Web | Vanilla JS, Web Component | HTML5 Audio | — |

---

## 🍎 macOS

SwiftUI MenuBarExtra + AVFoundation tabanlı menü çubuğu radyo çalar.
Ortak JSON kaynağından dinamik istasyon listesi, ülke bazlı alt menüler, genre desteği,
media key entegrasyonu (MPRemoteCommandCenter) ve ayar yönetimi içerir.

- **Konum:** [`macosx/`](macosx/)
- **Gereksinim:** macOS 14.0+ (Sonoma), Xcode 15+

### Kurulum & Çalıştırma

```bash
# Xcode ile aç ve çalıştır
open macosx/Radyola.xcodeproj
# Xcode → Product → Run (⌘R)
```

### Kaldırma

Uygulamayı `/Applications` klasöründen çöp kutusuna sürükleyin.

---

## 🐧 Linux

GTK4 + Libadwaita + GStreamer tabanlı native radyo çalar.

- **Konum:** [`linux/`](linux/)
- **Gereksinim:** Debian 13+ (Trixie), Python 3.11+

### Gerekli Paketler

```bash
sudo apt install python3-gi python3-dbus gir1.2-gtk-4.0 gir1.2-adw-1 \
    gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly

# İsteğe bağlı: GNOME'da system tray ikonu için
sudo apt install gnome-shell-extension-appindicator
```

### Doğrudan Çalıştırma (Kurulum Gerekmez)

```bash
python3 linux/radyola.py
```

### DEB Paketi ile Kurulum

```bash
cd linux/
./build-deb.sh
# → radyola_1.0.0_all.deb oluşturulur

sudo apt install ./radyola_1.0.0_all.deb
```

> `apt install ./` kullanmak bağımlılıkları otomatik çözer (python3-gi, gstreamer vb.).

### Çalıştırma (Kurulum Sonrası)

```bash
radyola
# veya GNOME uygulama menüsünden "Radyola" arayın
```

### Kaldırma

```bash
sudo apt remove radyola
```

---

## 🪟 Windows

pystray + pygame tabanlı system tray radyo çalar.

- **Konum:** [`windows/`](windows/)
- **Gereksinim:** Windows 10+, Python 3.11+

### Gerekli Paketler

```cmd
pip install pystray Pillow pygame
```

### Doğrudan Çalıştırma (Kurulum Gerekmez)

```cmd
python windows\radyola.py
```

### EXE Oluşturma

```cmd
cd windows
build.bat
REM → dist\Radyola.exe oluşturulur
```

Veya manuel:

```cmd
pip install pyinstaller
pyinstaller --onefile --windowed --name Radyola --hidden-import=pystray._win32 radyola.py
```

### Çalıştırma (EXE)

```cmd
dist\Radyola.exe
REM Çift tıklayarak da çalıştırılabilir
```

### Kaldırma

`Radyola.exe` dosyasını silin. Ayar dosyasını da temizlemek için:

```cmd
rmdir /s /q "%APPDATA%\Radyola"
```

---

## 🤖 Android

Jetpack Compose + Media3 (ExoPlayer) tabanlı radyo çalar. Arka planda çalma,
bildirim ve kilit ekranı kontrolleri, favoriler ve uyku zamanlayıcı içerir.
Kuratörlü listenin yanında ~3.400 istasyonluk **Keşfet** dizininde arama yapar.

- **Konum:** [`android/`](android/)
- **Gereksinim:** Android 7.0+ (API 24), derleme için JDK 21 + Android SDK 37

### Hazır APK

Derlemek istemiyorsanız:

- **Yayınlanan sürümler** → [Releases](https://github.com/aripdcom/radyola/releases)
- **Her commit'in APK'sı** → [Actions → Android](https://github.com/aripdcom/radyola/actions/workflows/android.yml)
  → bir koşu seçin → sayfanın altındaki **Artifacts**

### Derleme

```bash
cd android
echo "sdk.dir=$HOME/Android/Sdk" > local.properties

./gradlew assembleDebug
# → app/build/outputs/apk/debug/app-debug.apk
```

Yayın (release) APK için:

```bash
./gradlew assembleRelease
# → app/build/outputs/apk/release/app-release.apk  (~3 MB)
```

### Cihaza Kurma

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Kablosuz hata ayıklama için önce `adb connect <IP>:<PORT>` çalıştırın.

### Kaldırma

```bash
adb uninstall com.aripd.radyola
```

---

## Sürekli Tümleştirme (CI/CD)

Depo GitLab'dan GitHub'a taşındı; boru hattı GitHub Actions üzerinde çalışıyor
([`.github/workflows/`](.github/workflows/)).

| İş akışı | Ne zaman | Ne yapar |
|---|---|---|
| [`android.yml`](.github/workflows/android.yml) | `android/` veya `data/` değiştiğinde | Birim testleri, debug + release APK → **Artifacts** (30 gün) |
| [`web.yml`](.github/workflows/web.yml) | `web/` veya `data/` değiştiğinde | Derleme her PR'da; `main`'de ayrıca GitHub Pages'e yayınlar |
| [`linux.yml`](.github/workflows/linux.yml) | `linux/` değiştiğinde | `.deb` paketini derler, Ubuntu'da kurulumunu dener → **Artifacts** |
| [`windows.yml`](.github/workflows/windows.yml) | `windows/` değiştiğinde | PyInstaller ile `Radyola.exe` → **Artifacts** |
| [`macos.yml`](.github/workflows/macos.yml) | `macosx/` değiştiğinde | `xcodebuild` ile imzasız `.app` (zip) → **Artifacts** |
| [`release.yml`](.github/workflows/release.yml) | `v*` etiketi itildiğinde | GitHub Release: APK + `.deb` + `.exe` + macOS `.zip`, SHA-256 özetleriyle |
| [`stream-check.yml`](.github/workflows/stream-check.yml) | Haftalık (Pzt 04:17 UTC) + elle | Kuratörlü listedeki akışları dener; ölü varsa issue açar |

### Yeni sürüm çıkarmak

```bash
git tag v1.1.0
git push origin v1.1.0
```

Ya da arayüzden: **Actions → Yayın → Run workflow** ve etiket adını yazın —
etiket henüz yoksa iş akışı onu da oluşturur.

Release'e dört platformun paketi eklenir: `radyola-1.1.0.apk`,
`radyola-1.1.0-linux-all.deb`, `radyola-1.1.0-windows.exe`,
`radyola-1.1.0-macos.zip` (macOS paketi imzasızdır; ilk açılışta
sağ tık → Aç gerekir).

### Depo ayarları (bir kez)

1. **Pages** — elle açmak gerekmez: ilk dağıtımda `web.yml` siteyi
   "GitHub Actions" kaynağıyla kendisi açar (`configure-pages` / `enablement`)
2. **Özel alan adı** — DNS `radyola.aripd.com` kaydı GitHub Pages'e yöneldikten
   sonra Settings → Secrets and variables → Actions → Variables:
   `PAGES_CUSTOM_DOMAIN = radyola.aripd.com`.
   Değişken tanımlı değilken site `https://aripdcom.github.io/radyola/`
   adresinde yayınlanır — DNS taşınmadan önce yayın kesilmesin diye.
3. **APK imzalama** (isteğe bağlı) — Settings → Secrets:
   `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`,
   `ANDROID_KEY_PASSWORD`. Tanımlı değilse APK debug anahtarıyla imzalanır;
   yan yüklenir ama her koşuda farklı bir imza üretir, yani kurulu uygulamanın
   üzerine yazılamaz. Ayrıntı: [`android/README.md`](android/README.md#imzalama).

---

## Radyo İstasyonları

Tüm platformlar aynı JSON kaynağından ([`data/`](data/)) dinamik istasyon listesi çeker:

🇹🇷 Açık Radyo · ITU Radio (Jazz/Blues, Classical, Rock) · TRT Haber · NTV Radyo · HABERTÜRK · Bozcaada · Gökçeada · Boğaziçi  
🇧🇪 MUSIQ3 · VRT Klara · Viva Brabant Wallon · Radio Panik  
🇬🇧 BBC Radio 1 · BBC World Service  
🇷🇺 Sputnik Türkiye  
🇬🇷 Μινόρε Καλλονής

## Lisans

MIT