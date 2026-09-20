#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radyola — Windows Native İnternet Radyo Çalar

Linux Radyola uygulamasının Windows native karşılığı.
System tray (pystray) + pygame (SDL2_mixer) tabanlı.

Gereksinimler:
    - Python 3.11+
    - pip install pystray Pillow pygame

Kullanım:
    python radyola.py

Lisans: MIT
"""

import sys
import os

import json
import logging
import threading
import time
import tempfile
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

try:
    import pygame
except ImportError:
    print("HATA: pygame kurulu değil. Çalıştırın: pip install pygame")
    sys.exit(1)

try:
    import pystray
    from pystray import MenuItem, Menu
except ImportError:
    print("HATA: pystray kurulu değil. Çalıştırın: pip install pystray")
    sys.exit(1)

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("HATA: Pillow kurulu değil. Çalıştırın: pip install Pillow")
    sys.exit(1)

log = logging.getLogger("radyola")
logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")


# ──────────────────────────────────────────────
# Veri Modeli
# ──────────────────────────────────────────────

# Adresler denenme sırasıyla: özel alan adı DNS taşımalarında kesintiye
# düşebiliyor; GitHub Pages adresi her koşulda çalışır.
STATIONS_JSON_URLS = [
    "https://radyola.aripd.com/data/stations.json",
    "https://aripdcom.github.io/radyola/data/stations.json",
]

_COUNTRY_FLAGS = {
    "türkiye": "TR", "turkey": "TR", "belgium": "BE",
    "united kingdom": "GB", "uk": "GB", "greece": "GR",
    "russia": "RU", "spain": "ES", "united states": "US",
    "usa": "US", "france": "FR", "germany": "DE",
    "netherlands": "NL", "italy": "IT", "japan": "JP",
    "portugal": "PT", "ireland": "IE", "canada": "CA",
    "australia": "AU", "austria": "AT", "switzerland": "CH",
    "sweden": "SE", "norway": "NO", "denmark": "DK",
    "finland": "FI", "poland": "PL", "czech republic": "CZ",
    "hungary": "HU", "romania": "RO", "bulgaria": "BG",
    "croatia": "HR", "serbia": "RS", "brazil": "BR",
    "argentina": "AR", "mexico": "MX", "india": "IN",
    "china": "CN", "south korea": "KR",
}


@dataclass
class RadioStation:
    """Bir radyo istasyonunu temsil eder."""
    title: str
    url: str
    location: str = ""
    genre: str = ""

    @property
    def country_code(self) -> str:
        if not self.location:
            return ""
        parts = self.location.split(",")
        country_part = parts[-1].strip().lower() if parts else ""
        return _COUNTRY_FLAGS.get(country_part, "")

    @property
    def country(self) -> str:
        if not self.location:
            return "Diğer"
        parts = self.location.split(",")
        return parts[-1].strip() if parts else "Diğer"

    @property
    def city(self) -> str:
        if not self.location:
            return ""
        parts = self.location.split(",")
        return parts[0].strip() if parts else ""


def _fetch_stations_from_json() -> list[RadioStation]:
    """Ortak JSON kaynağından kanal listesini çeker."""
    try:
        raw = None
        for source_url in STATIONS_JSON_URLS:
            try:
                req = urllib.request.Request(
                    source_url, headers={"User-Agent": "Radyola/1.0"},
                )
                with urllib.request.urlopen(req, timeout=15) as response:
                    raw = response.read().decode("utf-8")
                break
            except Exception as exc:
                log.warning(f"{source_url} alınamadı ({exc}), sıradaki denenecek")
        if raw is None:
            raise RuntimeError("hiçbir veri adresine ulaşılamadı")

        data = json.loads(raw)
        stations = []
        for item in data:
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            location = (item.get("location") or "").strip()
            genre = (item.get("genre") or "").strip()
            if not title or not url:
                continue
            stations.append(RadioStation(title=title, url=url, location=location, genre=genre))

        if stations:
            log.info(f"JSON'dan {len(stations)} istasyon yüklendi")
            return stations
        log.warning("JSON'dan istasyon alınamadı — fallback")
        return _fallback_stations()
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as e:
        log.warning(f"JSON verisi alınamadı ({e}) — fallback")
        return _fallback_stations()


def _fallback_stations() -> list[RadioStation]:
    return [
        RadioStation("Açık Radyo", "https://stream.34bit.net/ar.mp3", "İstanbul, Türkiye", "Eclectic"),
        RadioStation("VRT Klara", "http://icecast-servers.vrtcdn.be/klara-high.mp3", "Brussels, Belgium", "Classical"),
        RadioStation("Radio Panik", "https://streaming.domainepublic.net/radiopanik.mp3", "Brussels, Belgium", "Alternative"),
    ]


STATIONS: list[RadioStation] = _fetch_stations_from_json()


# ──────────────────────────────────────────────
# Ayarlar
# ──────────────────────────────────────────────

_CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Radyola"
_CONFIG_FILE = _CONFIG_DIR / "settings.json"

_DEFAULT_SETTINGS = {
    "autoplay_on_start": False,
    "remember_station": True,
    "last_station": "",
    "volume": 100,
}


def load_settings() -> dict:
    try:
        if _CONFIG_FILE.exists():
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            return {**_DEFAULT_SETTINGS, **saved}
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"Ayar dosyası okunamadı: {e}")
    return dict(_DEFAULT_SETTINGS)


def save_settings(settings: dict) -> None:
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except OSError as e:
        log.warning(f"Ayar dosyası yazılamadı: {e}")


APP_SETTINGS = load_settings()


def _get_country_groups():
    from collections import OrderedDict
    groups = OrderedDict()
    for i, station in enumerate(STATIONS):
        country = station.country
        if country not in groups:
            groups[country] = []
        groups[country].append((i, station))
    return groups


# ──────────────────────────────────────────────
# Pygame Stream Oynatıcı
# ──────────────────────────────────────────────

# İlk buffer boyutu (stream başlamadan önce indirilecek miktar)
_INITIAL_BUFFER_BYTES = 131072  # 128KB (~8 saniye 128kbps MP3)


class PygameStreamPlayer:
    """Pygame (SDL2_mixer) tabanlı internet radyo akışı oynatıcı.

    HTTP stream'i arka plan thread'inde geçici dosyaya yazar,
    pygame.mixer.music ile dosyayı çalar. SDL2_mixer dosyayı
    ilerleyici (progressive) olarak okur — tüm dosyanın inmesini beklemez.
    """

    def __init__(self):
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
        self._current_station: Optional[RadioStation] = None
        self._stop_event = threading.Event()
        self._download_thread: Optional[threading.Thread] = None
        self._temp_path: Optional[str] = None
        self._paused = False
        self._volume_percent = APP_SETTINGS.get("volume", 100)
        pygame.mixer.music.set_volume(self._volume_percent / 100.0)

    def play(self, station: RadioStation) -> None:
        """Belirtilen istasyonu çalmaya başlar."""
        if self._current_station == station and self.is_playing:
            return
        self.stop()
        self._current_station = station
        self._stop_event.clear()
        self._paused = False

        # Geçici dosya oluştur
        fd, self._temp_path = tempfile.mkstemp(suffix=".mp3", prefix="radyola_")
        os.close(fd)

        # İndirme thread'ini başlat
        self._download_thread = threading.Thread(
            target=self._download_worker,
            args=(station.url, self._temp_path),
            daemon=True,
        )
        self._download_thread.start()

    def _download_worker(self, url: str, path: str) -> None:
        """Arka planda stream verisini dosyaya yazar ve çalmayı başlatır."""
        started_playback = False
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Radyola/1.0",
                "Icy-MetaData": "0",
            })
            response = urllib.request.urlopen(req, timeout=15)

            total_written = 0
            with open(path, "wb") as f:
                while not self._stop_event.is_set():
                    data = response.read(8192)
                    if not data:
                        break
                    f.write(data)
                    f.flush()
                    total_written += len(data)

                    # İlk buffer dolduğunda çalmayı başlat
                    if not started_playback and total_written >= _INITIAL_BUFFER_BYTES:
                        try:
                            pygame.mixer.music.load(path)
                            pygame.mixer.music.play()
                            started_playback = True
                            log.info(f"Çalınıyor: {self._current_station.title if self._current_station else '?'}")
                        except Exception as e:
                            log.error(f"Çalma hatası: {e}")
                            return
        except Exception as e:
            if not self._stop_event.is_set():
                log.error(f"Stream hatası: {e}")

    def pause(self) -> None:
        if self._current_station:
            pygame.mixer.music.pause()
            self._paused = True

    def resume(self) -> None:
        if self._current_station:
            pygame.mixer.music.unpause()
            self._paused = False

    def stop(self) -> None:
        self._stop_event.set()
        try:
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
        except Exception:
            pass
        # İndirme thread'inin bitmesini bekle
        if self._download_thread and self._download_thread.is_alive():
            self._download_thread.join(timeout=2)
        self._download_thread = None
        # Geçici dosyayı sil
        if self._temp_path:
            try:
                os.unlink(self._temp_path)
            except OSError:
                pass
            self._temp_path = None
        self._current_station = None
        self._paused = False

    def toggle(self, station: RadioStation) -> None:
        if self._current_station and self._current_station.title == station.title:
            if self.is_playing:
                self.pause()
            else:
                self.resume()
        else:
            self.play(station)

    def set_volume(self, percent: int) -> None:
        self._volume_percent = max(0, min(100, percent))
        pygame.mixer.music.set_volume(self._volume_percent / 100.0)
        APP_SETTINGS["volume"] = self._volume_percent
        save_settings(APP_SETTINGS)

    @property
    def volume(self) -> int:
        return self._volume_percent

    @property
    def is_playing(self) -> bool:
        return pygame.mixer.music.get_busy() and not self._paused

    @property
    def is_paused(self) -> bool:
        return self._paused and self._current_station is not None

    @property
    def current_station(self) -> Optional[RadioStation]:
        return self._current_station

    @property
    def state(self) -> str:
        if self.is_playing:
            return "playing"
        if self.is_paused:
            return "paused"
        return "stopped"

    def cleanup(self):
        self.stop()
        pygame.mixer.quit()


# ──────────────────────────────────────────────
# Tray İkon Oluşturucu
# ──────────────────────────────────────────────


def _create_tray_icon(state: str = "stopped") -> Image.Image:
    """Duruma göre tray ikonu oluşturur (PIL ile)."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if state == "playing":
        draw.ellipse([4, 4, size - 4, size - 4], fill=(76, 175, 80, 255))
        draw.polygon([(24, 16), (24, 48), (48, 32)], fill=(255, 255, 255, 255))
    elif state == "paused":
        draw.ellipse([4, 4, size - 4, size - 4], fill=(255, 152, 0, 255))
        draw.rectangle([20, 16, 28, 48], fill=(255, 255, 255, 255))
        draw.rectangle([36, 16, 44, 48], fill=(255, 255, 255, 255))
    else:
        draw.ellipse([4, 4, size - 4, size - 4], fill=(158, 158, 158, 255))
        draw.arc([12, 12, size - 12, size - 12], 210, 330, fill=(255, 255, 255, 255), width=3)
        draw.arc([20, 20, size - 20, size - 20], 210, 330, fill=(255, 255, 255, 255), width=3)
        draw.ellipse([28, 28, 36, 36], fill=(255, 255, 255, 255))

    return img


