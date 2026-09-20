#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radyola — Linux Native Internet Radyo Çalar

macOS Radyola uygulamasının GTK4/Libadwaita/GStreamer tabanlı
Linux native karşılığı. Debian 13 (Trixie) için optimize edilmiştir.

Gereksinimler:
    - Python 3.11+
    - GTK 4, Libadwaita 1, GStreamer 1.0
    - python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1
    - gir1.2-gstreamer-1.0, gir1.2-gst-plugins-base-1.0

Kullanım:
    python3 radyola.py

Lisans: MIT
"""

import sys
import os
import json
import logging
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gst", "1.0")

from gi.repository import Gtk, Adw, Gst, GLib, Gio  # noqa: E402

# D-Bus (MPRIS + System Tray) — opsiyonel, yoksa sessizce devre dışı kalır
try:
    import dbus
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop

    HAS_DBUS = True
except ImportError:
    HAS_DBUS = False

log = logging.getLogger("radyola")


# ──────────────────────────────────────────────
# Veri Modeli
# ──────────────────────────────────────────────

# Kanal listesinin adresleri, denenme sırasıyla. Özel alan adı DNS
# taşımalarında kesintiye düşebiliyor; GitHub Pages adresi her koşulda
# çalışır (özel alan adı bağlanınca GitHub oraya yönlendirir).
STATIONS_JSON_URLS = [
    "https://radyola.aripd.com/data/stations.json",
    "https://aripdcom.github.io/radyola/data/stations.json",
]

# Ülke adından bayrak emoji'sine eşleme
_COUNTRY_FLAGS = {
    "türkiye": "🇹🇷",
    "turkey": "🇹🇷",
    "belgium": "🇧🇪",
    "united kingdom": "🇬🇧",
    "uk": "🇬🇧",
    "greece": "🇬🇷",
    "russia": "🇷🇺",
    "spain": "🇪🇸",
    "united states": "🇺🇸",
    "usa": "🇺🇸",
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
}


@dataclass
class RadioStation:
    """Bir radyo istasyonunu temsil eder.

    JSON alanları: date, title, url, website, location, genre
    """

    title: str
    url: str
    location: str = ""  # "İstanbul, Türkiye" formatında
    genre: str = ""     # "Jazz / Blues", "News", "Classical" vb.

    @property
    def flag(self) -> str:
        """Konum string'inden ülke bayrağı emoji'si çıkarır."""
        if not self.location:
            return "📻"
        # "İstanbul, Türkiye" → "Türkiye"
        parts = self.location.split(",")
        country_part = parts[-1].strip().lower() if parts else ""
        return _COUNTRY_FLAGS.get(country_part, "📻")

    @property
    def city(self) -> str:
        """Konum string'inden şehir adını çıkarır."""
        if not self.location:
            return ""
        parts = self.location.split(",")
        return parts[0].strip() if parts else ""


def _fetch_stations_from_json() -> list[RadioStation]:
    """JSON dosyasından kanal listesini çeker ve parse eder.

    JSON formatı: [{"date": ..., "title": ..., "url": ..., "website": ..., "location": ..., "genre": ...}, ...]
    """
    try:
        raw = None
        for source_url in STATIONS_JSON_URLS:
            try:
                req = urllib.request.Request(
                    source_url,
                    headers={"User-Agent": "Radyola/1.0"},
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    raw = response.read().decode("utf-8")
                break
            except Exception as exc:
                print(f"radyola: {source_url} alınamadı ({exc}), sıradaki denenecek")
        if raw is None:
            raise RuntimeError("hiçbir veri adresine ulaşılamadı")

        data = json.loads(raw)
        stations = []
        for item in data:
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            location = item.get("location", "")
            genre = item.get("genre", "")

            if not title or not url:
                continue

            stations.append(RadioStation(title=title, url=url, location=location, genre=genre))

        if stations:
            log.info(f"JSON'dan {len(stations)} istasyon yüklendi")
            return stations
        else:
            log.warning("JSON'dan istasyon alınamadı — fallback kullanılıyor")
            return _fallback_stations()

    except (urllib.error.URLError, OSError, ValueError) as e:
        log.warning(f"JSON kaynağına bağlanılamadı ({e}) — fallback kullanılıyor")
        return _fallback_stations()


def _fallback_stations() -> list[RadioStation]:
    """İnternet bağlantısı yoksa kullanılacak varsayılan istasyonlar."""
    return [
        RadioStation("Açık Radyo", "https://stream.34bit.net/ar.mp3", "İstanbul, Türkiye", "Eclectic"),
        RadioStation("VRT Klara", "http://icecast-servers.vrtcdn.be/klara-high.mp3", "Brussels, Belgium", "Classical"),
        RadioStation("BBC Radio 1", "http://open.live.bbc.co.uk/mediaselector/5/select/version/2.0/mediaset/http-icy-mp3-a/vpid/bbc_radio_one/format/pls.pls", "London, United Kingdom", "Pop / Dance"),
        RadioStation("Radio Panik", "https://streaming.domainepublic.net/radiopanik.mp3", "Brussels, Belgium", "Alternative"),
    ]


# Uygulama başlangıcında istasyonları yükle
STATIONS: list[RadioStation] = _fetch_stations_from_json()


# ──────────────────────────────────────────────
# Ayarlar (Settings) Yönetimi
# ──────────────────────────────────────────────

_CONFIG_DIR = Path.home() / ".config" / "radyola"
_CONFIG_FILE = _CONFIG_DIR / "settings.json"

_DEFAULT_SETTINGS = {
    "autoplay_on_start": False,  # Başlangıçta son istasyonu otomatik çal
    "remember_station": True,    # Son çalınan istasyonu hatırla
    "last_station": "",          # Son çalınan istasyonun adı
    "volume": 100,               # Ses seviyesi (0-100)
}


def load_settings() -> dict:
    """Ayarları JSON dosyasından yükler. Dosya yoksa varsayılanları döndürür."""
    try:
        if _CONFIG_FILE.exists():
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            # Eksik anahtarları varsayılanlarla tamamla
            merged = {**_DEFAULT_SETTINGS, **saved}
            return merged
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"Ayar dosyası okunamadı: {e}")
    return dict(_DEFAULT_SETTINGS)


