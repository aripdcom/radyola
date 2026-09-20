#!/bin/bash
# ──────────────────────────────────────────────
# Radyola Linux — DEB Paket Oluşturma Scripti
# Debian 13 (Trixie) için .deb paketi oluşturur
# ──────────────────────────────────────────────

set -e

VERSION="1.0.0"
PACKAGE_NAME="radyola"
ARCH="all"  # Python — mimariden bağımsız

BUILD_DIR="$(pwd)/build/${PACKAGE_NAME}_${VERSION}_${ARCH}"

echo "[1/5] Temizleniyor..."
rm -rf build/ *.deb

echo "[2/5] Dizin yapısı oluşturuluyor..."
mkdir -p "${BUILD_DIR}/DEBIAN"
mkdir -p "${BUILD_DIR}/opt/radyola"
mkdir -p "${BUILD_DIR}/usr/share/applications"
mkdir -p "${BUILD_DIR}/usr/bin"

# dpkg-deb izin gereksinimleri
chmod 0755 "${BUILD_DIR}/DEBIAN"
find "${BUILD_DIR}" -type d -exec chmod 0755 {} \;

echo "[3/5] Dosyalar kopyalanıyor..."
# Ana uygulama dosyaları
cp radyola.py "${BUILD_DIR}/opt/radyola/"
cp radyola.css "${BUILD_DIR}/opt/radyola/"

# Desktop dosyası (yolları güncelle)
cat > "${BUILD_DIR}/usr/share/applications/radyola.desktop" << 'EOF'
[Desktop Entry]
Name=Radyola
Comment=İnternet Radyo Çalar
Exec=/usr/bin/radyola
Icon=audio-x-generic
Terminal=false
Type=Application
Categories=Audio;Music;Player;
Keywords=radio;radyo;internet;stream;
StartupNotify=false
EOF

# Çalıştırılabilir wrapper script
cat > "${BUILD_DIR}/usr/bin/radyola" << 'EOF'
#!/bin/bash
exec python3 /opt/radyola/radyola.py "$@"
EOF
chmod 755 "${BUILD_DIR}/usr/bin/radyola"

echo "[4/5] DEBIAN kontrol dosyası oluşturuluyor..."
cat > "${BUILD_DIR}/DEBIAN/control" << EOF
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Section: sound
Priority: optional
Architecture: ${ARCH}
Depends: python3 (>= 3.11),
         python3-gi,
         python3-dbus,
         gir1.2-gtk-4.0,
         gir1.2-adw-1,
         gir1.2-gstreamer-1.0,
         gir1.2-gst-plugins-base-1.0,
         gstreamer1.0-plugins-good,
         gstreamer1.0-plugins-bad,
         gstreamer1.0-plugins-ugly
Recommends: gnome-shell-extension-appindicator
Maintainer: Radyola <radyola@example.com>
Description: İnternet Radyo Çalar
 Radyola, GTK4/Libadwaita/GStreamer tabanlı bir internet
 radyo çalar uygulamasıdır. System tray üzerinden çalışır,
 ortak JSON kaynağından dinamik istasyon listesi çeker.
 MPRIS D-Bus entegrasyonu ile media tuşlarını destekler.
Homepage: https://github.com/aripdcom/radyola
EOF

# Post-install script (isteğe bağlı — masaüstü veritabanını günceller)
cat > "${BUILD_DIR}/DEBIAN/postinst" << 'EOF'
#!/bin/bash
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database -q /usr/share/applications/ 2>/dev/null || true
fi
EOF
chmod 755 "${BUILD_DIR}/DEBIAN/postinst"

echo "[5/5] DEB paketi oluşturuluyor..."
# setgid bitlerini temizle (dpkg-deb 2755 izinlerini reddeder)
find "${BUILD_DIR}" -type d -exec chmod g-s {} +
chmod 0755 "${BUILD_DIR}/DEBIAN"
dpkg-deb --build --root-owner-group "${BUILD_DIR}"

# Paketi build dizininden taşı
mv "build/${PACKAGE_NAME}_${VERSION}_${ARCH}.deb" .

echo ""
echo "════════════════════════════════════════════"
echo "  ✅ Paket oluşturuldu: ${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
echo ""
echo "  Kurulum:   sudo dpkg -i ${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"
echo "  Kaldırma:  sudo apt remove ${PACKAGE_NAME}"
echo "  Çalıştır:  radyola"
echo "════════════════════════════════════════════"