# ──────────────────────────────────────────────
# System Tray Uygulaması
# ──────────────────────────────────────────────


class RadyolaApp:
    """Radyola — System tray internet radyo uygulaması (Windows)."""

    def __init__(self):
        self._player = PygameStreamPlayer()
        self._tray: Optional[pystray.Icon] = None

    def run(self) -> None:
        self._apply_startup_settings()
        self._tray = pystray.Icon(
            "radyola",
            icon=_create_tray_icon("stopped"),
            title="Radyola — İnternet Radyo",
            menu=self._build_menu(),
        )
        log.info("Radyola tray-only modda başlatıldı (Windows)")
        self._tray.run()

    def _build_menu(self) -> Menu:
        country_groups = _get_country_groups()
        menu_items = []
        current = self._player.current_station

        # Başlık
        if current:
            state_icon = "||" if self._player.is_paused else ">>"
            header = f"{state_icon} {current.title}"
        else:
            header = "Radyola"
        menu_items.append(MenuItem(header, None, enabled=False))
        menu_items.append(Menu.SEPARATOR)

        # Ülke alt menüleri
        for country_name, station_items in country_groups.items():
            code = station_items[0][1].country_code if station_items else ""
            active_in_group = any(
                current and current.title == s.title for _, s in station_items
            )
            if active_in_group:
                country_label = f"[{code}] {country_name} *"
            else:
                country_label = f"[{code}] {country_name} ({len(station_items)})"

            sub_items = []
            for station_idx, station in station_items:
                prefix = "> " if current and current.title == station.title else "  "
                label = f"{prefix}{station.title}"
                if station.genre:
                    label += f" [{station.genre}]"
                if station.city:
                    label += f" ({station.city})"
                sub_items.append(MenuItem(label, self._make_station_cb(station)))
            menu_items.append(MenuItem(country_label, Menu(*sub_items)))

        menu_items.append(Menu.SEPARATOR)

        # Oynatma kontrolleri
        if self._player.is_playing:
            pp_label = "Duraklat"
        elif self._player.is_paused:
            pp_label = "Devam"
        else:
            pp_label = "Cal"
        menu_items.append(MenuItem(pp_label, self._on_play_pause, enabled=bool(current)))
        menu_items.append(MenuItem("Durdur", self._on_stop, enabled=bool(current)))

        # Ses seviyesi
        current_vol = self._player.volume
        vol_items = []
        for label, pct in [("Sessiz", 0), ("%25", 25), ("%50", 50), ("%75", 75), ("%100", 100)]:
            mark = ">" if current_vol == pct else " "
            vol_items.append(MenuItem(f"{mark} {label}", self._make_vol_cb(pct)))
        menu_items.append(MenuItem(f"Ses: %{current_vol}", Menu(*vol_items)))

        menu_items.append(Menu.SEPARATOR)

        # Ayarlar
        ap = APP_SETTINGS.get("autoplay_on_start", False)
        rm = APP_SETTINGS.get("remember_station", True)
        settings_items = [
            MenuItem(f"{'[x]' if ap else '[ ]'} Otomatik cal", self._toggle_autoplay),
            MenuItem(f"{'[x]' if rm else '[ ]'} Son istasyonu hatirla", self._toggle_remember),
        ]
        menu_items.append(MenuItem("Ayarlar", Menu(*settings_items)))
        menu_items.append(MenuItem("Cikis", self._on_quit))

        return Menu(*menu_items)

    # Callback fabrikaları
    def _make_station_cb(self, station):
        def cb(icon, item):
            self._player.toggle(station)
            self._save_last_station()
            self._update_tray()
        return cb

    def _make_vol_cb(self, percent):
        def cb(icon, item):
            self._player.set_volume(percent)
            self._update_tray()
        return cb

    # Aksiyonlar
    def _on_play_pause(self, icon, item):
        if self._player.is_playing:
            self._player.pause()
        elif self._player.current_station:
            self._player.resume()
        self._update_tray()

    def _on_stop(self, icon, item):
        self._player.stop()
        self._update_tray()

    def _toggle_autoplay(self, icon, item):
        APP_SETTINGS["autoplay_on_start"] = not APP_SETTINGS.get("autoplay_on_start", False)
        save_settings(APP_SETTINGS)
        self._update_tray()

    def _toggle_remember(self, icon, item):
        APP_SETTINGS["remember_station"] = not APP_SETTINGS.get("remember_station", True)
        save_settings(APP_SETTINGS)
        self._update_tray()

    def _on_quit(self, icon, item):
        self._save_last_station()
        self._player.cleanup()
        icon.stop()

    # Yardımcılar
    def _save_last_station(self):
        if self._player.current_station and APP_SETTINGS.get("remember_station", True):
            APP_SETTINGS["last_station"] = self._player.current_station.title
            save_settings(APP_SETTINGS)

    def _update_tray(self):
        if self._tray:
            self._tray.icon = _create_tray_icon(self._player.state)
            current = self._player.current_station
            self._tray.title = f"Radyola — {current.title}" if current else "Radyola"
            self._tray.menu = self._build_menu()

    def _apply_startup_settings(self):
        last_name = APP_SETTINGS.get("last_station", "")
        if last_name and APP_SETTINGS.get("remember_station", True):
            for s in STATIONS:
                if s.title == last_name:
                    if APP_SETTINGS.get("autoplay_on_start", False):
                        self._player.play(s)
                        log.info(f"Otomatik çalma: {s.title}")
                    break


# ──────────────────────────────────────────────
# Giriş Noktası
# ──────────────────────────────────────────────

def main() -> int:
    app = RadyolaApp()
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
