"""Modül 3 — E-Fatura → Muhasebe Fişi (08.11.2026, Kenan Bey).

Entegratörlerin (Uyumsoft, İzibiz, QNB eFinans, Logo…) ve GİB portalının hepsinin verdiği ortak biçim UBL-TR XML'dir:
faturalar XML ya da ZIP olarak yüklenir, seçili firmanın VKN'sine göre ALIŞ / SATIŞ / İADE ayrılır, KDV ve tevkifat
ayrıştırılır, her fatura için dengeli bir yevmiye fişi üretilir ve muhasebe programlarının "Excel'den fiş aktarma"
ekranına uygun sütunlarla dışa aktarılır. (Portallara otomatik giriş YOK: SGK / Dijital VD güvenlik kodu ister.)
"""
import io
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
      "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"}
VARSAYILAN_HESAP = {"alis": "153", "satis": "600", "kdv_indirilecek": "191", "kdv_hesaplanan": "391",
                    "satici": "320", "alici": "120", "tevkifat": "360", "satis_iade": "610"}
HESAP_AD = {"alis": "Alış (gider / stok)", "satis": "Satış", "kdv_indirilecek": "İndirilecek KDV",
            "kdv_hesaplanan": "Hesaplanan KDV", "satici": "Satıcılar (cari)", "alici": "Alıcılar (cari)",
            "tevkifat": "Ödenecek tevkifat KDV", "satis_iade": "Satıştan iadeler"}


def _t(el, yol, vars_=None):
    x = el.find(yol, NS) if el is not None else None
    return (x.text or "").strip() if x is not None and x.text else vars_


def _f(el, yol):
    try:
        return float(_t(el, yol, "0").replace(",", "."))
    except ValueError:
        return 0.0


def _taraf(parti):
    p = parti.find("cac:Party", NS) if parti is not None else None
    kimlik = ""
    for pid in (p.findall("cac:PartyIdentification/cbc:ID", NS) if p is not None else []):
        if pid.get("schemeID") in ("VKN", "TCKN") and pid.text:
            kimlik = pid.text.strip()
    ad = _t(p, "cac:PartyName/cbc:Name") or " ".join(
        x for x in (_t(p, "cac:Person/cbc:FirstName"), _t(p, "cac:Person/cbc:FamilyName")) if x)
    return kimlik, ad or "?"


def fatura_oku(xml_bayt, kaynak=""):
    """UBL-TR fatura XML → sözlük (tutarlar TL'ye çevrilmiş)."""
    k = ET.fromstring(xml_bayt)
    if not k.tag.endswith("Invoice"):
        raise ValueError("UBL Invoice değil")
    sv, sa = _taraf(k.find("cac:AccountingSupplierParty", NS))
    av, aa = _taraf(k.find("cac:AccountingCustomerParty", NS))
    kdv, kdv_oran, diger_vergi = 0.0, {}, 0.0
    for alt in k.findall("cac:TaxTotal/cac:TaxSubtotal", NS):
        tutar, kod = _f(alt, "cbc:TaxAmount"), _t(alt, "cac:TaxCategory/cac:TaxScheme/cbc:TaxTypeCode", "")
        if kod == "0015":
            kdv += tutar
            oran = _t(alt, "cbc:Percent", "?")
            kdv_oran[oran] = kdv_oran.get(oran, 0.0) + tutar
        else:
            diger_vergi += tutar   # ÖTV, ÖİV vb. → maliyete / satışa eklenir
    tevkifat = sum(_f(w, "cbc:TaxAmount") for w in k.findall("cac:WithholdingTaxTotal", NS))
    lmt = k.find("cac:LegalMonetaryTotal", NS)
    matrah = _f(lmt, "cbc:TaxExclusiveAmount") or _f(lmt, "cbc:LineExtensionAmount")
    doviz = _t(k, "cbc:DocumentCurrencyCode", "TRY")
    kur = 1.0
    uyari = []
    if doviz not in ("TRY", "TL"):
        kur = _f(k, "cac:PricingExchangeRate/cbc:CalculationRate") or 0.0
        if not kur:
            uyari.append(f"{doviz} faturada kur yok — tutarlar dövizdir, elle çevirin")
            kur = 1.0
    return {"no": _t(k, "cbc:ID", "?"), "ettn": _t(k, "cbc:UUID", ""), "tarih": _t(k, "cbc:IssueDate", ""),
            "tip": _t(k, "cbc:InvoiceTypeCode", "SATIS").upper(), "profil": _t(k, "cbc:ProfileID", ""),
            "satici_vkn": sv, "satici": sa, "alici_vkn": av, "alici": aa, "doviz": doviz, "kur": kur,
            "matrah": round((matrah + diger_vergi) * kur, 2), "diger_vergi": round(diger_vergi * kur, 2),
            "kdv": round(kdv * kur, 2), "kdv_oran": {o: round(v * kur, 2) for o, v in kdv_oran.items()},
            "tevkifat": round(tevkifat * kur, 2), "kaynak": kaynak, "uyari": uyari}