def save_settings(settings: dict) -> None:
    """Ayarları JSON dosyasına kaydeder."""
    try:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except OSError as e:
        log.warning(f"Ayar dosyası yazılamadı: {e}")


# Global ayarlar — uygulama başlangıcında yüklenir
APP_SETTINGS = load_settings()


def _get_country_groups():
    """İstasyonları ülkeye göre gruplar. Sıralama: orijinal JSON sırası korunur.

    Dönüş: OrderedDict { ülke_adı: [(index, RadioStation), ...] }
    """
    from collections import OrderedDict
    groups = OrderedDict()
    for i, station in enumerate(STATIONS):
        if station.location:
            parts = station.location.split(",")
            country = parts[-1].strip()
        else:
            country = "Diğer"
        if country not in groups:
            groups[country] = []
        groups[country].append((i, station))
    return groups


# ──────────────────────────────────────────────
# GStreamer Ses Oynatıcı
# ──────────────────────────────────────────────


class GStreamerPlayer:
    """GStreamer playbin tabanlı internet radyo akışı oynatıcı.

    playbin, GStreamer'ın yüksek seviyeli ses/video oynatma elemanıdır.
    URL'den otomatik olarak codec ve format algılayarak çalma yapabilir.
    MP3, AAC, HLS (m3u8), PLS ve diğer tüm formatları destekler.
    """

    def __init__(self):
        Gst.init(None)
        self._playbin = Gst.ElementFactory.make("playbin", "radyola-player")
        if not self._playbin:
            raise RuntimeError("GStreamer playbin oluşturulamadı")

        self._current_station: Optional[RadioStation] = None
        self._on_error: Optional[callable] = None
        self._on_state_changed: Optional[callable] = None
        self._on_volume_changed: Optional[callable] = None

        # Başlangıç ses seviyesini ayarlardan al
        initial_vol = APP_SETTINGS.get("volume", 100)
        self._playbin.set_property("volume", max(0.0, min(1.0, initial_vol / 100.0)))

        # Bus mesajlarını dinle (hata, durum değişikliği vb.)
        bus = self._playbin.get_bus()
        bus.add_signal_watch()
        bus.connect("message::error", self._on_bus_error)
        bus.connect("message::state-changed", self._on_bus_state_changed)
        bus.connect("message::eos", self._on_bus_eos)

    # ── Genel API ──

    def play(self, station: RadioStation) -> None:
        """Belirtilen istasyonu çalmaya başlar."""
        if self._current_station == station and self.is_playing:
            return

        self.stop()
        self._current_station = station
        self._playbin.set_property("uri", station.url)
        self._playbin.set_state(Gst.State.PLAYING)

    def pause(self) -> None:
        """Çalmayı duraklatır."""
        if self._current_station:
            self._playbin.set_state(Gst.State.PAUSED)

    def resume(self) -> None:
        """Duraklatılmış çalmayı sürdürür."""
        if self._current_station:
            self._playbin.set_state(Gst.State.PLAYING)

    def stop(self) -> None:
        """Çalmayı durdurur ve kaynakları serbest bırakır."""
        self._playbin.set_state(Gst.State.NULL)
        self._current_station = None

    def toggle(self, station: RadioStation) -> None:
        """Aynı istasyonsa play/pause toggle, farklıysa yeni istasyonu çal."""
        if self._current_station == station:
            if self.is_playing:
                self.pause()
            else:
                self.resume()
        else:
            self.play(station)

    def set_volume(self, percent: int) -> None:
        """Ses seviyesini ayarlar (0-100)."""
        vol = max(0.0, min(1.0, percent / 100.0))
        self._playbin.set_property("volume", vol)
        # Ayarlara kaydet
        APP_SETTINGS["volume"] = percent
        save_settings(APP_SETTINGS)
        if self._on_volume_changed:
            GLib.idle_add(self._on_volume_changed, percent)

    @property
    def volume(self) -> int:
        """Ses seviyesini yüzde olarak döndürür (0-100)."""
        return int(round(self._playbin.get_property("volume") * 100))

    def on_volume_changed(self, callback: callable) -> None:
        """Ses değişikliği callback'i. callback(percent: int)"""
        self._on_volume_changed = callback

    # ── Durum Sorguları ──

    @property
    def is_playing(self) -> bool:
        """Şu an çalıyor mu?"""
        _, state, _ = self._playbin.get_state(Gst.CLOCK_TIME_NONE)
        return state == Gst.State.PLAYING

    @property
    def is_paused(self) -> bool:
        """Duraklatılmış mı?"""
        _, state, _ = self._playbin.get_state(Gst.CLOCK_TIME_NONE)
        return state == Gst.State.PAUSED

    @property
    def current_station(self) -> Optional[RadioStation]:
        """Şu an çalan/duraklatılan istasyon."""
        return self._current_station

    @property
    def state(self) -> str:
        """Durum string'i: 'playing', 'paused', 'stopped'."""
        if self.is_playing:
            return "playing"
        if self.is_paused:
            return "paused"
        return "stopped"

    # ── Callback'ler ──

    def on_error(self, callback: callable) -> None:
        """Hata callback'i ayarlar. callback(error_message: str)"""
        self._on_error = callback

    def on_state_changed(self, callback: callable) -> None:
        """Durum değişikliği callback'i. callback(state: str)"""
        self._on_state_changed = callback

    # ── Bus Mesaj İşleyicileri ──

    def _on_bus_error(self, bus, message):
        err, debug = message.parse_error()
        error_msg = f"{err.message}"
        if self._on_error:
            GLib.idle_add(self._on_error, error_msg)
        self.stop()

    def _on_bus_state_changed(self, bus, message):
        if message.src != self._playbin:
            return
        _, new_state, _ = message.parse_state_changed()
        if self._on_state_changed:
            state_map = {
                Gst.State.PLAYING: "playing",
                Gst.State.PAUSED: "paused",
                Gst.State.NULL: "stopped",
                Gst.State.READY: "ready",
            }
            state_str = state_map.get(new_state, "unknown")
            GLib.idle_add(self._on_state_changed, state_str)

    def _on_bus_eos(self, bus, message):
        """Akış sona erdiğinde."""
        self.stop()
        if self._on_state_changed:
            GLib.idle_add(self._on_state_changed, "stopped")

    def cleanup(self):
        """Kaynakları temizler. Uygulama kapanışında çağrılmalı."""
        self.stop()


