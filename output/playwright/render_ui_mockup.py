from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

W, H = 1600, 1000
BG = "#0b111b"
PANEL = "#111b29"
PANEL2 = "#0e1724"
LINE = "#263a52"
TEXT = "#eef5ff"
MUTED = "#8192aa"
CYAN = "#22d3ee"
GREEN = "#25d39a"
AMBER = "#f5b94b"
RED = "#ff5361"
BLUE = "#4d86ff"

root = Path(__file__).parent
out = root / "nidar-gcs-ui-design.png"

def font(size, bold=False, mono=False):
    candidates = []
    if mono:
        candidates = [r"C:\Windows\Fonts\consola.ttf"]
    elif bold:
        candidates = [r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arialbd.ttf"]
    else:
        candidates = [r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"]
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

F10 = font(10)
F11 = font(11)
F12 = font(12)
F12B = font(12, True)
F13B = font(13, True)
F15B = font(15, True)
F19B = font(19, True)
FM10 = font(10, mono=True)
FM11 = font(11, mono=True)
FM14 = font(14, mono=True)

im = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(im)

def rect(box, fill, outline=None, radius=7, width=1):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)

def text(x, y, s, f=F11, fill=TEXT, anchor=None):
    d.text((x, y), s, font=f, fill=fill, anchor=anchor)

def panel(box, title=None, right=None):
    rect(box, PANEL, LINE, 7)
    if title:
        text(box[0]+14, box[1]+14, title, F11, TEXT)
    if right:
        text(box[2]-14, box[1]+15, right, F10, MUTED, "ra")

# Header
rect((8, 8, W-8, 66), PANEL, LINE, 7)
text(24, 21, "TEAM EDITH", F19B)
text(175, 27, "NIDAR AIRMOUSE  ·  GCS", F10, MUTED)
rect((760, 20, 906, 51), PANEL2, LINE, 5)
d.ellipse((776, 31, 784, 39), fill=GREEN)
text(795, 26, "AUTONOMOUS", F10, TEXT)
for x, label, val, color in [(922, "MISSION", "00:12:21 / 30:00", TEXT), (1086, "LOCAL LINK", "98% · 3ms", GREEN), (1260, "6S BATTERY", "87% · 22.4V", GREEN)]:
    rect((x,20,x+150,51), PANEL2, LINE, 5)
    text(x+10,26,label,F10,MUTED); text(x+10,39,val,F10,color)
rect((1422, 20, 1576, 51), "#102d3b", "#226a80", 5)
text(1499, 35, "SIMULATION", F10, CYAN, "mm")

# Layout coordinates
left=(8,74,308,874); center=(316,74,1270,874); right=(1278,74,1592,874)

# Left camera
panel((8,74,308,344), "LIVE CAMERA", "● LIVE · OPTICAL")
rect((22,109,294,267), "#08101d", "#304968", 5)
d.rectangle((38,125,278,251), outline="#2d5874", width=1)
d.rectangle((94,151,222,225), outline="#2d5874", width=1)
d.line((158,153,158,223), fill="#7ea9be", width=1)
d.line((96,187,220,187), fill="#7ea9be", width=1)
text(34, 119, "● REC", F10, RED)
text(280, 119, "1280×720 · 30 FPS", F10, MUTED, "ra")
text(158, 179, "+", font(28), "#b8d6e7aa", "mm")
text(34, 243, "JETSON AI FEED · SIMULATED", F10, MUTED)
d.rounded_rectangle((22,281,294,289), 4, fill="#25374e")
d.rounded_rectangle((22,281,207,289), 4, fill=CYAN)
text(22, 301, "PILOT VIEW", F10, MUTED); text(294, 301, "96%", FM10, CYAN, "ra")

# Left detections
panel((8,352,308,874), "SURVIVOR DETECTIONS", "2 / 6 FOUND")
dets=[("● SURVIVOR 1","FOUND","GRID B2 · MOVEMENT DETECTED","92% CONFIDENCE","[08:14]",True),
      ("● SURVIVOR 2","FOUND","GRID C4 · STATIONARY (THERMAL)","85% CONFIDENCE","[08:29]",False),
      ("○ SURVIVOR 3","SEARCHING","GRID A3 · SEARCH PENDING","NO DETECTION YET","—",False),
      ("○ SURVIVOR 4","SEARCHING","GRID D2 · SEARCH PENDING","NO DETECTION YET","—",False),
      ("○ SURVIVOR 5","SEARCHING","GRID D4 · SEARCH PENDING","NO DETECTION YET","—",False)]
y=389
for name,status,sub,conf,timestamp,focus in dets:
    rect((22,y,294,y+82), "#0d1826", CYAN if focus else "#29415a", 5, 2 if focus else 1)
    text(32,y+11,name,F11,TEXT)
    rect((235,y+9,284,y+28), "#10392f" if status=="FOUND" else PANEL2, GREEN if status=="FOUND" else "#40536b", 3)
    text(259,y+18,status,F10,GREEN if status=="FOUND" else MUTED,"mm")
    text(32,y+38,sub,F10,TEXT)
    text(32,y+61,conf,FM10,MUTED); text(283,y+61,timestamp,FM10,MUTED,"ra")
    y += 91

# Center map panel
panel((316,74,1270,874))
text(334, 91, "LIVE 2D SLAM MAP", F15B)
rect((507,88,624,113), PANEL2, "#2a8b7b", 4)
text(565,100,"● SLAM ACTIVE",F10,GREEN,"mm")
text(1252, 98, "TARGET: SURVIVOR 1 · FOCUSED", F10, MUTED, "ra")

mapbox=(334,124,1252,744)
rect(mapbox, "#536866", "#365165", 5)
# map grid
for x in range(mapbox[0]+40,mapbox[2],60): d.line((x,mapbox[1],x,mapbox[3]), fill="#d8e4e2", width=1)
for y in range(mapbox[1]+40,mapbox[3],60): d.line((mapbox[0],y,mapbox[2],y), fill="#d8e4e2", width=1)
# occupancy polygon
poly=[(370,160),(785,160),(785,210),(838,210),(838,165),(1203,165),(1203,690),(1050,690),(1050,652),(880,652),(880,716),(665,716),(665,670),(482,670),(482,625),(398,625),(398,510),(370,510),(370,332),(410,332),(410,245),(370,245)]
d.polygon(poly, fill="#c8cac8", outline="#11191b")
d.line(poly+[poly[0]], fill="#11191b", width=9, joint="curve")
# interior obstacles
for r in [(510,350,760,450),(425,510,685,588),(825,515,1110,610),(785,265,820,500)]:
    d.rectangle(r, fill="#536866", outline="#16201f", width=5)
# track route
track=[(924,208),(1005,255),(1050,330),(1032,400),(930,446),(810,465),(760,530),(790,602),(900,655),(1010,660),(1070,626),(1032,568),(930,535),(820,500)]
d.line(track, fill="white", width=14, joint="curve")
d.line(track, fill=BLUE, width=7, joint="curve")
# markers
d.ellipse((806,483,832,509), fill="#f5faf9", outline=BLUE, width=3)
rect((835,491,945,526), "#f6faf9", BLUE, 4); text(845,499,"DRONE · HDG 228°",FM10,"#10243b")
d.ellipse((914,280,934,300), fill="#f6faf9", outline=GREEN, width=3)
rect((940,275,1012,304), "#f6faf9", GREEN, 4); text(948,283,"S01 · B2",FM10,"#10243b")
rect((1052, 671, 1228, 726), "#f3f7f7", "#c9d6d8", 4)
d.line((1070,693,1104,693), fill=BLUE, width=4); text(1112,684,"TRAVELLED TRACK",F10,"#1767ff"); text(1112,701,"1 m GRID SCALE · SIMULATED",F10,"#112131")
text(350, 136, "A", F10, MUTED); text(550,136,"B",F10,MUTED); text(750,136,"C",F10,MUTED); text(950,136,"D",F10,MUTED); text(1150,136,"E",F10,MUTED)
# status strip
rect((334,756,1252,851), PANEL2, LINE, 5)
text(350, 772, "LIDAR · ACTIVE   SLAM · ACTIVE   VISION · ACTIVE   WIFI · CONNECTED", FM10, GREEN)
text(1236, 790, "MAPPED CELLS 115 / 180", FM10, MUTED, "ra")

# Right panels
panel((1278,74,1592,270), "MISSION STATUS", "AUTONOMOUS")
metrics=[("PHASE","EXPLORING"),("SURVIVORS","2 / 6"),("MAP COVERAGE","64%"),("COORDINATE FRAME","LOCAL ENU")]
for i,(a,b) in enumerate(metrics):
    x=1294+(i%2)*145; y=112+(i//2)*57
    text(x,y,a,F10,MUTED); text(x,y+18,b,F13B,TEXT)
d.rounded_rectangle((1294,235,1576,243),4,fill="#26384c"); d.rounded_rectangle((1294,235,1475,243),4,fill=CYAN)
panel((1278,278,1592,514), "TELEMETRY", "10 HZ SIM")
tele=[("Battery","87%",GREEN),("Voltage","22.4 V",TEXT),("Current","8.2 A",TEXT),("Altitude","2.35 m",TEXT),("Mode","AUTO",CYAN),("Link","37 ms",TEXT),("Quality","98%",GREEN),("Speed","1.19 m/s",TEXT),("Heading","228°",TEXT),("Position","VALID",GREEN)]
for i,(a,b,c) in enumerate(tele):
    col=i%2; row=i//2; x=1294+col*142; y=317+row*34
    text(x,y,a,F10,MUTED); text(x+130,y,b,FM10,c,"ra"); d.line((x,y+22,x+136,y+22),fill="#223247",width=1)
panel((1278,522,1592,874), "CORE SYSTEM HEALTH", "4 / 4 READY")
health=[("MicoAir H743 · MAVLink","READY",GREEN),("Jetson Orin · YOLO + SLAM","READY",GREEN),("RPLiDAR C1 · 10.2 Hz","READY",GREEN),("Raspberry Pi · Wi-Fi bridge","READY",GREEN),("Emergency / RTL path","SIMULATED",AMBER)]
for i,(a,b,c) in enumerate(health):
    y=566+i*52; text(1294,y,a,F10,TEXT); rect((1504,y-3,1576,y+19), "#10392f" if c==GREEN else "#3d3015", "#206f59" if c==GREEN else "#86692a", 3); text(1540,y+8,b,F10,c,"mm"); d.line((1294,y+29,1576,y+29),fill="#223247",width=1)

# Footer
rect((8,882,1592,992), PANEL, LINE, 7)
text(22, 898, "EVENT LOG · CHRONOLOGICAL", F11, TEXT); text(1367, 899, "LOCAL SYNTHETIC FEED", F10, MUTED, "ra")
logs=["[08:42:15] INFO  Waypoint WP-09 reached. Scanning Corridor Beta.","[08:41:25] INFO  Survivor S02 localized at Grid C4. Confidence 85%.","[08:40:52] INFO  LiDAR map updated · 115 / 180 cells mapped."]
for i,s in enumerate(logs): text(22,927+i*18,s,FM10,"#aebfd2")
rect((1377,898,1578,976), "#c93242", "#e35b67", 5)
text(1477,922,"● EMERGENCY ABORT",F12B,"white","mm"); text(1477,948,"RTL · RETURN TO ENTRY LZ",F10,"#ffd5d8","mm")

im.save(out, optimize=True)
print(out)