def dosyalardan_oku(yollar):
    """XML ya da ZIP (içinde XML) dosyaları → (faturalar, hatalar). Aynı ETTN ikinci kez alınmaz."""
    faturalar, hatalar, gorulen = [], [], set()

    def ekle(bayt, ad):
        try:
            f = fatura_oku(bayt, ad)
        except (ET.ParseError, ValueError) as e:
            hatalar.append(f"{ad}: {e}")
            return
        anahtar = f["ettn"] or (f["satici_vkn"], f["no"])
        if anahtar in gorulen:
            return
        gorulen.add(anahtar)
        faturalar.append(f)

    for y in map(Path, yollar):
        if y.suffix.lower() == ".zip":
            with zipfile.ZipFile(y) as z:
                for ad in z.namelist():
                    if ad.lower().endswith(".xml"):
                        ekle(z.read(ad), f"{y.name}/{ad}")
                    elif ad.lower().endswith(".zip"):   # bazı portallar zip içinde zip verir
                        with zipfile.ZipFile(io.BytesIO(z.read(ad))) as z2:
                            for ad2 in z2.namelist():
                                if ad2.lower().endswith(".xml"):
                                    ekle(z2.read(ad2), f"{y.name}/{ad}/{ad2}")
        else:
            ekle(y.read_bytes(), y.name)
    return sorted(faturalar, key=lambda f: (f["tarih"], f["no"])), hatalar


def yon(f, firma_vkn):
    """Firmanın bakışıyla: alis / satis / alis_iade (firma satıcıya iade etti) / satis_iade / yabanci."""
    iade = f["tip"] == "IADE"
    if f["alici_vkn"] == firma_vkn:
        return "satis_iade" if iade else "alis"
    if f["satici_vkn"] == firma_vkn:
        return "alis_iade" if iade else "satis"
    return "yabanci"


def fis(f, firma_vkn, h=None):
    """Bir fatura → dengeli fiş satırları [(hesap, açıklama, borç, alacak)] ve uyarılar."""
    h = {**VARSAYILAN_HESAP, **(h or {})}
    y = yon(f, firma_vkn)
    m, kdv, tev = f["matrah"], f["kdv"], f["tevkifat"]
    toplam = m + kdv - tev
    cari = f["satici"] if y in ("alis", "satis_iade") else f["alici"]
    ac = f"{f['no']} {cari}"[:60]
    s, uy = [], list(f["uyari"])
    if y == "alis":
        s = [(h["alis"], ac, m, 0), (h["kdv_indirilecek"], ac, kdv, 0), (h["satici"], ac, 0, toplam)]
        if tev:
            s.append((h["tevkifat"], ac + " tevkifat", 0, tev))
    elif y == "satis":
        s = [(h["alici"], ac, toplam, 0), (h["satis"], ac, 0, m), (h["kdv_hesaplanan"], ac, 0, kdv - tev)]
        if tev:
            uy.append("tevkifatlı satış: 391'e KDV − tevkifat yazıldı, beyanname ile kontrol edin")
    elif y == "satis_iade":    # müşteriden gelen iade faturası
        s = [(h["satis_iade"], ac, m, 0), (h["kdv_indirilecek"], ac, kdv, 0), (h["alici"], ac, 0, m + kdv)]
    elif y == "alis_iade":     # satıcıya kestiğimiz iade faturası
        s = [(h["satici"], ac, m + kdv, 0), (h["alis"], ac, 0, m), (h["kdv_hesaplanan"], ac, 0, kdv)]
    else:
        uy.append("fatura bu firmaya ait değil (satıcı ya da alıcı VKN'si eşleşmiyor) — fişe alınmadı")
    s = [x for x in s if abs(x[2]) >= 0.005 or abs(x[3]) >= 0.005]
    if abs(sum(x[2] for x in s) - sum(x[3] for x in s)) >= 0.01:
        uy.append("fiş dengesiz")
    return y, s, uy