# ──────────────────────────────────────────────
# MPRIS v2.2 D-Bus Servisi
# ──────────────────────────────────────────────


if HAS_DBUS:

    class MprisService(dbus.service.Object):
        """MPRIS v2.2 D-Bus arayüzü — masaüstü medya kontrolleri entegrasyonu.

        GNOME Shell Quick Settings, KDE Plasma widget, klavye media tuşları
        ve kilit ekranı kontrolleriyle otomatik entegrasyon sağlar.
        """

        MPRIS_IFACE = "org.mpris.MediaPlayer2"
        PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
        PROPS_IFACE = "org.freedesktop.DBus.Properties"
        BUS_NAME = "org.mpris.MediaPlayer2.Radyola"

        def __init__(self, player: GStreamerPlayer, app):
            DBusGMainLoop(set_as_default=True)
            self._bus = dbus.SessionBus()
            self._bus_name = dbus.service.BusName(self.BUS_NAME, self._bus)
            super().__init__(self._bus_name, "/org/mpris/MediaPlayer2")
            self._player = player
            self._app = app
            self._last_status = "Stopped"

        # ── org.freedesktop.DBus.Properties ──

        @dbus.service.method(PROPS_IFACE, in_signature="ss", out_signature="v")
        def Get(self, interface, prop):
            return self.GetAll(interface).get(prop, "")

        @dbus.service.method(PROPS_IFACE, in_signature="s", out_signature="a{sv}")
        def GetAll(self, interface):
            if interface == self.MPRIS_IFACE:
                return {
                    "CanQuit": True,
                    "CanRaise": False,
                    "HasTrackList": False,
                    "Identity": "Radyola",
                    "DesktopEntry": "radyola",
                    "SupportedUriSchemes": dbus.Array([], signature="s"),
                    "SupportedMimeTypes": dbus.Array([], signature="s"),
                }
            elif interface == self.PLAYER_IFACE:
                return {
                    "PlaybackStatus": self._playback_status(),
                    "Metadata": dbus.Dictionary(self._metadata(), signature="sv"),
                    "Rate": 1.0,
                    "MinimumRate": 1.0,
                    "MaximumRate": 1.0,
                    "Volume": 1.0,
                    "CanControl": True,
                    "CanPlay": True,
                    "CanPause": True,
                    "CanSeek": False,
                    "CanGoNext": True,
                    "CanGoPrevious": True,
                }
            return {}

        @dbus.service.method(PROPS_IFACE, in_signature="ssv")
        def Set(self, interface, prop, value):
            pass  # Read-only properties

        # ── org.mpris.MediaPlayer2 ──

        @dbus.service.method(MPRIS_IFACE)
        def Raise(self):
            pass  # Tray-only mod — pencere yok

        @dbus.service.method(MPRIS_IFACE)
        def Quit(self):
            if self._app:
                GLib.idle_add(self._app.quit)

        # ── org.mpris.MediaPlayer2.Player ──

        @dbus.service.method(PLAYER_IFACE)
        def Play(self):
            if self._player.current_station:
                GLib.idle_add(self._player.resume)
            else:
                GLib.idle_add(self._player.play, STATIONS[0])

        @dbus.service.method(PLAYER_IFACE)
        def Pause(self):
            GLib.idle_add(self._player.pause)

        @dbus.service.method(PLAYER_IFACE)
        def PlayPause(self):
            if self._player.is_playing:
                GLib.idle_add(self._player.pause)
            elif self._player.current_station:
                GLib.idle_add(self._player.resume)
            else:
                GLib.idle_add(self._player.play, STATIONS[0])

        @dbus.service.method(PLAYER_IFACE)
        def Stop(self):
            GLib.idle_add(self._player.stop)

        @dbus.service.method(PLAYER_IFACE)
        def Next(self):
            self._switch_station(1)

        @dbus.service.method(PLAYER_IFACE)
        def Previous(self):
            self._switch_station(-1)

        # ── PropertiesChanged Sinyali ──

        @dbus.service.signal(PROPS_IFACE, signature="sa{sv}as")
        def PropertiesChanged(self, interface, changed, invalidated):
            pass

        # ── Yardımcı Metodlar ──

        def _playback_status(self) -> str:
            if self._player.is_playing:
                return "Playing"
            if self._player.is_paused:
                return "Paused"
            return "Stopped"

        def _metadata(self) -> dict:
            station = self._player.current_station
            if not station:
                return {
                    "mpris:trackid": dbus.ObjectPath(
                        "/org/mpris/MediaPlayer2/NoTrack"
                    ),
                }
            return {
                "mpris:trackid": dbus.ObjectPath(
                    "/org/mpris/MediaPlayer2/track/current"
                ),
                "xesam:title": station.title,
                "xesam:artist": dbus.Array(["İnternet Radyo"], signature="s"),
                "xesam:genre": dbus.Array([station.genre] if station.genre else [], signature="s"),
                "xesam:comment": dbus.Array(
                    [f"{station.flag} {station.location}"] if station.location else [], signature="s"
                ),
            }

        def _switch_station(self, direction: int) -> None:
            """Sonraki/önceki istasyona geç."""
            current = self._player.current_station
            if not current:
                GLib.idle_add(self._player.play, STATIONS[0])
                return
            try:
                idx = STATIONS.index(current)
            except ValueError:
                idx = -1
            new_idx = (idx + direction) % len(STATIONS)
            GLib.idle_add(self._player.play, STATIONS[new_idx])

        def emit_state_change(self) -> None:
            """Oynatıcı durum değişikliğinde çağrılır."""
            status = self._playback_status()
            changed = {
                "PlaybackStatus": status,
                "Metadata": dbus.Dictionary(self._metadata(), signature="sv"),
            }
            self.PropertiesChanged(self.PLAYER_IFACE, changed, [])
            self._last_status = status

        def cleanup(self) -> None:
            """D-Bus kaydını temizler."""
            try:
                self._bus_name.__del__()
            except Exception:
                pass


