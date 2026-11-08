"""Modül 2 — Firma tanımları (08.11.2026, Kenan Bey): firma kartı + entegratör / SGK / Dijital Vergi Dairesi
erişim bilgileri. İleride bu bilgilerle sorgulama (e-fatura, bildirge) ve muhasebe fişi aktarımı yapılacak.

🔒 Şifreler DOSYAYA YAZILMAZ: Windows Kimlik Bilgisi Yöneticisi'nde (keyring → Windows Credential Manager, DPAPI)
saklanır; firmalar.json yalnız şifresiz bilgileri tutar. Hizmet adı "Başkan", kullanıcı "<firma_id>:<alan>".
"""
import json
import uuid
from pathlib import Path

import keyring
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)

import kayit

HIZMET = "Başkan"
DOSYA_ADI = "firmalar.json"
# (anahtar, etiket, gizli mi)
BOLUMLER = [
    ("Genel", [("unvan", "Unvan *", False), ("vkn", "VKN / TCKN", False), ("vergi_dairesi", "Vergi dairesi", False),
               ("adres", "Adres", False), ("telefon", "Telefon", False), ("eposta", "E-posta", False),
               ("yetkili", "Yetkili kişi", False)]),
    ("E-Fatura Entegratörü", [("entegrator", "Entegratör firma", False), ("entegrator_kullanici", "Kullanıcı adı", False),
                              ("entegrator_sifre", "Şifre", True)]),
    ("SGK", [("sgk_kullanici", "Kullanıcı adı", False), ("sgk_isyeri_kodu", "İşyeri kodu", False),
             ("sgk_sistem_sifre", "Sistem şifresi", True), ("sgk_isyeri_sifre", "İşyeri şifresi", True)]),
    ("Dijital Vergi Dairesi (GİB)", [("gib_kullanici", "Kullanıcı kodu / TCKN", False), ("gib_sifre", "Şifre", True)]),
]
GIZLI = [a for _, alanlar in BOLUMLER for a, _, g in alanlar if g]


def _dosya(kok=None):
    return Path(kok or kayit.KOK) / DOSYA_ADI


def liste(kok=None):
    try:
        return json.loads(_dosya(kok).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def unvanlar(kok=None):
    return sorted((f["unvan"] for f in liste(kok) if f.get("unvan")), key=str.lower)


def sifre_oku(fid, alan):
    try:
        return keyring.get_password(HIZMET, f"{fid}:{alan}") or ""
    except keyring.errors.KeyringError:
        return ""


def kaydet(firma, sifreler, kok=None):
    """firma: şifresiz alanlar (id yoksa atanır); sifreler: {alan: değer} → Kimlik Bilgisi Yöneticisi. Dönüş: id."""
    firma = {k: v for k, v in firma.items() if k not in GIZLI}
    firma.setdefault("id", uuid.uuid4().hex)
    for alan, deger in sifreler.items():
        anahtar = f"{firma['id']}:{alan}"
        if deger:
            keyring.set_password(HIZMET, anahtar, deger)
        else:
            try:
                keyring.delete_password(HIZMET, anahtar)
            except keyring.errors.PasswordDeleteError:
                pass
    l = [f for f in liste(kok) if f.get("id") != firma["id"]] + [firma]
    yol = _dosya(kok)
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".tmp")
    gecici.write_text(json.dumps(sorted(l, key=lambda f: f.get("unvan", "").lower()), ensure_ascii=False, indent=1),
                      encoding="utf-8")
    gecici.replace(yol)
    return firma["id"]


def sil(fid, kok=None):
    for alan in GIZLI:
        try:
            keyring.delete_password(HIZMET, f"{fid}:{alan}")
        except keyring.errors.PasswordDeleteError:
            pass
    l = [f for f in liste(kok) if f.get("id") != fid]
    _dosya(kok).write_text(json.dumps(l, ensure_ascii=False, indent=1), encoding="utf-8")