def fis_excel(faturalar, firma_vkn, yol, h=None, ilk_fis_no=1):
    """Muhasebe programlarının Excel'den fiş aktarma ekranları için: her satır bir fiş kalemi."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Fiş"
    ws.append(["Fiş No", "Fiş Tarihi", "Hesap Kodu", "Açıklama", "Borç", "Alacak", "Evrak No", "Evrak Tarihi",
               "Cari VKN", "Cari Unvan", "ETTN", "Uyarı"])
    no, alinan = ilk_fis_no, 0
    for f in faturalar:
        y, satirlar, uy = fis(f, firma_vkn, h)
        if y == "yabanci":
            continue
        cari_vkn, cari = (f["satici_vkn"], f["satici"]) if y in ("alis", "satis_iade") else (f["alici_vkn"], f["alici"])
        for hesap, ac, b, a in satirlar:
            ws.append([no, f["tarih"], hesap, ac, round(b, 2) or None, round(a, 2) or None, f["no"], f["tarih"],
                       cari_vkn, cari, f["ettn"], "; ".join(uy)])
        no += 1
        alinan += 1
    for c in ws[1]:
        c.font = Font(bold=True)
    for sut, g in zip("ABCDEFGHIJKL", (8, 12, 12, 40, 15, 15, 18, 12, 13, 35, 38, 40)):
        ws.column_dimensions[sut].width = g
    for r in ws.iter_rows(min_row=2, min_col=5, max_col=6):
        for c in r:
            c.number_format = "#,##0.00"
    n = ws.max_row + 1
    ws.cell(n, 4, "TOPLAM").font = Font(bold=True)
    ws.cell(n, 5, f"=SUM(E2:E{n - 1})").number_format = "#,##0.00"
    ws.cell(n, 6, f"=SUM(F2:F{n - 1})").number_format = "#,##0.00"
    wb.save(yol)
    return alinan


ORNEK_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
 <cbc:ProfileID>TICARIFATURA</cbc:ProfileID><cbc:ID>{no}</cbc:ID><cbc:UUID>{ettn}</cbc:UUID>
 <cbc:IssueDate>2026-11-05</cbc:IssueDate><cbc:InvoiceTypeCode>{tip}</cbc:InvoiceTypeCode>
 <cbc:DocumentCurrencyCode>TRY</cbc:DocumentCurrencyCode>
 <cac:AccountingSupplierParty><cac:Party><cac:PartyIdentification><cbc:ID schemeID="VKN">{sv}</cbc:ID>
  </cac:PartyIdentification><cac:PartyName><cbc:Name>{sa}</cbc:Name></cac:PartyName></cac:Party></cac:AccountingSupplierParty>
 <cac:AccountingCustomerParty><cac:Party><cac:PartyIdentification><cbc:ID schemeID="VKN">{av}</cbc:ID>
  </cac:PartyIdentification><cac:PartyName><cbc:Name>{aa}</cbc:Name></cac:PartyName></cac:Party></cac:AccountingCustomerParty>
 <cac:TaxTotal><cbc:TaxAmount currencyID="TRY">{kdv}</cbc:TaxAmount><cac:TaxSubtotal>
  <cbc:TaxableAmount currencyID="TRY">{m}</cbc:TaxableAmount><cbc:TaxAmount currencyID="TRY">{kdv}</cbc:TaxAmount>
  <cbc:Percent>20</cbc:Percent><cac:TaxCategory><cac:TaxScheme><cbc:Name>KDV</cbc:Name><cbc:TaxTypeCode>0015</cbc:TaxTypeCode>
  </cac:TaxScheme></cac:TaxCategory></cac:TaxSubtotal></cac:TaxTotal>
 {tev}
 <cac:LegalMonetaryTotal><cbc:LineExtensionAmount currencyID="TRY">{m}</cbc:LineExtensionAmount>
  <cbc:TaxExclusiveAmount currencyID="TRY">{m}</cbc:TaxExclusiveAmount>
  <cbc:PayableAmount currencyID="TRY">{od}</cbc:PayableAmount></cac:LegalMonetaryTotal>
</Invoice>"""