# ──────────────────────────────────────────────
# DBusMenu Servisi (System Tray Menüsü)
# ──────────────────────────────────────────────


if HAS_DBUS:

    class DBusMenuService(dbus.service.Object):
        """com.canonical.dbusmenu protokolü ile system tray menüsü.

        Tray ikonuna tıklandığında radyo kanallarını, oynatma kontrollerini
        ve çıkış seçeneğini bir menü olarak gösterir. Pencere açılmaz.

        Menü yapısı:
            ── Radyola ──────────────
            ▶ 🇹🇷 Açık Radyo (Kültür)
            ▶ 🇷🇺 Sputnik Türkiye (Haber)
            ...
            ─────────────────────────
            ⏸ Duraklat / ▶ Devam
            ⏹ Durdur
            ─────────────────────────
            📺 Pencereyi Göster
            ❌ Çıkış
        """

        MENU_IFACE = "com.canonical.dbusmenu"
        PROPS_IFACE = "org.freedesktop.DBus.Properties"

        # Sabit menü öğe ID'leri
        _ROOT_ID = 0
        _HEADER_ID = 1
        _SEP1_ID = 2
        _STATION_BASE_ID = 100  # İstasyonlar: 100, 101, 102, ...
        _COUNTRY_BASE_ID = 200  # Ülke alt menüleri: 200, 201, 202, ...
        _SEP2_ID = 50
        _PLAY_PAUSE_ID = 51
        _STOP_ID = 52
        _SEP3_ID = 53
        _VOLUME_MENU_ID = 70     # Ses seviyesi alt menüsü
        _VOLUME_0_ID = 71        # Sessiz
        _VOLUME_25_ID = 72
        _VOLUME_50_ID = 73
        _VOLUME_75_ID = 74
        _VOLUME_100_ID = 75
        _SETTINGS_MENU_ID = 60   # Ayarlar alt menüsü
        _SETTINGS_AUTOPLAY_ID = 62
        _SETTINGS_REMEMBER_ID = 63
        _QUIT_ID = 55

        # Ses seviyesi presetleri: (ID, etiket, yüzde)
        _VOLUME_PRESETS = [
            (71, "🔇  Sessiz", 0),
            (72, "🔈  %25", 25),
            (73, "🔉  %50", 50),
            (74, "🔉  %75", 75),
            (75, "🔊  %100", 100),
        ]

        def __init__(self, player: GStreamerPlayer, app, bus: dbus.SessionBus):
            super().__init__(bus, "/DBusMenu")
            self._player = player
            self._app = app
            self._revision = dbus.UInt32(1)

        def _get_country_groups(self):
            """İstasyonları ülkeye göre gruplar (modül seviyesi fonksiyona delege)."""
            return _get_country_groups()

        def _build_layout(self, parent_id, depth, props):
            """Menü ağacını oluşturur.

            parent_id=0: root menü (başlık, ülke alt menüleri, kontroller)
            parent_id=200+: ülke alt menüsü (o ülkenin istasyonları)
            parent_id=60: ayarlar alt menüsü
            """
            current = self._player.current_station
            country_groups = self._get_country_groups()
            country_list = list(country_groups.keys())

            # ── Ses seviyesi alt menüsü ──
            if parent_id == self._VOLUME_MENU_ID:
                current_vol = self._player.volume
                children = []
                for vid, vlabel, vpercent in self._VOLUME_PRESETS:
                    children.append(self._make_item(
                        vid,
                        {"label": vlabel,
                         "toggle-type": "radio",
                         "toggle-state": dbus.Int32(1 if current_vol == vpercent else 0),
                         "enabled": True},
                    ))

                submenu_item = dbus.Struct(
                    (dbus.Int32(parent_id),
                     dbus.Dictionary({"children-display": "submenu"}, signature="sv"),
                     dbus.Array(children, signature="v")),
                    signature=None,
                )
                return dbus.Struct(
                    (self._revision, submenu_item),
                    signature=None,
                )

            # ── Ayarlar alt menüsü ──
            if parent_id == self._SETTINGS_MENU_ID:
                settings = APP_SETTINGS
                children = []

                # Başlangıçta otomatik çal
                children.append(self._make_item(
                    self._SETTINGS_AUTOPLAY_ID,
                    {"label": "Başlangıçta otomatik çal",
                     "toggle-type": "checkmark",
                     "toggle-state": dbus.Int32(1 if settings.get("autoplay_on_start", False) else 0),
                     "enabled": True},
                ))

                # Son istasyonu hatırla
                children.append(self._make_item(
                    self._SETTINGS_REMEMBER_ID,
                    {"label": "Son istasyonu hatırla",
                     "toggle-type": "checkmark",
                     "toggle-state": dbus.Int32(1 if settings.get("remember_station", True) else 0),
                     "enabled": True},
                ))

                submenu_item = dbus.Struct(
                    (dbus.Int32(parent_id),
                     dbus.Dictionary({"children-display": "submenu"}, signature="sv"),
                     dbus.Array(children, signature="v")),
                    signature=None,
                )
                return dbus.Struct(
                    (self._revision, submenu_item),
                    signature=None,
                )

            # ── Ülke alt menüsü ──
            if self._COUNTRY_BASE_ID <= parent_id < self._COUNTRY_BASE_ID + len(country_list):
                country_idx = parent_id - self._COUNTRY_BASE_ID
                country_name = country_list[country_idx]
                station_items = country_groups[country_name]

                children = []
                for station_idx, station in station_items:
                    item_id = self._STATION_BASE_ID + station_idx
                    label = f"{station.flag}  {station.title}"
                    if station.genre:
                        label += f"  [{station.genre}]"
                    if station.city:
                        label += f"  ({station.city})"

                    props_dict = {"label": label, "enabled": True}
                    if current and current.title == station.title:
                        props_dict["toggle-type"] = "radio"
                        props_dict["toggle-state"] = dbus.Int32(1)
                    else:
                        props_dict["toggle-type"] = "radio"
                        props_dict["toggle-state"] = dbus.Int32(0)

                    children.append(self._make_item(item_id, props_dict))

                submenu_item = dbus.Struct(
                    (dbus.Int32(parent_id),
                     dbus.Dictionary({"children-display": "submenu"}, signature="sv"),
                     dbus.Array(children, signature="v")),
                    signature=None,
                )
                return dbus.Struct(
                    (self._revision, submenu_item),
                    signature=None,
                )

            # ── Diğer parent_id'ler (istasyon öğeleri vb.) ──
            if parent_id != self._ROOT_ID:
                return dbus.Struct(
                    (self._revision,
                     dbus.Struct(
                         (dbus.Int32(parent_id),
                          dbus.Dictionary({}, signature="sv"),
                          dbus.Array([], signature="v")),
                         signature=None)),
                    signature=None,
                )

            # ── Root menü ──
            children = []

            # ── Başlık ──
            if current:
                state_text = "⏸ Duraklatıldı" if self._player.is_paused else "🎵 Çalıyor"
                header_label = f"{state_text} — {current.title}"
            else:
                header_label = "Radyola — İnternet Radyo"
            children.append(self._make_item(
                self._HEADER_ID,
                {"label": header_label, "enabled": False},
            ))

            # ── Ayırıcı 1 ──
            children.append(self._make_item(
                self._SEP1_ID,
                {"type": "separator"},
            ))

            # ── Ülke Alt Menüleri ──
            for country_idx, (country_name, station_items) in enumerate(country_groups.items()):
                country_menu_id = self._COUNTRY_BASE_ID + country_idx

                # Ülke bayrağı ve ismi
                flag = station_items[0][1].flag if station_items else "📻"
                count = len(station_items)

                # Aktif istasyon bu ülkede mi?
                active_in_group = any(
                    current and current.title == s.title
                    for _, s in station_items
                )
                if active_in_group:
                    label = f"{flag}  {country_name}  ▸ 🔊"
                else:
                    label = f"{flag}  {country_name}  ({count})"

                # Alt menü öğesi — çocukları GetLayout(country_menu_id) ile doldurulacak
                submenu_children = []
                for station_idx, station in station_items:
                    item_id = self._STATION_BASE_ID + station_idx
                    st_label = f"{station.flag}  {station.title}"
                    if station.city:
                        st_label += f"  ({station.city})"

                    st_props = {"label": st_label, "enabled": True}
                    if current and current.title == station.title:
                        st_props["toggle-type"] = "radio"
                        st_props["toggle-state"] = dbus.Int32(1)
                    else:
                        st_props["toggle-type"] = "radio"
                        st_props["toggle-state"] = dbus.Int32(0)

                    submenu_children.append(self._make_item(item_id, st_props))

                country_item = dbus.Struct(
                    (dbus.Int32(country_menu_id),
                     dbus.Dictionary(
                         {"label": dbus.String(label),
                          "children-display": dbus.String("submenu"),
                          "enabled": dbus.Boolean(True)},
                         signature="sv",
                     ),
                     dbus.Array(submenu_children, signature="v")),
                    signature=None,
                )
                children.append(country_item)

            # ── Ayırıcı 2 ──
            children.append(self._make_item(
                self._SEP2_ID,
                {"type": "separator"},
            ))

            # ── Oynatma Kontrolleri ──
            if self._player.is_playing:
                pp_label = "⏸  Duraklat"
            elif self._player.is_paused:
                pp_label = "▶  Devam"
            else:
                pp_label = "▶  Çal"
            children.append(self._make_item(
                self._PLAY_PAUSE_ID,
                {"label": pp_label, "enabled": bool(current)},
            ))

            children.append(self._make_item(
                self._STOP_ID,
                {"label": "⏹  Durdur",
                 "enabled": bool(current)},
            ))

            # ── Ses Seviyesi Alt Menüsü ──
            current_vol = self._player.volume
            vol_children = []
            for vid, vlabel, vpercent in self._VOLUME_PRESETS:
                vol_children.append(self._make_item(
                    vid,
                    {"label": vlabel,
                     "toggle-type": "radio",
                     "toggle-state": dbus.Int32(1 if current_vol == vpercent else 0),
                     "enabled": True},
                ))

            # Ses seviyesi ikonu
            if current_vol == 0:
                vol_icon = "🔇"
            elif current_vol <= 50:
                vol_icon = "🔉"
            else:
                vol_icon = "🔊"

            vol_item = dbus.Struct(
                (dbus.Int32(self._VOLUME_MENU_ID),
                 dbus.Dictionary(
                     {"label": dbus.String(f"{vol_icon}  Ses: %{current_vol}"),
                      "children-display": dbus.String("submenu"),
                      "enabled": dbus.Boolean(True)},
                     signature="sv",
                 ),
                 dbus.Array(vol_children, signature="v")),
                signature=None,
            )
            children.append(vol_item)

            # ── Ayırıcı 3 ──
            children.append(self._make_item(
                self._SEP3_ID,
                {"type": "separator"},
            ))

            # ── Ayarlar Alt Menüsü ──
            settings = APP_SETTINGS
            settings_children = []
            settings_children.append(self._make_item(
                self._SETTINGS_AUTOPLAY_ID,
                {"label": "Başlangıçta otomatik çal",
                 "toggle-type": "checkmark",
                 "toggle-state": dbus.Int32(1 if settings.get("autoplay_on_start", False) else 0),
                 "enabled": True},
            ))
            settings_children.append(self._make_item(
                self._SETTINGS_REMEMBER_ID,
                {"label": "Son istasyonu hatırla",
                 "toggle-type": "checkmark",
                 "toggle-state": dbus.Int32(1 if settings.get("remember_station", True) else 0),
                 "enabled": True},
            ))

            settings_item = dbus.Struct(
                (dbus.Int32(self._SETTINGS_MENU_ID),
                 dbus.Dictionary(
                     {"label": dbus.String("⚙️  Ayarlar"),
                      "children-display": dbus.String("submenu"),
                      "enabled": dbus.Boolean(True)},
                     signature="sv",
                 ),
                 dbus.Array(settings_children, signature="v")),
                signature=None,
            )
            children.append(settings_item)

            # ── Çıkış ──
            children.append(self._make_item(
                self._QUIT_ID,
                {"label": "❌  Çıkış", "enabled": True},
            ))

            root_item = dbus.Struct(
                (dbus.Int32(self._ROOT_ID),
                 dbus.Dictionary(
                     {"children-display": "submenu"},
                     signature="sv",
                 ),
                 dbus.Array(children, signature="v")),
                signature=None,
            )

            return dbus.Struct(
                (self._revision, root_item),
                signature=None,
            )

        @staticmethod
        def _make_item(item_id, props):
            """Tek bir menü öğesi oluşturur (çocuksuz)."""
            d = dbus.Dictionary({}, signature="sv")
            for k, v in props.items():
                if isinstance(v, bool):
                    d[k] = dbus.Boolean(v)
                elif isinstance(v, int) and not isinstance(v, bool):
                    d[k] = dbus.Int32(v)
                else:
                    d[k] = dbus.String(str(v))
            return dbus.Struct(
                (dbus.Int32(item_id), d, dbus.Array([], signature="v")),
                signature=None,
            )

        # ── com.canonical.dbusmenu Metodları ──

        @dbus.service.method(MENU_IFACE, in_signature="iias", out_signature="u(ia{sv}av)")
        def GetLayout(self, parent_id, recursion_depth, property_names):
            return self._build_layout(parent_id, recursion_depth, property_names)

        @dbus.service.method(MENU_IFACE, in_signature="aias", out_signature="a(ia{sv})")
        def GetGroupProperties(self, ids, property_names):
            result = dbus.Array([], signature="(ia{sv})")
            return result

        @dbus.service.method(MENU_IFACE, in_signature="i", out_signature="b")
        def AboutToShow(self, item_id):
            """Menü açılmadan hemen önce çağrılır.

            Root menü (0) için layout'u güncelle.
            Alt menüler (ülke menüleri) için güncelleme yapma —
            aksi halde menü açılıp hemen kapanır.
            """
            if item_id == self._ROOT_ID:
                self._revision = dbus.UInt32(self._revision + 1)
                return True  # needs_update = True
            return False  # alt menüler için güncelleme gerekmez

        @dbus.service.method(MENU_IFACE, in_signature="isvu", out_signature="")
        def Event(self, item_id, event_id, data, timestamp):
            """Menü öğesine tıklandığında çağrılır."""
            if event_id != "clicked":
                return

            # Ülke alt menü başlıkları — tıklama eylemi yok, alt menü açılır
            country_groups = self._get_country_groups()
            if self._COUNTRY_BASE_ID <= item_id < self._COUNTRY_BASE_ID + len(country_groups):
                return

            # İstasyon seçimi
            if self._STATION_BASE_ID <= item_id < self._STATION_BASE_ID + len(STATIONS):
                station_idx = item_id - self._STATION_BASE_ID
                station = STATIONS[station_idx]
                GLib.idle_add(self._player.toggle, station)
                self._notify_layout_update()
                return

            # Play/Pause
            if item_id == self._PLAY_PAUSE_ID:
                if self._player.is_playing:
                    GLib.idle_add(self._player.pause)
                elif self._player.current_station:
                    GLib.idle_add(self._player.resume)
                self._notify_layout_update()
                return

            # Durdur
            if item_id == self._STOP_ID:
                GLib.idle_add(self._player.stop)
                self._notify_layout_update()
                return

            # ── Ses Seviyesi Seçimi ──
            for vid, vlabel, vpercent in self._VOLUME_PRESETS:
                if item_id == vid:
                    GLib.idle_add(self._player.set_volume, vpercent)
                    self._notify_layout_update()
                    return

            # ── Ayarlar Toggle'ları ──
            if item_id == self._SETTINGS_AUTOPLAY_ID:
                APP_SETTINGS["autoplay_on_start"] = not APP_SETTINGS.get("autoplay_on_start", False)
                save_settings(APP_SETTINGS)
                self._notify_layout_update()
                return

            if item_id == self._SETTINGS_REMEMBER_ID:
                APP_SETTINGS["remember_station"] = not APP_SETTINGS.get("remember_station", True)
                save_settings(APP_SETTINGS)
                self._notify_layout_update()
                return

            # Çıkış
            if item_id == self._QUIT_ID:
                if self._app:
                    GLib.idle_add(self._app.quit)
                return

        @dbus.service.method(MENU_IFACE, in_signature="ai", out_signature="ai")
        def AboutToShowGroup(self, ids):
            # Sadece root menü varsa revision artır
            updated_ids = []
            for item_id in ids:
                if item_id == self._ROOT_ID:
                    self._revision = dbus.UInt32(self._revision + 1)
                    updated_ids.append(item_id)
            return dbus.Array(updated_ids, signature="i")

        @dbus.service.method(MENU_IFACE, in_signature="a(isvu)", out_signature="ai")
        def EventGroup(self, events):
            id_errors = dbus.Array([], signature="i")
            for item_id, event_id, data, timestamp in events:
                self.Event(item_id, event_id, data, timestamp)
            return id_errors

        # ── org.freedesktop.DBus.Properties ──

        @dbus.service.method(PROPS_IFACE, in_signature="ss", out_signature="v")
        def Get(self, interface, prop):
            return self.GetAll(interface).get(prop, "")

        @dbus.service.method(PROPS_IFACE, in_signature="s", out_signature="a{sv}")
        def GetAll(self, interface):
            if interface == self.MENU_IFACE:
                return {
                    "Version": dbus.UInt32(3),
                    "TextDirection": "ltr",
                    "Status": "normal",
                    "IconThemePath": dbus.Array([], signature="s"),
                }
            return {}

        @dbus.service.method(PROPS_IFACE, in_signature="ssv")
        def Set(self, interface, prop, value):
            pass

        # ── Sinyaller ──

        @dbus.service.signal(MENU_IFACE, signature="u(ia{sv}av)")
        def LayoutUpdated(self, revision, layout):
            pass

        @dbus.service.signal(MENU_IFACE, signature="a(ia{sv})a(ias)")
        def ItemsPropertiesUpdated(self, updated_props, removed_props):
            pass

        def _notify_layout_update(self):
            """Menü yapısının değiştiğini tray host'a bildirir."""
            self._revision = dbus.UInt32(self._revision + 1)
            try:
                self.LayoutUpdated(
                    self._revision,
                    dbus.Struct(
                        (dbus.Int32(0),
                         dbus.Dictionary({}, signature="sv"),
                         dbus.Array([], signature="v")),
                        signature=None,
                    ),
                )
            except Exception:
                pass

        def cleanup(self) -> None:
            pass


