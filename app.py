"""Başkan — masaüstü uygulaması. Modül 1: Mizan → Mali Tablolar."""
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                               QPushButton, QLabel, QLineEdit, QTabWidget, QTableWidget, QTableWidgetItem,
                               QFileDialog, QMessageBox, QStackedWidget, QDialog, QComboBox, QSpinBox,
                               QFormLayout, QDialogButtonBox, QHeaderView, QTextEdit)

import cikti
import kayit
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
    # 08.11 (Kenan Bey): elle ayarlanan sütun genişliği yeniden hesaplamada / sekme geçişinde bozulmasın →
    # yalnız İLK doldurmada boyutla; sonra kullanıcının genişliği kalır ve QSettings'te saklanır (açılışta geri gelir).
    if not tbl.property("genislik_ayarli"):
        ayar, anahtar = QSettings("Baskan", "Baskan"), f"sutun/{tbl.objectName() or 'tablo'}"
        kayitli = ayar.value(anahtar) or []
        if len(kayitli) == tbl.columnCount():
            for j, g in enumerate(kayitli):
                tbl.setColumnWidth(j, int(g))
        else:
            tbl.resizeColumnsToContents()
        tbl.setProperty("genislik_ayarli", True)
        tbl.horizontalHeader().sectionResized.connect(
            lambda *_: ayar.setValue(anahtar, [tbl.columnWidth(j) for j in range(tbl.columnCount())]))


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