def ornek(no, sv, sa, av, aa, m, tip="SATIS", tevkifat=0.0):
    tev = (f'<cac:WithholdingTaxTotal><cbc:TaxAmount currencyID="TRY">{tevkifat}</cbc:TaxAmount></cac:WithholdingTaxTotal>'
           if tevkifat else "")
    return ORNEK_XML.format(no=no, ettn=f"ettn-{no}", tip=tip, sv=sv, sa=sa, av=av, aa=aa, m=m, kdv=m * 0.2,
                            tev=tev, od=m * 1.2 - tevkifat).encode()


def sina():
    import tempfile
    BIZ = "1111111111"
    d = Path(tempfile.mkdtemp())
    (d / "satis.xml").write_bytes(ornek("SAT2026000000001", BIZ, "BİZ A.Ş.", "2222222222", "Müşteri Ltd.", 1000.0))
    with zipfile.ZipFile(d / "gelen.zip", "w") as z:
        z.writestr("a.xml", ornek("ALI2026000000007", "3333333333", "Tedarikçi A.Ş.", BIZ, "BİZ A.Ş.", 500.0,
                                  tip="TEVKIFAT", tevkifat=50.0))
        z.writestr("b.xml", ornek("IAD2026000000002", "2222222222", "Müşteri Ltd.", BIZ, "BİZ A.Ş.", 100.0, tip="IADE"))
        z.writestr("c.xml", ornek("SAT2026000000001", BIZ, "BİZ A.Ş.", "2222222222", "Müşteri Ltd.", 1000.0))  # tekrar
        z.writestr("bozuk.xml", b"<bozuk")
    fs, hata = dosyalardan_oku([d / "satis.xml", d / "gelen.zip"])
    assert len(fs) == 3 and len(hata) == 1, (len(fs), hata)
    yonler = {f["no"]: fis(f, BIZ) for f in fs}
    y, s, _ = yonler["SAT2026000000001"]
    assert y == "satis" and s == [("120", s[0][1], 1200.0, 0), ("600", s[1][1], 0, 1000.0), ("391", s[2][1], 0, 200.0)]
    y, s, _ = yonler["ALI2026000000007"]   # tevkifatlı alış: 153 500 + 191 100 = 320 550 + 360 50
    assert y == "alis" and [(x[0], x[2], x[3]) for x in s] == [("153", 500.0, 0), ("191", 100.0, 0), ("320", 0, 550.0), ("360", 0, 50.0)]
    y, s, _ = yonler["IAD2026000000002"]   # müşteriden gelen iade: 610 + 191 / 120
    assert y == "satis_iade" and [(x[0], x[2], x[3]) for x in s] == [("610", 100.0, 0), ("191", 20.0, 0), ("120", 0, 120.0)]
    for y, s, uy in yonler.values():
        assert "fiş dengesiz" not in uy
    assert fis_excel(fs, BIZ, d / "fis.xlsx") == 3
    print("faturalar sına: tamam")


if __name__ == "__main__":
    sina()


# ---------------- arayüz ----------------
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,  # noqa: E402
                               QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from PySide6.QtCore import Qt  # noqa: E402

import firmalar  # noqa: E402

YON_AD = {"alis": "Alış", "satis": "Satış", "satis_iade": "Satıştan iade", "alis_iade": "Alıştan iade",
          "yabanci": "Bu firmaya ait değil"}


