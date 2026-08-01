"""
tempat variable untuk berbagai macam perubahan
"""


season = '26 SPRING'
# season_code = 'S26'
season_code = season.split(' ')[1][0] + season.split(' ')[0]
SO_list = [

]


# ============================================================
#  Report Launcher override (auto-integration)
#  If the dashboard wrote launcher_params.json next to this file, use the
#  SO numbers entered there instead of the list above. Editing this file by
#  hand still works whenever the dashboard isn't used.
# ============================================================
import json as _json, os as _os
_lp = _os.path.join(_os.path.dirname(__file__), "launcher_params.json")
if _os.path.exists(_lp):
    try:
        with open(_lp, encoding="utf-8") as _f:
            _ov = _json.load(_f)
        _so = _ov.get("SO_list", SO_list)
        if isinstance(_so, list):
            _cleaned = [str(s).strip() for s in _so if str(s).strip()]
        else:
            _cleaned = [str(_so).strip()] if str(_so).strip() else []
        # Only override when the dashboard actually provided SO numbers, so an
        # empty form doesn't silently wipe the hand-edited defaults above.
        if _cleaned:
            SO_list = _cleaned
        _sn = str(_ov.get("season", "")).strip().upper()
        if _sn and len(_sn.split(" ")) >= 2:
            season = _sn
            season_code = season.split(" ")[1][0] + season.split(" ")[0]
            IM_header = 56 if season.split(" ")[1][0] == "S" else 53
            
    except Exception as _e:
        print(f"[launcher] could not read {_lp}: {_e}")


# ============================================================
#  TATA LETAK PRODUCT CARD  (dipakai oleh SO_order.py)
#  Ubah ukuran / jarak di sini — tidak perlu masuk ke kode.
#  Angka lebih besar = lebih besar / lebih lebar, kecuali ada catatan.
# ============================================================

# --- tampilkan swatch? -------------------------------------------------------
# False = card hanya berisi foto hero + judul (tanpa deretan swatch warna dan
#         tanpa oval penanda warna yang dipesan)
# True  = swatch dan ovalnya muncul kembali seperti semula
SHOW_SWATCHES = False

# --- tampilkan harga? --------------------------------------------------------
# False = baris judul hanya "#347  NAMA STYLE" (harga disembunyikan)
# True  = harga ikut tampil, mis. "#347  NAMA STYLE  $68"
SHOW_PRICE = False

# --- skala keseluruhan & output ---------------------------------------------
DPI     = 300   # resolusi PNG yang disimpan
UNIT_IN = 1.125    # inci per unit tata letak — naikkan untuk memperbesar SELURUH card
BLOCK_W = 5.0      # lebar (inci) satu blok style
PER_ROW = 5        # maksimal blok style per baris sebelum turun (4->[4] 6->[3,3] ...)

# --- tinggi foto hero vs. swatch --------------------------------------------
HERO_U = 5.0       # satuan tinggi foto hero (foto style)
SW_U   = 1.1       # satuan tinggi SATU baris swatch (makin kecil = swatch makin kecil)

# --- grid swatch di dalam blok ----------------------------------------------
MAXCOLS = 4        # swatch turun baris setelah sebanyak ini per baris (5 -> 3,2)
SUB     = 2        # sub-kolom per swatch (agar baris pendek bisa di tengah); jaga >= 1
FINE    = MAXCOLS * SUB   # turunan: total kolom halus per baris swatch

# --- ukuran resize gambar swatch (piksel, l x t) ----------------------------
SW_W = 300
SW_H = 500

# --- jarak DI DALAM blok (fraksi gridspec matplotlib) -----------------------
SWATCH_ROW_GAP = 0.2     # jarak vertikal antar baris swatch   (hspace dalam)
SWATCH_COL_GAP = 0.0     # jarak horizontal antar swatch       (wspace dalam; boleh negatif)

# --- jarak ANTAR blok + margin halaman --------------------------------------
BLOCK_COL_GAP = 0.12     # jarak horizontal antar blok         (wspace luar)
BLOCK_ROW_GAP = 0.18     # jarak vertikal antar baris blok      (hspace luar)
MARGIN_L = 0.03          # margin halaman sebagai fraksi dari figure
MARGIN_R = 0.97
MARGIN_T = 0.97
MARGIN_B = 0.03

# --- teks -------------------------------------------------------------------
LABEL_WRAP_WIDTH = 12    # jumlah huruf sebelum label swatch turun ke baris baru
LABEL_FONTSIZE   = 7     # label nama warna swatch
LABEL_PAD        = 4     # jarak antara swatch dan labelnya
TITLE_FONTSIZE   = 11    # baris judul "#700  NAMA STYLE  $65"
TITLE_PAD_IN     = 0.12  # jarak (inci) judul di bawah foto saat swatch dimatikan

# --- oval lingkaran di swatch yang dipilih ----------------------------------
OVAL_W_SCALE  = 1.2      # lebar oval  = SW_W * ini
OVAL_H_SCALE  = 1.4      # tinggi oval = SW_H * ini
OVAL_Y_FACTOR = 1.7      # titik tengah vertikal = SW_H / ini (makin kecil = makin bawah)
OVAL_COLOR    = "black"
OVAL_LW       = 1.5      # ketebalan garis oval

# --- warna ------------------------------------------------------------------
CARD_BG       = "white"      # latar belakang figure / halaman
SWATCH_BORDER = "#cccccc"    # garis tipis di sekeliling tiap swatch
