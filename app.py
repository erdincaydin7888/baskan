"""Başkan — masaüstü uygulaması. Modül 1: Mizan → Mali Tablolar."""
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                               QPushButton, QLabel, QLineEdit, QTabWidget, QTableWidget, QTableWidgetItem,
                               QFileDialog, QMessageBox, QStackedWidget, QDialog, QComboBox, QSpinBox,
                               QFormLayout, QDialogButtonBox, QHeaderView, QTextEdit)

import mizan
import motor

UYGULAMA = "Başkan"
RENK = {"sinif": "#dbe7f5", "bolum": "#dbe7f5", "grup": "#eef3f9", "ara": "#fff2cc", "toplam": "#c9e4c5"}


def tl(x):
    return "" if x is None else mizan.tl(x)


def yuzde(x):
    return "" if x is None else f"%{x * 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tablo_doldur(tbl, basliklar, satirlar):
    """satirlar: [(tür, [hücreler])]; sayılar sağa yaslanır, tür rengi ve kalınlığı belirler."""
    tbl.clear()
    tbl.setColumnCount(len(basliklar))
    tbl.setHorizontalHeaderLabels(basliklar)
    tbl.setRowCount(len(satirlar))
    kalin = QFont()
    kalin.setBold(True)
    for i, (tur, hucreler) in enumerate(satirlar):
        for j, v in enumerate(hucreler):
            it = QTableWidgetItem(v if isinstance(v, str) else tl(v))
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if not isinstance(v, str):
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if v is not None and v < 0:
                    it.setForeground(QColor("#b00020"))
            if tur in RENK:
                it.setBackground(QColor(RENK[tur]))
                it.setFont(kalin)
            tbl.setItem(i, j, it)
    tbl.resizeColumnsToContents()
    tbl.horizontalHeader().setStretchLastSection(True)


