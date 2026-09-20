# Radyola — Windows Native İnternet Radyo Çalar

**Radyola**, Linux [Radyola](../linux/) uygulamasının Windows native karşılığıdır. System tray (pystray) + pygame (SDL2_mixer) tabanlı bir internet radyo çalar uygulamasıdır. Harici yazılım kurulumu gerektirmez.

## Hazır EXE

Derlemek istemiyorsanız: her değişiklikte CI EXE'yi derler —
[Actions → Windows](https://github.com/aripdcom/radyola/actions/workflows/windows.yml)
→ bir koşu seçin → **Artifacts**. Sürüm etiketlerinde EXE,
[Releases](https://github.com/aripdcom/radyola/releases) sayfasına da eklenir.

## Özellikler

- **Dinamik istasyon listesi** (tüm platformlarla ortak JSON kaynağı)
- **Play/Pause/Stop** kontrolleri
- **System Tray** — pystray ile native Windows tray ikonu
- **Ses Seviyesi** — 5 kademeli (0%, 25%, 50%, 75%, 100%)
- **Ülke bazlı alt menüler** — istasyonlar ülkeye göre gruplanır
- **Ayar yönetimi** — `%APPDATA%/Radyola/settings.json`
- **Tek dosya** mimarisi
- **Dinamik tray ikonu** — duruma göre yeşil/turuncu/gri

## Gereksinimler

```bash
pip install pystray Pillow pygame
```

| Paket | Açıklama |
|---|---|
| `pystray` | Windows system tray ikonu ve menüsü |
| `Pillow` | Tray ikonu oluşturma (PIL) |
| `pygame` | Ses çalma (SDL2_mixer, harici yazılım gerektirmez) |

## Kullanım

```bash
python radyola.py
```

## Linux Versiyonuyla Karşılaştırma

| Özellik | Linux | Windows |
|---|---|---|
| **Tray** | D-Bus StatusNotifierItem | pystray (Win32) |
| **Ses** | GStreamer (playbin) | pygame (SDL2_mixer) |
| **Media Tuşları** | MPRIS D-Bus | — |
| **Ayar Dizini** | `~/.config/radyola/` | `%APPDATA%/Radyola/` |
| **İstasyon Kaynağı** | Ortak JSON | Ortak JSON (aynı) |

## Lisans

MIT