class KiyasPencere(QDialog):
    """İki dönemin gelir tablosu, bilanço ve vergi/rasyoları yan yana: 1. dönem | 2. dönem | fark | değişim."""

    def __init__(self, ad1, ad2, k, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Karşılaştırma: {ad1}  →  {ad2}")
        self.resize(1250, 800)
        self.k, self.ad1, self.ad2 = k, ad1, ad2
        lay = QVBoxLayout(self)
        ust = QHBoxLayout()
        ust.addWidget(QLabel(f"<b>1:</b> {ad1} &nbsp;&nbsp; <b>2:</b> {ad2}"))
        ust.addStretch()
        b = QPushButton("Excel'e Aktar…")
        b.clicked.connect(self.aktar)
        ust.addWidget(b)
        lay.addLayout(ust)
        sek = QTabWidget()
        self.basliklar = ["Kod", "Kalem", ad1, ad2, "Fark", "Değişim"]
        for ad, anahtar in (("Gelir Tablosu", "gelir"), ("Bilanço", "bilanco"), ("Vergi ve Rasyolar", "ozet")):
            t = QTableWidget()
            t.setObjectName("kiyas-" + anahtar)
            tablo_doldur(t, self.basliklar, [(tur, [kod, ad_, a, b_, f, yuzde(o)]) for tur, kod, ad_, a, b_, f, o in k[anahtar]])
            sek.addTab(t, ad)
        lay.addWidget(sek)

    def aktar(self):
        yol, _ = QFileDialog.getSaveFileName(self, "Excel'e aktar", "Karsilastirma.xlsx", "Excel (*.xlsx)")
        if not yol:
            return
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        wb = Workbook()
        wb.remove(wb.active)
        for ad, anahtar in (("Gelir Tablosu", "gelir"), ("Bilanço", "bilanco"), ("Vergi ve Rasyolar", "ozet")):
            ws = wb.create_sheet(ad)
            ws.append(self.basliklar)
            for c in ws[1]:
                c.font = Font(bold=True)
            for n, (tur, kod, ad_, a, b_, f, o) in enumerate(self.k[anahtar], 2):
                ws.append([kod, ad_, a, b_, f"=IF(AND(C{n}=\"\",D{n}=\"\"),\"\",N(D{n})-N(C{n}))",
                           f"=IF(N(C{n})=0,\"\",E{n}/ABS(C{n}))"])
                for j in (3, 4, 5):
                    ws.cell(n, j).number_format = "#,##0.00;[Red]-#,##0.00"
                ws.cell(n, 6).number_format = "0.0%"
                if tur in RENK:
                    for j in range(1, 7):
                        ws.cell(n, j).font = Font(bold=True)
                        ws.cell(n, j).fill = PatternFill("solid", fgColor=RENK[tur][1:])
            for j, g in enumerate((10, 50, 18, 18, 18, 10), 1):
                ws.column_dimensions[chr(64 + j)].width = g
        try:
            wb.save(yol)
        except PermissionError:
            QMessageBox.critical(self, UYGULAMA, "Dosya kaydedilemedi (Excel'de açık olabilir).")
            return
        QMessageBox.information(self, UYGULAMA, f"Kaydedildi:\n{yol}")


class MaliTablolar(QWidget):
    def __init__(self, ana_sayfaya):
        super().__init__()
        self.hesaplar, self.ham, self.okuma_uyari, self.sonuc, self.dosya = None, None, [], None, None
        lay = QVBoxLayout(self)

        ust = QHBoxLayout()
        for ad, fn in (("← Ana Sayfa", ana_sayfaya), ("Mizan Yükle…", self.yukle),
                       ("Sütunları Düzelt…", self.esle), ("Excel'e Aktar (formüllü)…", self.aktar),
                       ("Yazdır…", self.yazdir), ("PDF'e Kaydet…", self.pdf)):
            b = QPushButton(ad)
            b.clicked.connect(fn)
            ust.addWidget(b)
        ust.addStretch()
        lay.addLayout(ust)

        # 08.11 (Kenan Bey): birden çok firma, dönem kaydı, eski dönemleri açma, iki dönem karşılaştırma
        fd = QHBoxLayout()
        fd.addWidget(QLabel("Firma:"))
        self.firma = QComboBox()
        self.firma.setEditable(True)
        self.firma.setMinimumWidth(220)
        self.firma.lineEdit().setPlaceholderText("firma adı")
        fd.addWidget(self.firma)
        fd.addWidget(QLabel("Dönem:"))
        self.donem = QLineEdit()
        self.donem.setPlaceholderText("örn. 2026/09 ya da 2026-3. çeyrek")
        self.donem.setFixedWidth(200)
        fd.addWidget(self.donem)
        for ad, fn in (("Kaydet", self.kaydet), ("Kayıtlı Dönemler…", self.kayitlar), ("İki Dönemi Karşılaştır…", self.karsilastir)):
            b = QPushButton(ad)
            b.clicked.connect(fn)
            fd.addWidget(b)
        fd.addStretch()
        lay.addLayout(fd)
        self.firmalari_yenile()

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
        self.marj = alan("örn. 25", 60)            # 150 grubu (150-152 + üretim)
        self.marj153 = alan("örn. 20", 60)         # 153 ticari mal
        self.ticari_satis = alan("boşsa maliyet payı", 130)
        self.ds150m = alan("veya stok ₺", 120)     # 08.11: oran yerine dönem sonu stok (doluysa o kullanılır)
        self.ds153m = alan("veya stok ₺", 120)
        self.marj2 = alan("örn. 25", 60)
        self.elle_miktar = alan("adet / kg", 110)
        self.elle_tutar = alan("örn. 400.000.000,00", 150)
        sayfalar = [[(f"{s} DS ₺:", self.ds_oto[s]) for s in motor.STOK] + [("veya brüt kâr %:", self.marj_oto)],
                    [(f"{s} {ad.split(' -')[0].title()} DS ₺:", self.ds[s]) for s, ad in motor.STOK.items()],
                    [("150 grubu (mamul) kâr %:", self.marj), ("ya da DS ₺:", self.ds150m),
                     ("153 ticari mal kâr %:", self.marj153), ("ya da DS ₺:", self.ds153m),
                     ("153 satışı ₺:", self.ticari_satis)],
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
            w.setObjectName(ad)
            if ad == "Kontrol":
                w.setReadOnly(True)
            self.tablolar[ad] = w
            self.sekme.addTab(w, ad)
        lay.addWidget(self.sekme, 1)   # boş yükseklik tablolara gitsin (giriş satırları arasında boşluk açılmasın)

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
        "150 grubu ve 153 için ayrı ayrı: dönem sonu stok (DS) doluysa SMM = satılabilir maliyet − DS, boşsa brüt kâr oranı: "
        "her grubun SMM'si = o grubun satışı × (1 − oranı), dönem sonu stok = satılabilir maliyet − SMM. Ticari mal "
        "satışı boşsa net satış grupların satılabilir maliyeti oranında bölünür. Tek oran girerseniz ikisine de uygulanır.",
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

    def parametreler(self):
        """Ekrandaki girdilerden motor.hesapla parametreleri → (kwargs, eksik uyarısı). Kayıtta da bu saklanır."""
        i = self.yontem.currentIndex()
        yontem = motor.YONTEMLER[i]
        marj = self.deger(self.marj_oto) if i == 0 else self.deger(self.marj2) if i == 3 else None
        ds_w = {0: self.ds_oto, 1: self.ds}.get(i)
        ds_stok = {s: self.deger(w) for s, w in ds_w.items()} if ds_w else None
        eksik = ""
        if i == 2:  # 150 / 153: stok doluysa stoktan, boşsa orandan; oranı da boş grup diğer oranı alır
            m150, m153 = self.deger(self.marj), self.deger(self.marj153)
            s150, s153 = self.deger(self.ds150m), self.deger(self.ds153m)
            if s150 is None and m150 is None:
                m150 = m153
            if s153 is None and m153 is None:
                m153 = m150
            marj = {"150": m150, "153": m153}
            ds_stok = {"150": s150, "153": s153}
            if all(v is None for v in (m150, m153, s150, s153)):
                eksik = "   ⚠ 150 / 153 için brüt kâr oranı ya da dönem sonu stok girin"
        elif i == 1 and not any(v is not None for v in ds_stok.values()):
            eksik = "   ⚠ Dönem sonu stoklarını girin"
        elif i == 3 and marj is None:
            eksik = "   ⚠ Brüt kâr oranını girin"
        elif i == 3 and self.deger(self.elle_tutar) is None:
            eksik = "   ⚠ Stok tutarını girin"
        if i >= 2 and eksik:  # oran / tutar yokken fiili envanter (mizan bakiyeleri) ile göster
            yontem, marj, ds_stok = "envanter", None, None
        kar = None if marj is None else (
            {k: (None if v is None else v / 100) for k, v in marj.items()} if isinstance(marj, dict) else marj / 100)
        kw = dict(yontem=yontem, ds_stok=ds_stok, kar_marji=kar,
                  ticari_satis=self.deger(self.ticari_satis) if i == 2 else None,
                  elle_miktar=self.deger(self.elle_miktar), elle_tutar=self.deger(self.elle_tutar),
                  istirak=self.deger(self.istirak), gecmis_zarar=self.deger(self.gyz) or 0.0,
                  arge=self.deger(self.arge) or 0.0, bagis=self.deger(self.bagis) or 0.0,
                  bagis_tam=self.deger(self.bagis_tam) or 0.0,
                  fgk_istisna=mizan.sayi(self.istisna.text()), fgk_oran=mizan.sayi(self.oran.text()) / 100,
                  vergi_orani=mizan.sayi(self.vergi.text()) / 100)
        return kw, eksik

    def hesapla(self):
        if not self.hesaplar or getattr(self, "_yukleniyor", False):
            return
        i = self.yontem.currentIndex()
        kw, eksik = self.parametreler()
        try:
            self.sonuc = r = motor.hesapla(self.hesaplar, **kw)
        except ValueError as e:   # ör. bir grup için ne oran ne stok girilmiş
            self.durum.setText(f"⚠ {e}")
            self.durum.setStyleSheet("font-weight:bold; padding:4px; color:#b00020")
            return
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
        self.durum.setText(f"{self.etiket()} — {len(self.hesaplar)} kebir hesap — " +
                           ("✔ BİLANÇO DENGEDE" if dengede else f"❌ DENGESİZ: {tl(r['fark'])}") +
                           ("" if eksik else f" — SMM {tl(s['smm'])} — Brüt kâr {tl(s['brut_kar'])}" +
                            (f" ({yuzde(s['brut_oran'])})" if s["brut_oran"] is not None else "")) + eksik)
        self.durum.setStyleSheet(f"font-weight:bold; padding:4px; color:{'#1b5e20' if dengede else '#b00020'}")
        self.goster(r)

    def goster(self, r):
        es = self.ham[2] if self.ham else {}
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

    # --- firma / dönem kayıtları (08.11) ---
    GIRDI_ALANLARI = ("marj_oto", "marj", "marj153", "ticari_satis", "ds150m", "ds153m", "marj2", "elle_miktar",
                      "elle_tutar", "istisna", "oran", "vergi", "istirak", "gyz", "arge", "bagis", "bagis_tam")

    def etiket(self):
        f, d = self.firma.currentText().strip(), self.donem.text().strip()
        return f"{f} · {d}" if f and d else (Path(self.dosya).name if self.dosya else "")

    def firmalari_yenile(self):
        secili = self.firma.currentText()
        self.firma.blockSignals(True)
        self.firma.clear()
        self.firma.addItems(sorted({f for f, *_ in kayit.liste()}, key=str.lower))
        self.firma.setEditText(secili)
        self.firma.blockSignals(False)

    def girdiler(self):
        g = {a: getattr(self, a).text() for a in self.GIRDI_ALANLARI}
        g.update({f"ds{s}": w.text() for s, w in self.ds.items()})
        g.update({f"ds_oto{s}": w.text() for s, w in self.ds_oto.items()})
        g["yontem"] = self.yontem.currentIndex()
        return g

    def girdileri_yaz(self, g):
        self._yukleniyor = True   # her setText yeniden hesaplamasın
        try:
            for a in self.GIRDI_ALANLARI:
                getattr(self, a).setText(g.get(a, ""))
            for s, w in self.ds.items():
                w.setText(g.get(f"ds{s}", ""))
            for s, w in self.ds_oto.items():
                w.setText(g.get(f"ds_oto{s}", ""))
            self.yontem.setCurrentIndex(int(g.get("yontem", 0)))
        finally:
            self._yukleniyor = False

    def kaydet(self):
        if not self.hesaplar:
            QMessageBox.warning(self, UYGULAMA, "Önce bir mizan yükleyin.")
            return
        f, d = self.firma.currentText().strip(), self.donem.text().strip()
        if not f or not d:
            QMessageBox.warning(self, UYGULAMA, "Firma adını ve dönemi yazın (örn. 2026/09).")
            return
        var = any(ff == f and dd == d for ff, dd, *_ in kayit.liste())
        if var and QMessageBox.question(self, UYGULAMA, f"{f} · {d} zaten kayıtlı. Üzerine yazılsın mı?") != QMessageBox.Yes:
            return
        kw, _ = self.parametreler()
        g = self.girdiler()
        g["_parametreler"] = kw
        yol = kayit.kaydet(f, d, self.hesaplar, g, str(self.dosya or ""))
        self.firmalari_yenile()
        self.durum.setText(f"✔ Kaydedildi: {f} · {d}  ({yol})")

    def kayit_ac(self, yol):
        v = kayit.oku(yol)
        self.hesaplar, self.okuma_uyari, self.ham = v["hesaplar"], [], None
        self.dosya = v.get("kaynak_dosya") or f"{v['firma']}.xlsx"
        self.firma.setEditText(v["firma"])
        self.donem.setText(v["donem"])
        self.girdileri_yaz(v.get("girdiler", {}))
        self.hesapla()

    def kayitlar(self):
        l = kayit.liste()
        if not l:
            QMessageBox.information(self, UYGULAMA, f"Henüz kayıtlı dönem yok.\nKayıt klasörü: {kayit.KOK}")
            return
        d = QDialog(self)
        d.setWindowTitle("Kayıtlı dönemler")
        d.resize(620, 420)
        lay = QVBoxLayout(d)
        lay.addWidget(QLabel(f"Kayıt klasörü: {kayit.KOK}"))
        t = QTableWidget(len(l), 3)
        t.setHorizontalHeaderLabels(["Firma", "Dönem", "Kaydedilme"])
        for i, (f, dn, tarih, _) in enumerate(l):
            for j, x in enumerate((f, dn, tarih)):
                it = QTableWidgetItem(x)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                t.setItem(i, j, it)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        t.resizeColumnsToContents()
        t.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(t)
        alt = QHBoxLayout()
        for ad, fn in (("Aç", lambda: (self.kayit_ac(l[t.currentRow()][3]), d.accept()) if t.currentRow() >= 0 else None),
                       ("Sil", lambda: self._kayit_sil(l, t, d))):
            b = QPushButton(ad)
            b.clicked.connect(fn)
            alt.addWidget(b)
        t.doubleClicked.connect(lambda *_: (self.kayit_ac(l[t.currentRow()][3]), d.accept()))
        alt.addStretch()
        lay.addLayout(alt)
        d.exec()

    def _kayit_sil(self, l, t, d):
        i = t.currentRow()
        if i < 0:
            return
        f, dn, _, yol = l[i]
        if QMessageBox.question(self, UYGULAMA, f"{f} · {dn} kaydı silinsin mi?") == QMessageBox.Yes:
            kayit.sil(yol)
            self.firmalari_yenile()
            d.accept()
            self.kayitlar()

    def karsilastir(self):
        l = kayit.liste()
        if len(l) < 2:
            QMessageBox.information(self, UYGULAMA, "Karşılaştırma için en az iki kayıtlı dönem gerekir (Kaydet ile ekleyin).")
            return
        d = QDialog(self)
        d.setWindowTitle("İki dönemi karşılaştır")
        form = QFormLayout(d)
        adlar = [f"{f} · {dn}" for f, dn, *_ in l]
        c1, c2 = QComboBox(), QComboBox()
        c1.addItems(adlar)
        c2.addItems(adlar)
        c1.setCurrentIndex(max(0, len(l) - 2))
        c2.setCurrentIndex(len(l) - 1)
        form.addRow("1. dönem (eski):", c1)
        form.addRow("2. dönem (yeni):", c2)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        form.addRow(bb)
        if not d.exec():
            return
        try:
            r = []
            for c in (c1, c2):
                v = kayit.oku(l[c.currentIndex()][3])
                r.append(motor.hesapla(v["hesaplar"], **v.get("girdiler", {}).get("_parametreler", {})))
        except (ValueError, TypeError) as e:
            QMessageBox.critical(self, UYGULAMA, f"Karşılaştırma hesaplanamadı: {e}")
            return
        KiyasPencere(adlar[c1.currentIndex()], adlar[c2.currentIndex()], kayit.karsilastir(*r), self).show()

    # --- dışa aktar ---
    def aktar(self):
        if not self.sonuc:
            return
        yol, _ = QFileDialog.getSaveFileName(self, "Excel'e aktar", str(Path(self.dosya).with_name(
            Path(self.dosya).stem + "_Mali_Tablolar.xlsx")), "Excel (*.xlsx)")
        if not yol:
            return
        try:
            cikti.excel_formullu(self.sonuc, self.hesaplar, yol, self.tablolar["Kontrol"].toPlainText())
        except PermissionError:
            QMessageBox.critical(self, UYGULAMA, "Dosya kaydedilemedi (Excel'de açık olabilir).")
            return
        QMessageBox.information(self, UYGULAMA, f"Kaydedildi (toplam ve ara satırlar formüllü, kalemler "
                                                f"'Kebir Mizan' sayfasına bağlı):\n{yol}")

    def _belge(self):
        from PySide6.QtGui import QTextDocument
        d = QTextDocument()
        d.setHtml(cikti.rapor_html(self.sonuc, Path(self.dosya).stem))
        return d

    def yazdir(self):
        if not self.sonuc:
            return
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        p = QPrinter(QPrinter.HighResolution)
        if QPrintDialog(p, self).exec():
            self._belge().print_(p)

    def pdf(self):
        if not self.sonuc:
            return
        from PySide6.QtPrintSupport import QPrinter
        yol, _ = QFileDialog.getSaveFileName(self, "PDF'e kaydet", str(Path(self.dosya).with_name(
            Path(self.dosya).stem + "_Mali_Tablolar.pdf")), "PDF (*.pdf)")
        if not yol:
            return
        p = QPrinter(QPrinter.HighResolution)
        p.setOutputFormat(QPrinter.PdfFormat)
        p.setOutputFileName(yol)
        self._belge().print_(p)
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