# ──────────────────────────────────────────────
# StatusNotifierItem (System Tray) D-Bus
# ──────────────────────────────────────────────


if HAS_DBUS:

    class TrayIndicator(dbus.service.Object):
        """StatusNotifierItem D-Bus protokolü ile system tray ikonu.

        GNOME (gnome-shell-extension-appindicator uzantısıyla), KDE Plasma,
        XFCE ve MATE tarafından desteklenir. Tray host yoksa sessizce
        devre dışı kalır.

        ItemIsMenu=True olarak ayarlandığında, tray ikonuna tıklamak
        doğrudan DBusMenu menüsünü gösterir (pencere açmaz).
        """

        SNI_IFACE = "org.kde.StatusNotifierItem"
        SNI_WATCHER = "org.kde.StatusNotifierWatcher"
        PROPS_IFACE = "org.freedesktop.DBus.Properties"

        _ICON_MAP = {
            "stopped": "audio-x-generic",
            "playing": "media-playback-start",
            "paused": "media-playback-pause",
        }

        def __init__(self, player: GStreamerPlayer, app, bus: dbus.SessionBus,
                     dbus_menu: "DBusMenuService" = None):
            self._obj_path = "/StatusNotifierItem"
            super().__init__(bus, self._obj_path)
            self._player = player
            self._app = app
            self._bus = bus
            self._dbus_menu = dbus_menu
            self._current_icon = "audio-x-generic"
            self._registered = False
            self._try_register()

        def _try_register(self) -> None:
            """StatusNotifierWatcher'a kayıt ol."""
            try:
                watcher = self._bus.get_object(
                    self.SNI_WATCHER, "/StatusNotifierWatcher"
                )
                watcher_iface = dbus.Interface(watcher, self.SNI_WATCHER)
                watcher_iface.RegisterStatusNotifierItem(self._obj_path)
                self._registered = True
                log.info("System tray: StatusNotifierWatcher'a kayıt olundu")
            except dbus.DBusException:
                log.info(
                    "System tray: StatusNotifierWatcher bulunamadı — "
                    "tray ikonu devre dışı (GNOME'da gnome-shell-extension-appindicator gerekir)"
                )
                self._registered = False

        @property
        def is_registered(self) -> bool:
            return self._registered

        # ── org.freedesktop.DBus.Properties ──

        @dbus.service.method(PROPS_IFACE, in_signature="ss", out_signature="v")
        def Get(self, interface, prop):
            return self.GetAll(interface).get(prop, "")

        @dbus.service.method(PROPS_IFACE, in_signature="s", out_signature="a{sv}")
        def GetAll(self, interface):
            if interface == self.SNI_IFACE:
                station = self._player.current_station
                tooltip_text = (
                    f"Radyola — {station.title}" if station else "Radyola"
                )
                return {
                    "Category": "ApplicationStatus",
                    "Id": "radyola",
                    "Title": "Radyola",
                    "Status": "Active",
                    "IconName": self._current_icon,
                    "ToolTip": dbus.Struct(
                        ("", dbus.Array([], signature="(iiay)"),
                         tooltip_text, ""),
                        signature=None,
                    ),
                    "ItemIsMenu": True,
                    "Menu": dbus.ObjectPath("/DBusMenu"),
                }
            return {}

        # ── StatusNotifierItem Aksiyonları ──

        @dbus.service.method(SNI_IFACE, in_signature="ii")
        def Activate(self, x, y):
            """Sol tık — menü gösterilir (ItemIsMenu=True olduğu için
            tray host bu metodu çağırmak yerine doğrudan DBusMenu'yü kullanır)."""
            pass

        @dbus.service.method(SNI_IFACE, in_signature="ii")
        def SecondaryActivate(self, x, y):
            """Orta tık — play/pause toggle."""
            if self._player.is_playing:
                GLib.idle_add(self._player.pause)
            elif self._player.current_station:
                GLib.idle_add(self._player.resume)

        @dbus.service.method(SNI_IFACE, in_signature="is")
        def Scroll(self, delta, orientation):
            """Fare tekerleği — istasyonlar arası geçiş.

            Yukarı kaydırma: önceki istasyon
            Aşağı kaydırma: sonraki istasyon
            """
            if not STATIONS:
                return
            current = self._player.current_station
            if not current:
                # Hiçbir şey çalmıyorsa ilk istasyonu başlat
                GLib.idle_add(self._player.play, STATIONS[0])
                return
            try:
                idx = STATIONS.index(current)
            except ValueError:
                idx = 0
            # delta > 0: yukarı (önceki), delta < 0: aşağı (sonraki)
            direction = -1 if delta > 0 else 1
            new_idx = (idx + direction) % len(STATIONS)
            GLib.idle_add(self._player.play, STATIONS[new_idx])

        # ── Sinyaller ──

        @dbus.service.signal(SNI_IFACE)
        def NewIcon(self):
            pass

        @dbus.service.signal(SNI_IFACE)
        def NewToolTip(self):
            pass

        @dbus.service.signal(SNI_IFACE)
        def NewStatus(self, status):
            pass

        # ── Güncelleme ──

        def update_icon(self, state: str) -> None:
            """Çalma durumuna göre tray ikonunu günceller."""
            new_icon = self._ICON_MAP.get(state, "audio-x-generic")
            if new_icon != self._current_icon:
                self._current_icon = new_icon
                if self._registered:
                    self.NewIcon()
                    self.NewToolTip()
            # Menü içeriğini de güncelle
            if self._dbus_menu:
                self._dbus_menu._notify_layout_update()

        def cleanup(self) -> None:
            pass