class EslemeDialog(QDialog):
    """Otomatik bulunamayan/yanlış bulunan sütunları kullanıcının seçmesi için."""

    def __init__(self, df, satir, es, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mizan sütunlarını eşleştir")
        self.resize(1000, 600)
        lay = QVBoxLayout(self)
        on = QTableWidget(min(20, len(df)), df.shape[1])
        on.setHorizontalHeaderLabels([f"Sütun {j + 1}" for j in range(df.shape[1])])
        for i in range(on.rowCount()):
            for j in range(df.shape[1]):
                v = df.iat[i, j]
                on.setItem(i, j, QTableWidgetItem("" if v is None or str(v) == "nan" else str(v)))
        lay.addWidget(QLabel("Dosyanın ilk satırları:"))
        lay.addWidget(on)
        form = QFormLayout()
        self.satir = QSpinBox()
        self.satir.setRange(1, max(1, len(df)))
        self.satir.setValue(satir + 1)
        form.addRow("Başlık satırı (veri bir altından başlar):", self.satir)
        secenek = ["(yok)"] + [f"Sütun {j + 1}: {str(df.iat[satir, j])[:30]}" for j in range(df.shape[1])]
        self.kutu = {}
        for rol in mizan.ROLLER:
            cb = QComboBox()
            cb.addItems(secenek)
            cb.setCurrentIndex(es[rol] + 1 if rol in es else 0)
            self.kutu[rol] = cb
            form.addRow(mizan.ROL_AD[rol] + ":", cb)
        lay.addLayout(form)
        lay.addWidget(QLabel("Bakiye önceliği: Borç−Alacak toplamı → Borç/Alacak Bakiye → tek Bakiye sütunu."))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def sonuc(self):
        return self.satir.value() - 1, {r: cb.currentIndex() - 1 for r, cb in self.kutu.items() if cb.currentIndex() > 0}


class MaliTablolar(QWidget):
    def __init__(self, ana_sayfaya):
        super().__init__()
        self.hesaplar, self.ham, self.okuma_uyari, self.sonuc, self.dosya = None, None, [], None, None
        lay = QVBoxLayout(self)

        ust = QHBoxLayout()
        for ad, fn in (("← Ana Sayfa", ana_sayfaya), ("Mizan Yükle…", self.yukle),
                       ("Sütunları Düzelt…", self.esle), ("Excel'e Aktar…", self.aktar)):
            b = QPushButton(ad)
            b.clicked.connect(fn)
            ust.addWidget(b)
        ust.addStretch()
        lay.addLayout(ust)

        def alan(yer="", gen=130):
            w = QLineEdit()
            w.setPlaceholderText(yer)
            w.setFixedWidth(gen)
            w.textChanged.connect(self.hesapla)
            return w

        def satira(lay_, ciftler):
            for etiket, w in ciftler:
                lay_.addWidget(QLabel(etiket))
                lay_.addWidget(w)
            lay_.addStretch()

        # SMM yöntemi: her yöntemin kendi giriş satırı
        smm_satir = QHBoxLayout()
        smm_satir.addWidget(QLabel("SMM yöntemi:"))
        self.yontem = QComboBox()
        self.yontem.addItems(["Otomatik (mizandan tanı)", "Dönem sonu fiili envanter (150-153)",
                              "Brüt kâr oranı (stoklar mizandan)",
                              "Stok miktar + tutar elle, brüt kâr oranı"])
        self.yontem.currentIndexChanged.connect(self.yontem_degisti)
        smm_satir.addWidget(self.yontem)
        self.yontem_yigin = QStackedWidget()
        self.ds = {s: alan("mizan bakiyesi") for s in motor.STOK}
        self.ds_oto = {s: alan("gerekirse", 110) for s in motor.STOK}
        self.marj_oto = alan("yoksa", 50)
        self.marj = alan("örn. 25", 60)
        self.marj2 = alan("örn. 25", 60)
        self.elle_miktar = alan("adet / kg", 110)
        self.elle_tutar = alan("örn. 400.000.000,00", 150)
        sayfalar = [[(f"{s} DS ₺:", self.ds_oto[s]) for s in motor.STOK] + [("veya brüt kâr %:", self.marj_oto)],
                    [(f"{s} {ad.split(' -')[0].title()} DS ₺:", self.ds[s]) for s, ad in motor.STOK.items()],
                    [("Brüt kâr oranı % (brüt kâr / net satış):", self.marj)],
                    [("Satışa hazır stok miktarı:", self.elle_miktar), ("Stok tutarı ₺:", self.elle_tutar),
                     ("Brüt kâr oranı %:", self.marj2)]]
        for ciftler in sayfalar:
            w = QWidget()
            hl = QHBoxLayout(w)
            hl.setContentsMargins(0, 0, 0, 0)
            satira(hl, ciftler)
            self.yontem_yigin.addWidget(w)
        smm_satir.addWidget(self.yontem_yigin, 1)
        lay.addLayout(smm_satir)
        self.yontem_aciklama = QLabel()
        self.yontem_aciklama.setStyleSheet("color:#555; padding-left:4px")
        self.yontem_aciklama.setWordWrap(True)
        lay.addWidget(self.yontem_aciklama)

        girdi = QHBoxLayout()
        self.istisna = alan(gen=120)
        self.istisna.setText("0")
        self.oran = alan(gen=50)
        self.oran.setText("10")
        self.vergi = alan(gen=50)
        self.vergi.setText("25")
        self.istirak = alan("640/641'den", 120)
        self.gyz = alan("0", 120)
        satira(girdi, (("FGK istisna (yatırıma eklenen) ₺:", self.istisna), ("FGK oranı %:", self.oran),
                       ("Kurumlar vergisi %:", self.vergi), ("İştirak kazancı istisnası ₺:", self.istirak),
                       ("Geçmiş yıl zararı (mali) ₺:", self.gyz)))
        indirim = QHBoxLayout()
        self.arge = alan("0", 120)
        self.bagis = alan("0", 120)
        self.bagis_tam = alan("0", 120)
        satira(indirim, (("Ar-Ge indirimi ₺:", self.arge), ("Bağış (%5 sınırlı) ₺:", self.bagis),
                         ("Tamamı indirilen bağış ₺:", self.bagis_tam)))
        lay.addLayout(indirim)
        lay.addLayout(girdi)
        self.yontem_degisti(0)

        self.durum = QLabel("Bir mizan dosyası yükleyin (xlsx, xls, csv).")
        self.durum.setStyleSheet("font-weight:bold; padding:4px")
        lay.addWidget(self.durum)

        self.sekme = QTabWidget()
        self.tablolar = {}
        for ad in ("Kontrol", "Kebir Mizan", "Envanter ve SMM", "Gelir Tablosu", "Detaylı Bilanço",
                   "FGK Hesaplama", "Vergi ve Rasyolar"):
            w = QTextEdit() if ad == "Kontrol" else QTableWidget()
            if ad == "Kontrol":
                w.setReadOnly(True)
            self.tablolar[ad] = w
            self.sekme.addTab(w, ad)
        lay.addWidget(self.sekme)

    # --- dosya ---
    def yukle(self):
        yol, _ = QFileDialog.getOpenFileName(self, "Mizan seç", "", "Mizan (*.xlsx *.xlsm *.xls *.csv *.txt)")
        if not yol:
            return
        try:
            df = mizan.ham_oku(yol)
            satir, es = mizan.sutun_bul(df)
        except Exception as e:
            QMessageBox.critical(self, UYGULAMA, f"Dosya okunamadı:\n{e}")
            return
        self.dosya, self.ham = yol, (df, satir, es)
        if not self.oku():
            self.esle()

    def esle(self):
        if not self.ham:
            return
        d = EslemeDialog(*self.ham, parent=self)
        if d.exec():
            satir, es = d.sonuc()
            self.ham = (self.ham[0], satir, es)
            self.oku()

    def oku(self):
        df, satir, es = self.ham
        try:
            self.hesaplar, self.okuma_uyari = mizan.kebire_indir(df, satir, es)
        except ValueError as e:
            QMessageBox.warning(self, UYGULAMA, f"{e}\nSütunları elle eşleştirin.")
            return False
        if not self.hesaplar:
            QMessageBox.warning(self, UYGULAMA, "Hiç hesap satırı bulunamadı. Sütunları elle eşleştirin.")
            return False
        self.hesapla()
        return True

    # --- hesap ---
    ACIKLAMA = [
        "Mizan yüklenince stok hesaplarının sürekli / aralıklı envanterle izlendiği, üretim ve hizmet maliyeti "
        "olup olmadığı tanınır, SMM buna göre kurulur. Yalnız gerekirse sayım stoku ya da brüt kâr oranı ister.",
        "SMM = (150 + 151 + 152 + 153 mizan bakiyeleri − girilen dönem sonu stokları) + 710/720/730 üretim "
        "maliyetleri (→620) + 740 hizmet maliyeti (→622). Boş bırakılan stok mizan bakiyesinde kalır.",
        "SMM = Net satış × (1 − brüt kâr oranı). Dönem sonu stok = 150-153 mizan bakiyeleri + 710/720/730/740 "
        "− SMM; stok hesaplarına bakiyeleri oranında dağıtılır.",
        "SMM = Net satış × (1 − brüt kâr oranı). Dönem sonu stok = elle yazılan stok tutarı + 710/720/730/740 "
        "− SMM; miktar ortalama birim maliyetle bulunur."]

    def yontem_degisti(self, i):
        self.yontem_yigin.setCurrentIndex(i)
        self.yontem_aciklama.setText(self.ACIKLAMA[i])
        self.hesapla()

    @staticmethod
    def deger(w):
        s = w.text().strip()
        return mizan.sayi(s) if s else None

    def hesapla(self):
        if not self.hesaplar:
            return
        i = self.yontem.currentIndex()
        yontem = motor.YONTEMLER[i]
        marj = self.deger({0: self.marj_oto, 2: self.marj}.get(i, self.marj2))
        ds_w = {0: self.ds_oto, 1: self.ds}.get(i)
        ds_stok = {s: self.deger(w) for s, w in ds_w.items()} if ds_w else None
        eksik = ""
        if i == 1 and not any(v is not None for v in ds_stok.values()):
            eksik = "   ⚠ Dönem sonu stoklarını girin"
        elif i >= 2 and marj is None:
            eksik = "   ⚠ Brüt kâr oranını girin"
        elif i == 3 and self.deger(self.elle_tutar) is None:
            eksik = "   ⚠ Stok tutarını girin"
        if i >= 2 and eksik:  # oran / tutar yokken fiili envanter (mizan bakiyeleri) ile göster
            yontem, marj = "envanter", None
        self.sonuc = r = motor.hesapla(
            self.hesaplar, yontem=yontem, ds_stok=ds_stok, kar_marji=None if marj is None else marj / 100,
            elle_miktar=self.deger(self.elle_miktar), elle_tutar=self.deger(self.elle_tutar),
            istirak=self.deger(self.istirak), gecmis_zarar=self.deger(self.gyz) or 0.0,
            arge=self.deger(self.arge) or 0.0, bagis=self.deger(self.bagis) or 0.0,
            bagis_tam=self.deger(self.bagis_tam) or 0.0,
            fgk_istisna=mizan.sayi(self.istisna.text()), fgk_oran=mizan.sayi(self.oran.text()) / 100,
            vergi_orani=mizan.sayi(self.vergi.text()) / 100)
        dengede = r["fark"] == 0
        s = r["smm"]
        a = r["analiz"]
        for k, w in self.ds_oto.items():  # otomatikte yalnız gereken stok kutuları açık
            w.setEnabled(k in a["gerekli"])
        self.marj_oto.setEnabled(bool(a["gerekli"]))
        if i == 0:
            self.yontem_aciklama.setText(a["metin"][-1])
            if a.get("eksik"):
                eksik = "   ⚠ " + ", ".join(a["eksik"]) + " dönem sonu stoku veya brüt kâr oranı gerekli"
        self.durum.setText(f"{Path(self.dosya).name} — {len(self.hesaplar)} kebir hesap — " +
                           ("✔ BİLANÇO DENGEDE" if dengede else f"❌ DENGESİZ: {tl(r['fark'])}") +
                           ("" if eksik else f" — SMM {tl(s['smm'])} — Brüt kâr {tl(s['brut_kar'])}" +
                            (f" ({yuzde(s['brut_oran'])})" if s["brut_oran"] is not None else "")) + eksik)
        self.durum.setStyleSheet(f"font-weight:bold; padding:4px; color:{'#1b5e20' if dengede else '#b00020'}")
        self.goster(r)

    def goster(self, r):
        es = self.ham[2]
        uy = r["uyarilar"] + self.okuma_uyari
        self.tablolar["Kontrol"].setPlainText(
            "Okunan sütunlar: " + ", ".join(f"{mizan.ROL_AD[k]} = Sütun {v + 1}" for k, v in es.items()) +
            "\nBakiye her zaman Borç − Alacak'tan hesaplanır; alt hesaplar kebire toplanır, çift sayılmaz.\n\n" +
            "ENVANTER TANIMA (SMM yöntemi: " + r["analiz"]["secilen"] + "):\n• " + "\n• ".join(r["analiz"]["metin"]) +
            "\n\n" +
            ("UYARILAR:\n• " + "\n• ".join(uy) if uy else "Uyarı yok."))
        tablo_doldur(self.tablolar["Kebir Mizan"], ["Hesap Kodu", "Hesap Adı", "Bakiye (Borç − Alacak)"],
                     [("", [k, v["ad"], v["bakiye"]]) for k, v in sorted(self.hesaplar.items())])
        s = r["smm"]
        tablo_doldur(self.tablolar["Envanter ve SMM"], ["Kod", "Satışların Maliyeti Tablosu", "Tutar"],
                     [("" if tur == "kalem" else tur, [kod, ad, t]) for tur, kod, ad, t in r["envanter"]] +
                     [("ara", ["", "BRÜT KÂR ORANI (brüt kâr / net satış)",
                               yuzde(s["brut_oran"]) if s["brut_oran"] is not None else ""])])
        ns = r["net_satis"]
        tablo_doldur(self.tablolar["Gelir Tablosu"], ["Kod", "Gelir Tablosu Kalemleri", "Tutar (₺)", "Dikey Oran"],
                     [(tur, [kod, ad, t, yuzde(t / ns) if ns else ""]) for tur, kod, ad, t in r["gelir_tablosu"]])
        a, p = r["aktif"], r["pasif"]
        n = max(len(a), len(p))
        bos = ("", "", "", None)
        a = a[:-1] + [bos] * (n - len(a)) + a[-1:]  # toplamlar en alt satırda hizalansın
        p = p[:-1] + [bos] * (n - len(p)) + p[-1:]
        tablo_doldur(self.tablolar["Detaylı Bilanço"],
                     ["Kod", "AKTİF (VARLIKLAR)", "Tutar (₺)", "Kod", "PASİF (KAYNAKLAR)", "Tutar (₺)"],
                     [(x[0] or y[0], [x[1], x[2], x[3], y[1], y[2], y[3]]) for x, y in zip(a, p)])
        tablo_doldur(self.tablolar["FGK Hesaplama"], ["Adım", "Hesaplama Unsuru", "Tutar / Oran"],
                     [("ara" if n == "11" else "", [n, ad, yuzde(t) if n in ("6", "10") else t])
                      for n, ad, t in r["fgk"]])
        tablo_doldur(self.tablolar["Vergi ve Rasyolar"], ["Kalem", "Tutar / Oran"],
                     [("ara" if "TOPLAM" in ad or "MATRAH" in ad or "ÖDENECEK" in ad else "", [ad, t])
                      for ad, t in r["vergi"]] + [("bolum", ["FİNANSAL RASYOLAR", ""])] +
                     [("", [ad, "" if v is None else f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")])
                      for ad, v in r["rasyo"]])

    # --- dışa aktar ---
    def aktar(self):
        if not self.sonuc:
            return
        yol, _ = QFileDialog.getSaveFileName(self, "Excel'e aktar", str(Path(self.dosya).with_name(
            Path(self.dosya).stem + "_Mali_Tablolar.xlsx")), "Excel (*.xlsx)")
        if not yol:
            return
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        wb = Workbook()
        wb.remove(wb.active)
        for ad, w in self.tablolar.items():
            ws = wb.create_sheet(ad[:31])
            if isinstance(w, QTextEdit):
                for i, s in enumerate(w.toPlainText().splitlines(), 1):
                    ws.cell(i, 1, s)
                ws.column_dimensions["A"].width = 120
                continue
            for j in range(w.columnCount()):
                c = ws.cell(1, j + 1, w.horizontalHeaderItem(j).text())
                c.font = Font(bold=True)
                ws.column_dimensions[chr(65 + j)].width = 18 if j % 3 != 1 else 55
            for i in range(w.rowCount()):
                for j in range(w.columnCount()):
                    it = w.item(i, j)
                    if not it or not it.text():
                        continue
                    txt = it.text()
                    sayisal = bool(it.textAlignment() & Qt.AlignRight)
                    c = ws.cell(i + 2, j + 1, mizan.sayi(txt) if sayisal and not txt.startswith("%") else txt)
                    if sayisal:
                        c.number_format = "#,##0.00"
                    if it.font().bold():
                        c.font = Font(bold=True)
                        c.fill = PatternFill("solid", fgColor=it.background().color().name()[1:])
        try:
            wb.save(yol)
        except PermissionError:
            QMessageBox.critical(self, UYGULAMA, "Dosya kaydedilemedi (Excel'de açık olabilir).")
            return
        QMessageBox.information(self, UYGULAMA, f"Kaydedildi:\n{yol}")


class AnaPencere(QMainWindow):
    MODULLER = [("Mali Tablolar", "Mizan → Envanter/SMM, Gelir Tablosu,\nBilanço, FGK, Vergi", True)] + \
               [(f"Modül {i}", "Yakında", False) for i in range(2, 7)]

    def __init__(self):
        super().__init__()
        self.setWindowTitle(UYGULAMA)
        self.resize(1400, 850)
        self.yigin = QStackedWidget()
        self.setCentralWidget(self.yigin)

        ana = QWidget()
        lay = QVBoxLayout(ana)
        baslik = QLabel(UYGULAMA)
        baslik.setStyleSheet("font-size:40px; font-weight:bold; padding:20px")
        baslik.setAlignment(Qt.AlignCenter)
        lay.addWidget(baslik)
        grid = QGridLayout()
        for i, (ad, aciklama, aktif) in enumerate(self.MODULLER):
            b = QPushButton(f"{ad}\n\n{aciklama}")
            b.setMinimumSize(300, 150)
            b.setEnabled(aktif)
            b.setStyleSheet("font-size:16px")
            if aktif:
                b.clicked.connect(lambda: self.yigin.setCurrentIndex(1))
            grid.addWidget(b, i // 3, i % 3)
        lay.addLayout(grid)
        lay.addStretch()
        self.yigin.addWidget(ana)
        self.yigin.addWidget(MaliTablolar(lambda: self.yigin.setCurrentIndex(0)))


if __name__ == "__main__":
    uyg = QApplication(sys.argv)
    uyg.setApplicationName(UYGULAMA)
    p = AnaPencere()
    p.show()
    sys.exit(uyg.exec())
