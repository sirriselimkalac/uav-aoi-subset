# İş bilgisayarı rehberi (doğrulama oturumları)

Bu dosya, iş bilgisayarında [VALIDATION.md](VALIDATION.md) yürütülürken bu kuruluma özgü
farkları ve sırayı tutar. Komutların ve beklenen sonuçların asıl kaynağı VALIDATION.md'dir;
burada yalnızca onunla çelişmeyen ekler var. Her oturumda önce `git pull`, sonra bu dosyanın
**Durum** bölümü.

Gizlilik: bu dosyaya ve VALIDATION.md'ye iş yeri makine adı, IP, kullanıcı adı, kampanya yolu
yazılmaz. Depo bir gün açık olacak; geçmişteki her satır da açılır.

## Durum

- Güncelleme: 2026-11-03
- Veri seti açık: `D:\altum-pt-blueberries-60m-sample-data\altum-pt-blueberries-60m-sample-data`
  (tek klasör; 3.361 dosya bekleniyor, 2.1'deki sayımlarla doğrulanacak).
- Pix4D: tüm veriyle bir proje açıldı ve 1. adımı bitti, ama **3D Maps** şablonuyla
  (`D:\altum-pt-blueberries-60m-sample-data\altum-pt-blueberries`). Karar aşağıda: Ag
  Multispectral ile yeni proje.
- Uçuş düzeni (Pix4D harita görünümünden): hatlar kuzey-güney, gidiş-dönüş; başlangıç batı
  kenarının ortası (ilk hat yarım), her hattan sonra doğuya kayıyor, bitiş kuzeydoğu köşesi.
  Bu, V75'in beklenen cevabıdır.
- Pix4D Ag Multispectral projesi: 1. adım 44 dk sonra `e0046 No calibrated cameras` ile bitti
  (2026-11-03 11:02). Anahtar nokta ve eşleşme sayıları iyi (görüntü başına medyan 14.669 /
  10.431); başlangıç kareleri reddedilmiş ("All initial frames rejected", "No initial frame").
  Aynı veri 3D Maps ile kalibre oldu. Kalibrasyon yöntemi iki şablonda da Standard, neden o
  değil. Neden için iş bilgisayarındaki Claude iki `.p4d` ve iki logu karşılaştırıyor.
  Doğrulama bunu beklemez: 3D Maps projesi (kalite raporunda kalibre oranı ~%95 üstüyse) 2.
  adım, sonra 3. adım için ortomozaik + Google Maps Tiles and KML, Index Calculator beş bant
  Camera and Sun Irradiance, **LWIR No Correction** (Camera Only termali sabit kazançla
  ölçekliyor). Adımlar her zaman tek tek başlatılır.
- Faz 1: sürüyor. Takılma kaydının ilk dört satırı VALIDATION.md'ye yazıldı ve README düzeltildi
  (winget/git kontrolü, Git kurulumu, yeni pencere). Sıradaki: README'yi `git pull` ile tazele,
  `uv sync`, P5-P7. Faz 2-5: başlamadı.

## 1. Pix4D şablonu: Ag Multispectral ile yeniden

Doğrulama açısından şablon hiçbir kontrolün sonucunu değiştirmez: bantların aynı çekime
gruplanması (V50, V77e) görüntü içe aktarılırken olur, şablondan önce; V20c ise kaba bir görsel
karşılaştırmadır. Yine de yeniden yapıyoruz, çünkü:

- Ag Multispectral bu kamera için doğru şablon (reflektans ve indeks haritaları, radyometrik
  düzeltme); 3D Maps RGB ortomozaik ve 3B model içindir;
- README'nin *Tested setup* bölümü "Pix4Dmapper ile denendi" diyor; bu, kameranın doğru
  akışıyla denenmiş olmalı, ekran görüntüleri (RELEASE.md A2) de oradan alınacak;
- 1. adım bu veri boyutunda kısa sürer ve üzerine henüz hiçbir şey kurulmadı.

Yapılacak:

1. Mevcut 3D Maps projesine dokunma (Pix4D bir adımı yeniden başlatınca o adımın eski
   çıktılarını siler). Bitince silinebilir.
2. *Yeni Proje* → ad `altum-pt-blueberries-ag`, konum `D:\altum-pt-blueberries-60m-sample-data\`
   → *Add Images*: veri klasöründeki 3.360 TIFF → kamera Altum-PT olarak tanınmalı, 7 bant
   gruplanmış olmalı (480 çekim) → şablon **Ag Multispectral** → *İşlemeye Başla* işaretsiz.
3. *İşleme Seçenekleri*:
   - 3. adım → Index Calculator → radyometrik düzeltme: beş reflektans bandı
     **Camera and Sun Irradiance**. Veri setinde panel çekimi yok (yalnız panel CSV'si), bu
     yüzden *Kalibre Et* kullanılamaz; LWIR **Camera Only**.
   - 3. adım → ortomozaik açık, çıktı olarak **Google Maps Tiles and KML** işaretli
     (V20c'deki "Pix4D alan KML'i" bu olacak). Bu seçenek yoksa: QGIS'te bir reflektans
     haritasının geçerli piksellerinden poligon çıkar (Raster → Dönüştürme → Poligonlaştır) ve
     KML olarak kaydet. KML her durumda **klonun dışında** (`$Res`) kalır, commit edilmez.
4. 1, 2 ve 3. adımları çalıştır.
5. Log penceresinin başındaki `Active GPU` satırına bak. "Microsoft Remote Display Adapter"
   yazıyorsa Pix4D uzak masaüstü bağdaştırıcısını seçmiş, A4000'i kullanmıyor: Pix4D
   ayarlarında (Yardım → Ayarlar, işleme/donanım sekmesi) A4000'i seç, olmuyorsa not et. Doğrulamayı
   etkilemez, yalnız süreyi.

## 2. Klasörler (VALIDATION.md 2.1'in yerine)

Veri D: sürücüsünde kalıyor; Pix4D projesi görüntü yollarını tuttuğu için klasör taşınmaz.
Sabit bağlantı (hardlink) kontrolleri aynı sürücü istediği için çalışma klasörü de D:'de.
Her PowerShell oturumunun başında VALIDATION.md 2.1'deki bloğu **bu değerlerle** çalıştır:

```powershell
$Demo = "D:\uav-demo"
$Repo = "$Demo\uav-aoi-subset"
$Data = "D:\altum-pt-blueberries-60m-sample-data\altum-pt-blueberries-60m-sample-data"
$Lay  = "$Demo\data\blueberry_layered"
$Aoi  = "$Demo\aoi"
$Res  = "$Demo\results"
New-Item -ItemType Directory -Force $Demo, "$Demo\data", $Aoi, $Res | Out-Null
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
function aoi { uv run --project $Repo uav-aoi-subset @args }
```

VALIDATION.md'de `C:\uav-demo` geçen her yer bu kurulumda `D:\uav-demo` olarak okunur. Faz 1
README'nin önerdiği klasörle (`C:\uav-demo\phase1`) yapılır, ona dokunulmaz.

Disk: başlamadan `Get-PSDrive C, D` ile boş alana bak. D:'de en az **90 GB** gerekir: V12
veri setinin tamamını (25,4 GB) kopyalar, V34 tam kopya yapar (25,4 GB), V39 onun bir kopyasını
daha alır (25,4 GB). Her birini kendi kontrolü bittikten hemen sonra sil
(`Saha Fotoğrafları – deneme`, `move_src`, `move_dst`); `full_copy`'yi V39 bitene kadar tut.

## 3. Sıra ve bu kuruluma özgü notlar

Faz 1 yalnız README ile yapılır: o bitene kadar bu bölümü ve VALIDATION.md'nin Faz 1 sonrasını
okuma.

| Kontrol | Bu kurulumda |
|---|---|
| 2.1 sayımlar | `$Data` yukarıdaki yol; `Move-Item` adımı atlanır, sayım komutları aynen çalıştırılır |
| V12 | kopya D:'ye gider (25,4 GB); kontrolden sonra sil |
| V20c | Pix4D KML'i 1. bölümdeki Ag Multispectral projesinin 3. adımından |
| V37, V40 | `$Data` ile aynı sürücü (D:) olmalı; yukarıdaki değerlerle öyle |
| V43, V44 | "diğer sürücü" bu kurulumda **C:** (`--dest C:\uav-demo-other\...`); sonra sil |
| V50-V52 | tüm veriyle açılan proje değil, V31'in alt küme klasörüyle **ayrı yeni** proje (şablon Ag Multispectral) |
| V60 | beklenen yol `C:\uav-demo\data\blueberry` değil, `$Data` yolu |
| V75 | beklenen: kuzey-güney hatlar, gidiş-dönüş, doğuya kayarak (Durum bölümü) |
| V76a | dört şerit batıdan doğuya `0000SET` → `0003SET`; her biri yaklaşık dört hat; ilk hat yarım olduğu için şerit sınırları hat ortasına düşebilir, bu hata değil |
| 2.7, V79, V84 | MATLAB bu bilgisayarda yoksa n.a. yazılır ve nedeni not edilir |
| Faz 4-5 | kampanya verisi; çıktılar `C:\uav-demo\private` yerine `D:\uav-demo\private`; yalnız anonim sayılar |

Ek, isteğe bağlı (VALIDATION.md'de yok, V92'nin yerini tutmaz): `D:\altum-pt-blueberries-60m-sample-data`
klasörü hem veriyi hem Pix4D projelerini içeriyor. `aoi index` bu üst klasörde çalıştırılırsa
Pix4D'nin yazdığı dosyaların nasıl sayıldığı açık veriyle görülür; sonuç "Findings" altına not
olarak yazılabilir.

## 4. Sonuçlar ve gönderim

- Sonuçlar VALIDATION.md'nin *Results* tablolarına, yalnız sayılarla. Her bulgu GitHub'da
  *Bug report* formuyla issue.
- Her oturum sonunda: `git status` (yalnız `docs/` değişmeli), commit, `git push`,
  `git log origin/main -1` ile gönderimi doğrula. Clone geçici, gönderilmeyen sonuç kaybolur.
- Bu dosyanın **Durum** bölümünü de güncelle (hangi faz, hangi kontrol, açık sorular).
- Takılınca: Mac'teki Claude oturumuna "IS_BILGISAYARI.md durumuna bak" demek yeter; ekran
  görüntüsü ya da çıktı da eklenebilir.