class FirmaModulu(QWidget):
    def __init__(self, ana_sayfaya):
        super().__init__()
        self.secili = None
        lay = QHBoxLayout(self)

        sol = QVBoxLayout()
        geri = QPushButton("← Ana Sayfa")
        geri.clicked.connect(ana_sayfaya)
        sol.addWidget(geri)
        self.ara = QLineEdit()
        self.ara.setPlaceholderText("Firma ara (unvan / VKN)")
        self.ara.textChanged.connect(self.listele)
        sol.addWidget(self.ara)
        self.liste_w = QListWidget()
        self.liste_w.currentItemChanged.connect(lambda it, _: self.ac(it.data(Qt.UserRole) if it else None))
        sol.addWidget(self.liste_w, 1)
        yeni = QPushButton("+ Yeni Firma")
        yeni.clicked.connect(lambda: self.ac(None))
        sol.addWidget(yeni)
        solw = QWidget()
        solw.setLayout(sol)
        solw.setFixedWidth(320)
        lay.addWidget(solw)

        sag = QVBoxLayout()
        self.baslik = QLabel()
        self.baslik.setStyleSheet("font-size:18px; font-weight:bold; padding:4px")
        sag.addWidget(self.baslik)
        icerik = QWidget()
        ic = QVBoxLayout(icerik)
        self.alanlar = {}
        for bolum, alanlar in BOLUMLER:
            g = QGroupBox(bolum)
            f = QFormLayout(g)
            for a, etiket, gizli in alanlar:
                w = QLineEdit()
                if gizli:
                    w.setEchoMode(QLineEdit.Password)
                    satir = QHBoxLayout()
                    satir.addWidget(w)
                    goster = QPushButton("👁")
                    goster.setFixedWidth(36)
                    goster.setCheckable(True)
                    goster.toggled.connect(lambda acik, w=w: w.setEchoMode(QLineEdit.Normal if acik else QLineEdit.Password))
                    kopya = QPushButton("Kopyala")
                    kopya.clicked.connect(lambda _, w=w: self.kopyala(w.text()))
                    satir.addWidget(goster)
                    satir.addWidget(kopya)
                    f.addRow(etiket + ":", satir)
                else:
                    f.addRow(etiket + ":", w)
                self.alanlar[a] = w
            ic.addWidget(g)
        self.notlar = QPlainTextEdit()
        self.notlar.setPlaceholderText("Notlar")
        self.notlar.setFixedHeight(80)
        ic.addWidget(self.notlar)
        bilgi = QLabel("🔒 Şifreler bu bilgisayarın Windows Kimlik Bilgisi Yöneticisi'nde şifreli saklanır; dosyaya "
                       "yazılmaz ve başka bilgisayara kayıtlarla birlikte taşınmaz.")
        bilgi.setWordWrap(True)
        bilgi.setStyleSheet("color:#555")
        ic.addWidget(bilgi)
        ic.addStretch()
        kaydir = QScrollArea()
        kaydir.setWidgetResizable(True)
        kaydir.setWidget(icerik)
        sag.addWidget(kaydir, 1)
        alt = QHBoxLayout()
        for ad, fn in (("Kaydet", self.kaydet), ("Sil", self.sil)):
            b = QPushButton(ad)
            b.clicked.connect(fn)
            alt.addWidget(b)
        alt.addStretch()
        self.durum = QLabel()
        alt.addWidget(self.durum)
        sag.addLayout(alt)
        lay.addLayout(sag, 1)
        self.listele()
        self.ac(None)

    def listele(self, *_):
        a = self.ara.text().strip().lower()
        self.liste_w.blockSignals(True)
        self.liste_w.clear()
        for f in liste():
            if a and a not in f.get("unvan", "").lower() and a not in f.get("vkn", ""):
                continue
            it = QListWidgetItem(f.get("unvan", "?") + (f"  ·  {f['vkn']}" if f.get("vkn") else ""))
            it.setData(Qt.UserRole, f["id"])
            self.liste_w.addItem(it)
            if f["id"] == self.secili:
                self.liste_w.setCurrentItem(it)
        self.liste_w.blockSignals(False)

    def ac(self, fid):
        self.secili = fid
        f = next((x for x in liste() if x.get("id") == fid), {}) if fid else {}
        for a, w in self.alanlar.items():
            w.setText(sifre_oku(fid, a) if (a in GIZLI and fid) else f.get(a, ""))
        self.notlar.setPlainText(f.get("notlar", ""))
        self.baslik.setText(f.get("unvan") or "Yeni firma")
        self.durum.setText("")

    def kaydet(self):
        veri = {a: w.text().strip() for a, w in self.alanlar.items() if a not in GIZLI}
        if not veri["unvan"]:
            QMessageBox.warning(self, "Başkan", "Unvan zorunlu.")
            return
        if self.secili:
            veri["id"] = self.secili
        veri["notlar"] = self.notlar.toPlainText()
        try:
            self.secili = kaydet(veri, {a: self.alanlar[a].text() for a in GIZLI})
        except keyring.errors.KeyringError as e:
            QMessageBox.critical(self, "Başkan", f"Şifreler güvenli depoya yazılamadı: {e}")
            return
        self.listele()
        self.baslik.setText(veri["unvan"])
        self.durum.setText("✔ Kaydedildi")

    def sil(self):
        if not self.secili:
            return
        if QMessageBox.question(self, "Başkan", f"{self.baslik.text()} ve kayıtlı şifreleri silinsin mi?") != QMessageBox.Yes:
            return
        sil(self.secili)
        self.secili = None
        self.listele()
        self.ac(None)

    def kopyala(self, metin):
        """Panoya kopyalar, 30 sn sonra (pano hâlâ aynıysa) temizler."""
        pano = QApplication.clipboard()
        pano.setText(metin)
        self.durum.setText("Kopyalandı (30 sn sonra panodan silinir)")
        QTimer.singleShot(30_000, lambda: pano.text() == metin and pano.clear())