def _tl(x):
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class FaturaModulu(QWidget):
    def __init__(self, ana_sayfaya):
        super().__init__()
        self.faturalar = []
        lay = QVBoxLayout(self)
        ust = QHBoxLayout()
        for ad, fn in (("← Ana Sayfa", ana_sayfaya), ("Fatura XML / ZIP Yükle…", self.yukle),
                       ("Fişi Excel'e Aktar…", self.fis_aktar), ("Fatura Listesini Excel'e…", self.liste_aktar)):
            b = QPushButton(ad)
            b.clicked.connect(fn)
            ust.addWidget(b)
        ust.addWidget(QLabel("Firma:"))
        self.firma = QComboBox()
        self.firma.setMinimumWidth(280)
        self.firma.currentIndexChanged.connect(self.firma_degisti)
        ust.addWidget(self.firma)
        ust.addStretch()
        lay.addLayout(ust)

        hl = QHBoxLayout()
        hl.addWidget(QLabel("Hesap kodları:"))
        self.hesap = {}
        for k, v in VARSAYILAN_HESAP.items():
            hl.addWidget(QLabel(HESAP_AD[k] + ":"))
            w = QLineEdit(v)
            w.setFixedWidth(70)
            w.editingFinished.connect(self.hesap_kaydet)
            self.hesap[k] = w
            hl.addWidget(w)
        hl.addStretch()
        lay.addLayout(hl)
        self.durum = QLabel("Entegratör ya da GİB portalından indirdiğiniz e-fatura / e-arşiv XML'lerini (ya da ZIP) "
                            "yükleyin. Firma VKN'sine göre alış / satış ayrılır, her fatura için fiş üretilir.")
        self.durum.setWordWrap(True)
        lay.addWidget(self.durum)

        bol = QSplitter(Qt.Vertical)
        self.tablo = QTableWidget()
        self.tablo.setObjectName("faturalar")
        self.tablo.itemSelectionChanged.connect(self.fis_goster)
        self.fis_tablo = QTableWidget()
        self.fis_tablo.setObjectName("fis-onizleme")
        bol.addWidget(self.tablo)
        bol.addWidget(self.fis_tablo)
        bol.setSizes([500, 220])
        lay.addWidget(bol, 1)
        self.firmalari_yenile()

    def firmalari_yenile(self):
        secili = self.firma.currentData()
        self.firma.blockSignals(True)
        self.firma.clear()
        for f in firmalar.liste():
            self.firma.addItem(f"{f.get('unvan', '?')}  ·  {f.get('vkn') or 'VKN yok'}", f.get("vkn", ""))
        if secili:
            self.firma.setCurrentIndex(max(0, self.firma.findData(secili)))
        self.firma.blockSignals(False)
        self.firma_degisti()

    def vkn(self):
        return self.firma.currentData() or ""

    def firma_degisti(self, *_):
        ayar = QSettings("Baskan", "Baskan")
        for k, w in self.hesap.items():
            w.setText(ayar.value(f"hesap/{self.vkn()}/{k}", VARSAYILAN_HESAP[k]))
        self.doldur()

    def hesap_kaydet(self):
        ayar = QSettings("Baskan", "Baskan")
        for k, w in self.hesap.items():
            ayar.setValue(f"hesap/{self.vkn()}/{k}", w.text().strip() or VARSAYILAN_HESAP[k])
        self.fis_goster()

    def hesaplar(self):
        return {k: w.text().strip() or VARSAYILAN_HESAP[k] for k, w in self.hesap.items()}

    def yukle(self):
        if not self.firma.count():
            QMessageBox.warning(self, "Başkan", "Önce Firmalar modülünde firma tanımlayın (VKN ile).")
            return
        yollar, _ = QFileDialog.getOpenFileNames(self, "E-fatura XML / ZIP seç", "", "E-fatura (*.xml *.zip)")
        if not yollar:
            return
        yeni, hatalar = dosyalardan_oku(yollar)
        var = {f["ettn"] or (f["satici_vkn"], f["no"]) for f in self.faturalar}
        eklenen = [f for f in yeni if (f["ettn"] or (f["satici_vkn"], f["no"])) not in var]
        self.faturalar = sorted(self.faturalar + eklenen, key=lambda f: (f["tarih"], f["no"]))
        self.doldur()
        msj = f"{len(eklenen)} fatura eklendi ({len(yeni) - len(eklenen)} zaten vardı), toplam {len(self.faturalar)}."
        if hatalar:
            msj += f"  ⚠ {len(hatalar)} dosya okunamadı: " + "; ".join(hatalar[:3])
        self.durum.setText(msj)

    def doldur(self):
        b = ["Yön", "Tarih", "Fatura No", "Tip", "Karşı Taraf", "VKN", "Matrah", "KDV", "Tevkifat", "Toplam", "Uyarı"]
        self.tablo.setColumnCount(len(b))
        self.tablo.setHorizontalHeaderLabels(b)
        self.tablo.setRowCount(len(self.faturalar))
        for i, f in enumerate(self.faturalar):
            y, _, uy = fis(f, self.vkn(), self.hesaplar())
            karsi, kvkn = (f["satici"], f["satici_vkn"]) if y in ("alis", "satis_iade") else (f["alici"], f["alici_vkn"])
            for j, v in enumerate((YON_AD[y], f["tarih"], f["no"], f["tip"], karsi, kvkn, f["matrah"], f["kdv"],
                                   f["tevkifat"], f["matrah"] + f["kdv"] - f["tevkifat"], "; ".join(uy))):
                it = QTableWidgetItem(_tl(v) if isinstance(v, float) else str(v))
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if isinstance(v, float):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tablo.setItem(i, j, it)
        self.tablo.resizeColumnsToContents()
        self.fis_goster()

    def fis_goster(self):
        satirlar = []
        for i in sorted({x.row() for x in self.tablo.selectedIndexes()}) or range(min(1, len(self.faturalar))):
            _, s, _ = fis(self.faturalar[i], self.vkn(), self.hesaplar())
            satirlar += s
        self.fis_tablo.setColumnCount(4)
        self.fis_tablo.setHorizontalHeaderLabels(["Hesap", "Açıklama", "Borç", "Alacak"])
        self.fis_tablo.setRowCount(len(satirlar))
        for i, (h, a, bo, al) in enumerate(satirlar):
            for j, v in enumerate((h, a, _tl(bo) if bo else "", _tl(al) if al else "")):
                it = QTableWidgetItem(v)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if j >= 2:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.fis_tablo.setItem(i, j, it)
        self.fis_tablo.resizeColumnsToContents()

    def fis_aktar(self):
        if not self.faturalar:
            return
        yol, _ = QFileDialog.getSaveFileName(self, "Fişi Excel'e aktar", "Fis_Aktarim.xlsx", "Excel (*.xlsx)")
        if not yol:
            return
        try:
            n = fis_excel(self.faturalar, self.vkn(), yol, self.hesaplar())
        except PermissionError:
            QMessageBox.critical(self, "Başkan", "Dosya kaydedilemedi (Excel'de açık olabilir).")
            return
        QMessageBox.information(self, "Başkan", f"{n} fatura için fiş yazıldı:\n{yol}\n\nMuhasebe programının "
                                "'Excel'den fiş aktarma' ekranında sütunları eşleştirin (Fiş No, Tarih, Hesap, Borç, Alacak…).")

    def liste_aktar(self):
        if not self.faturalar:
            return
        yol, _ = QFileDialog.getSaveFileName(self, "Fatura listesi", "Fatura_Listesi.xlsx", "Excel (*.xlsx)")
        if not yol:
            return
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append([self.tablo.horizontalHeaderItem(j).text() for j in range(self.tablo.columnCount())] + ["ETTN", "Dosya"])
        for i, f in enumerate(self.faturalar):
            y = yon(f, self.vkn())
            karsi, kvkn = (f["satici"], f["satici_vkn"]) if y in ("alis", "satis_iade") else (f["alici"], f["alici_vkn"])
            ws.append([YON_AD[y], f["tarih"], f["no"], f["tip"], karsi, kvkn, f["matrah"], f["kdv"], f["tevkifat"],
                       f"=G{i + 2}+H{i + 2}-I{i + 2}", "; ".join(f["uyari"]), f["ettn"], f["kaynak"]])
        wb.save(yol)
        QMessageBox.information(self, "Başkan", f"Kaydedildi:\n{yol}")