# ──────────────────────────────────────────────
# Uygulama (Tray-Only — Pencere Yok)
# ──────────────────────────────────────────────


class RadyolaApp(Adw.Application):
    """Radyola — Tray-only internet radyo uygulaması.

    Pencere açmaz; sadece system tray ikonu ve MPRIS D-Bus
    arayüzü üzerinden çalışır.
    """

    def __init__(self):
        super().__init__(
            application_id="com.aripd.radyola",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self._player: Optional[GStreamerPlayer] = None
        self._mpris: Optional[object] = None
        self._tray: Optional[object] = None
        self._dbus_menu: Optional[object] = None

    def do_activate(self) -> None:
        """Uygulama aktifleştiğinde D-Bus servislerini başlatır (pencere açmaz)."""
        if not self._player:
            self._player = GStreamerPlayer()
            self._player.on_error(self._on_player_error)
            self._player.on_state_changed(self._on_player_state_changed)
            self._setup_dbus_services()
            self._apply_startup_settings()
            # Uygulamayı ayakta tut (pencere olmadığı için hold gerekli)
            self.hold()
            log.info("Radyola tray-only modda başlatıldı")

    def _setup_dbus_services(self) -> None:
        """MPRIS, DBusMenu ve System Tray D-Bus servislerini başlatır."""
        if not HAS_DBUS or not self._player:
            return

        # MPRIS medya kontrolleri
        try:
            self._mpris = MprisService(self._player, self)
            log.info("MPRIS D-Bus servisi başlatıldı")
        except Exception as e:
            log.warning(f"MPRIS başlatılamadı: {e}")
            self._mpris = None

        # DBusMenu + System Tray ikonu
        try:
            bus = dbus.SessionBus()
            self._dbus_menu = DBusMenuService(self._player, self, bus)
            log.info("DBusMenu servisi başlatıldı")
            self._tray = TrayIndicator(self._player, self, bus, self._dbus_menu)
            if self._tray.is_registered:
                log.info("System tray ikonu aktif (menülü)")
            else:
                log.info("System tray ikonu devre dışı (host yok)")
        except Exception as e:
            log.warning(f"System tray başlatılamadı: {e}")
            self._tray = None
            self._dbus_menu = None

    def _apply_startup_settings(self) -> None:
        """Başlangıç ayarlarını uygular (son istasyon, otomatik çalma)."""
        last_name = APP_SETTINGS.get("last_station", "")
        if last_name and APP_SETTINGS.get("remember_station", True):
            target = None
            for s in STATIONS:
                if s.title == last_name:
                    target = s
                    break
            if target and APP_SETTINGS.get("autoplay_on_start", False):
                GLib.timeout_add(500, self._autoplay_station, target)

    def _autoplay_station(self, station: RadioStation) -> bool:
        """Başlangıçta istasyonu otomatik çalar."""
        if self._player:
            self._player.play(station)
        return False

    def _on_player_error(self, error_msg: str) -> None:
        """Oynatıcı hatası durumunda loglar."""
        log.error(f"Oynatıcı hatası: {error_msg}")

    def _on_player_state_changed(self, state: str) -> None:
        """Oynatıcı durumu değiştiğinde MPRIS + Tray günceller."""
        if self._mpris:
            try:
                self._mpris.emit_state_change()
            except Exception:
                pass
        if self._tray:
            try:
                self._tray.update_icon(state)
            except Exception:
                pass

    def do_shutdown(self) -> None:
        """Uygulama kapanışında temizlik yapar."""
        if self._player and self._player.current_station:
            if APP_SETTINGS.get("remember_station", True):
                APP_SETTINGS["last_station"] = self._player.current_station.title
                save_settings(APP_SETTINGS)
        if self._mpris:
            self._mpris.cleanup()
        if self._dbus_menu:
            self._dbus_menu.cleanup()
        if self._tray:
            self._tray.cleanup()
        if self._player:
            self._player.cleanup()
        Adw.Application.do_shutdown(self)


# ──────────────────────────────────────────────
# Giriş Noktası
# ──────────────────────────────────────────────

def main() -> int:
    """Uygulamayı başlatır ve çıkış kodunu döndürür."""
    app = RadyolaApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())