def sina():
    """Bellek içi keyring ile kaydet / oku / sil; şifrelerin JSON'a yazılmadığını doğrular."""
    import tempfile
    from keyring.backend import KeyringBackend

    class Bellek(KeyringBackend):
        priority = 1
        d = {}
        def get_password(self, s, u): return self.d.get((s, u))
        def set_password(self, s, u, p): self.d[(s, u)] = p
        def delete_password(self, s, u):
            if (s, u) not in self.d:
                raise keyring.errors.PasswordDeleteError()
            del self.d[(s, u)]

    keyring.set_keyring(Bellek())
    k = tempfile.mkdtemp()
    fid = kaydet({"unvan": "Elektromall A.Ş.", "vkn": "1234567890", "gib_sifre": "SIZMAMALI"},
                 {"gib_sifre": "gizli-123", "sgk_sistem_sifre": "s1"}, kok=k)
    ham = _dosya(k).read_text(encoding="utf-8")
    assert "gizli-123" not in ham and "SIZMAMALI" not in ham and "s1" not in ham, "şifre dosyaya yazılmış!"
    assert sifre_oku(fid, "gib_sifre") == "gizli-123" and unvanlar(k) == ["Elektromall A.Ş."]
    kaydet({"id": fid, "unvan": "Elektromall A.Ş."}, {"gib_sifre": "", "sgk_sistem_sifre": "s2"}, kok=k)  # boş = sil
    assert sifre_oku(fid, "gib_sifre") == "" and sifre_oku(fid, "sgk_sistem_sifre") == "s2" and len(liste(k)) == 1
    sil(fid, kok=k)
    assert liste(k) == [] and not Bellek.d
    print("firmalar sına: tamam")


if __name__ == "__main__":
    sina()
