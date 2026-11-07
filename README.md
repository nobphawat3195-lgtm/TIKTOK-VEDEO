# TIKTOK-VEDEO

ระบบสร้างคลิป TikTok แนวตั้ง (1080x1920, H.264/AAC, `+faststart`) จาก storyboard YAML
หรือจากประวัติเทรด MT5 โดยตรง render ด้วย Pillow แล้ว pipe raw frame เข้า ffmpeg ทีละเฟรม
โดยไม่เขียนไฟล์เฟรมลง disk

- รองรับภาษาไทยเต็มรูปแบบ (libraqm shaping, wrap ไม่ตัดสระ/วรรณยุกต์, ใช้ `pythainlp` ตัดคำได้ถ้าติดตั้งไว้)
- Element: `text`, `image`, `counter` (ตัวเลขวิ่ง เช่น กำไร +$386.98)
- Animation: `fade`, `slide_up`, `pop`, `none` + `delay` ต่อ element, Ken Burns บนภาพพื้นหลัง
- เสียง: voice-over ต่อ scene (scene ยาวตามเสียงอัตโนมัติ), BGM loop + fade out + **ducking** ใต้เสียงพากย์
- Progress bar ด้านบนแบบ TikTok
- Template **Trade Recap**: CSV ของ deal จาก MT5 → Net P/L, Win rate, PF, Max DD, equity curve → คลิป 16 วินาที

## ติดตั้ง

ต้องมี `ffmpeg` และ Python 3.10+

```bash
pip install -r requirements.txt
```

ฟอนต์: ระบบจะหาฟอนต์ไทยในเครื่องเอง (Kanit/Prompt ใน `assets/fonts/`, Noto Sans Thai, Loma, Tahoma)
ถ้าจะกำหนดเอง ให้ตั้ง `TIKTOK_VIDEO_FONT=/path/to/font.ttf` หรือใส่ `font:` ใน storyboard

## ใช้งาน

### 1. คลิปสรุปผลเทรดจาก MT5

1. คัดลอก `mql5/ExportDeals.mq5` ไปไว้ที่ `MQL5/Scripts/` แล้ว compile
2. ลากสคริปต์ลงชาร์ต ตั้งค่า `InpDaysBack`, `InpSymbol` (prefix match เช่น `XAUUSD` จะเจอ `XAUUSDm` ด้วย) และ `InpMagic`
3. ไฟล์จะออกที่ `MQL5/Files/deals.csv` (commission ฝั่ง IN deal จะถูกรวมเข้าไม้ปิดให้แล้ว)

```bash
python -m tiktok_video recap deals.csv -o out/recap.mp4 --symbol XAUUSD --handle @mygoldea --bgm music.mp3
```

CSV ต้องมีคอลัมน์ `time, symbol, type, volume, profit` และใส่ `commission, swap, entry` เพิ่มได้
ตัวคั่นเป็น `,` `;` หรือ tab ก็ได้ แถวที่ `entry=in` และแถว balance จะถูกข้าม

### 2. คลิปจาก storyboard

```bash
python -m tiktok_video render examples/storyboard.yaml -o out/tips.mp4
python -m tiktok_video still  examples/storyboard.yaml --scene 2 --t 1.5 -o out/s2.png   # พรีวิวเฟรมเดียว
```

```yaml
video:  { fps: 30, bgm: music.mp3, bgm_volume: 0.25, font: fonts/Kanit-Bold.ttf }
defaults: { duration: 3, background: { gradient: ["#0B0F1A", "#1C2440"] } }
scenes:
  - title: "3 กฎ Scalping ทองคำ"      # shorthand: title / text / caption
    text: "XAUUSD M1 / M5"
    caption: "ข้อ 3 สำคัญที่สุด"
  - voice: voice/01.mp3                # ไม่ใส่ duration = ยาวตามเสียง + 0.4s
    background: { image: bg.jpg, dim: 0.4 }   # Ken Burns อัตโนมัติ
    elements:
      - { type: text, text: "Spread > 25 pts ข้าม", size: 72, y: 0.4, anim: slide_up }
      - { type: counter, from: 0, to: 386.98, decimals: 2, prefix: "$", signed: true,
          size: 150, y: 0.55, color: "#2EE59D", anim: pop, delay: 0.3 }
      - { type: image, path: chart.png, width: 0.84, y: 0.7, radius: 28 }
```

Prop ของ text: `size, color, stroke, stroke_color, box (#RRGGBBAA), align, line_height, max_width, x, y, font`
ส่วน `x`/`y` เป็นสัดส่วนของจอ (0–1) และเป็นจุดกึ่งกลางของ element ควรวางเนื้อหาสำคัญไว้ที่ `y` ไม่เกิน 0.75
และเว้นขอบขวาไว้ เพราะ UI ของ TikTok จะทับส่วนนั้น

## Test

```bash
pip install pytest && python -m pytest -q
```
