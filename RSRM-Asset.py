import customtkinter as ctk
from PIL import Image, ImageDraw
from tkinter import messagebox, filedialog
import threading
import queue
from datetime import datetime, timezone, timedelta
import sys
import os
import requests
import webbrowser
import subprocess

from database import (
    supabase,
    login_user,
    fetch_assets,
    insert_asset,
    fetch_logs,
    log_action,
    fetch_transfer_logs,
    insert_transfer_log,
    upload_pdf_to_supabase
)

def resource_path(relative_path):
    """ คืนค่า Path ที่ถูกต้องทั้งตอนรันแบบสคริปต์ปกติและแบบ .exe """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# =========================================================
# 1. กำหนดเลขเวอร์ชันปัจจุบันของโปรแกรมที่คุณกำลังใช้งานอยู่
# =========================================================

CURRENT_VERSION = "1.0.1" 

def check_for_updates(main_app=None):
    try:
        res = supabase.storage.from_("app-updates").get_public_url("version.json")
        version_url = res if isinstance(res, str) else res.get("publicUrl")
        
        if not version_url:
            return

        response = requests.get(version_url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            latest_version = data.get("version")
            download_url = data.get("download_url")
            notes = data.get("release_notes", "")
            force_update = data.get("force_update", False)

            if latest_version and latest_version != CURRENT_VERSION:
                msg = f"ตรวจพบเวอร์ชันใหม่ ({latest_version})\n\nรายละเอียด: {notes}\n\nต้องการอัปเดตเป็นเวอร์ชันล่าสุดเลยหรือไม่?"
                
                if force_update:
                    messagebox.showwarning("แจ้งเตือนบังคับอัปเดต", msg + "\n\n(ระบบจำเป็นต้องอัปเดตทันที)")
                    start_download_and_update(download_url, main_app)
                else:
                    if messagebox.askyesno("แจ้งเตือนอัปเดตเวอร์ชัน", msg):
                        start_download_and_update(download_url, main_app)
    except Exception as e:
        print(f"ไม่สามารถตรวจสอบอัปเดตได้: {e}")

def start_download_and_update(download_url, main_app):
    """สร้างหน้าต่างแสดง Progress Bar และเริ่มดาวน์โหลดไฟล์ใน Background Thread"""
    progress_win = ctk.CTkToplevel(main_app)
    progress_win.title("กำลังอัปเดตโปรแกรม...")
    progress_win.geometry("400x180")
    progress_win.resizable(False, False)
    progress_win.grab_set()  # ป้องกันไม่ให้ไปกดหน้าอื่นขณะอัปเดต
    
    # จัดหน้าต่างให้อยู่ตรงกลาง
    center_window(progress_win, 400, 180)

    ctk.CTkLabel(
        progress_win, 
        text="กำลังดาวน์โหลดเวอร์ชันล่าสุด...", 
        font=(FONT, 13, "bold"),
        text_color=NAVY
    ).pack(pady=(25, 10))

    progress_bar = ctk.CTkProgressBar(progress_win, width=320, progress_color=ORANGE)
    progress_bar.pack(pady=10)
    progress_bar.set(0)

    status_label = ctk.CTkLabel(progress_win, text="0%", font=(FONT, 11), text_color=MUTED)
    status_label.pack(pady=(0, 15))

    def run_download():
        try:
            # ดาวน์โหลดไฟล์แบบ Stream เพื่อคำนวณเปอร์เซ็นต์
            response = requests.get(download_url, stream=True, timeout=30)
            total_size = int(response.headers.get('content-length', 0))
            
            temp_dir = os.environ.get("TEMP", ".")
            new_exe_path = os.path.join(temp_dir, "RSRM_Asset_update.exe")
            
            downloaded = 0
            with open(new_exe_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = downloaded / total_size
                            progress_bar.set(percent)
                            status_label.configure(text=f"{int(percent * 100)}%")

            # ดาวน์โหลดเสร็จแล้ว เตรียมรัน Updater Script เพื่อสลับไฟล์
            status_label.configure(text="กำลังเตรียมรีสตาร์ทระบบ...")
            progress_win.after(1000, lambda: apply_update_and_restart(new_exe_path, main_app, progress_win))

        except Exception as e:
            messagebox.showerror("เกิดข้อผิดพลาด", f"ไม่สามารถดาวน์โหลดอัปเดตได้:\n{e}", parent=progress_win)
            progress_win.destroy()

    # ใช้ Thread เพื่อไม่ให้หน้าจอ UI ค้างตอนดาวน์โหลด
    threading.Thread(target=run_download, daemon=True).start()


def apply_update_and_restart(new_exe_path, main_app, progress_win):
    """สร้างไฟล์ Batch (.bat) เพื่อสลับไฟล์ .exe ตัวเก่ากับตัวใหม่ แล้วเปิดโปรแกรมขึ้นมาใหม่"""
    try:
        # ตรวจสอบว่ารันแบบ .exe หรือแบบ Python Script ปกติ
        if getattr(sys, 'frozen', False):
            current_exe_path = sys.executable
        else:
            # ถ้ารันแบบสคริปต์ .py จะไม่สามารถแทนที่ไฟล์ตัวเองได้โดยตรง
            messagebox.showinfo("โหมดพัฒนา", "ระบบอัปเดตอัตโนมัติจะทำงานสมบูรณ์เมื่อแพ็กเกจเป็นไฟล์ .exe แล้วเท่านั้น", parent=progress_win)
            progress_win.destroy()
            return

        batch_path = os.path.join(os.environ.get("TEMP", "."), "update_cra.bat")
        
        # เขียนคำสั่ง Batch: รอ 2 วินาที -> ลบไฟล์เก่า -> ย้ายไฟล์ใหม่มาทับ -> เปิดโปรแกรมใหม่ -> ลบไฟล์ bat ทิ้ง
        batch_content = f"""
@echo off
timeout /t 2 /nobreak >nul
del "{current_exe_path}"
move /y "{new_exe_path}" "{current_exe_path}"
start "" "{current_exe_path}"
del "%~f0"
"""
        
        with open(batch_path, "w", encoding="utf-8") as f:
            f.write(batch_content)
            
        # สั่งรันไฟล์ Batch
        subprocess.Popen(batch_path, shell=True)

        # ปิดโปรแกรมหลักทั้งหมด
        if progress_win:
            try:
                progress_win.destroy()
            except Exception:
                pass
        if main_app:
            try:
                main_app.destroy()
            except Exception:
                pass
        sys.exit(0)

    except Exception as e:
        messagebox.showerror("เกิดข้อผิดพลาด", f"ไม่สามารถแทนที่ไฟล์อัปเดตได้:\n{e}", parent=progress_win)
        progress_win.destroy()

# =========================================================
# CRA THEME
# =========================================================

NAVY = "#223D7E"
NAVY_DARK = "#182D5E"
ORANGE = "#F36C21"
BG = "#F4F6FA"
WHITE = "#FFFFFF"
TEXT = "#25324A"
MUTED = "#7B879B"
BORDER = "#E6EAF1"
GREEN = "#23865B"
RED = "#D94B4B"

FONT_FAMILY = "Bai Jamjuree"
FONT = FONT_FAMILY

# เว้นพื้นที่ด้านขวาของ Header ให้เท่ากับ scrollbar ของ Body
SCROLLBAR_SPACE = 22

# จำนวนแถวต่อหน้าในตารางครุภัณฑ์ (ลดเพื่อให้หน้าจอไม่ค้าง)
PAGE_SIZE = 25

# กลุ่มสถานะ (รองรับทั้งคำเดิมในฐานข้อมูลและคำที่ใช้ในฟอร์ม)
STATUS_AVAILABLE = ("พร้อมใช้งาน", "ปกติ")
STATUS_DAMAGED = ("ชำรุด", "ส่งซ่อม")
STATUS_REPAIRING = ("อยู่ระหว่างซ่อมแซม",)

# ชื่อตารางใน Supabase
ASSET_TABLE = "asset_list"

NOT_SPECIFIED = "ไม่ระบุ"
KEEP_CURRENT = "— ไม่เปลี่ยนแปลง —"
CLEAR_TOKEN = "-"

# ตัวกรองหน้า "ประวัติการทำรายการ": ชื่อที่แสดง -> ขึ้นต้นของรหัสกิจกรรมในฐานข้อมูล
LOG_FILTERS = {
    "ทั้งหมด": None,
    "เข้าสู่ระบบ": ("LOGIN",),
    "ออกจากระบบ": ("LOGOUT",),
    "เพิ่มครุภัณฑ์": ("INSERT_ASSET",),
    "แก้ไขครุภัณฑ์": ("UPDATE_ASSET",),
    "โอนออก": ("TRANSFER_OUT",),
    "โอนเข้า": ("TRANSFER_IN",),
}

# โครงสร้างฟิลด์ใน pop-up (ใช้ร่วมกันทั้งโหมดดูและโหมดแก้ไข)
# (key, ป้ายชื่อ, ชนิด, จำนวนคอลัมน์ที่กินพื้นที่)  ชนิด: entry | combo | textbox | locked
ASSET_SECTIONS = [
    ("01", "ข้อมูลครุภัณฑ์", [
        ("asset_number", "เลขครุภัณฑ์", "locked", 1),    # ห้ามแก้ไข
        ("brand", "ยี่ห้อ", "entry", 1),
        ("asset_name", "ชื่อครุภัณฑ์", "entry", 2),
        ("category", "ประเภท", "entry", 1),
        ("purchase_date", "วันที่ได้มา (YYYY-MM-DD)", "entry", 1),
        ("created_at", "วันที่บันทึกเข้าระบบ", "locked", 2),
    ]),
    ("02", "หน่วยงานและผู้รับผิดชอบ", [
        ("department", "หน่วยงาน", "entry", 2),
        ("responsible_work", "งานที่รับผิดชอบดูแล", "entry", 1),
        ("holding_work", "งานที่ถือครอง", "entry", 1),
    ]),
    ("03", "สถานที่ตั้ง", [
        ("location", "สถานที่ตั้ง", "entry", 1),
        ("room", "ห้อง", "entry", 1),
        ("floor", "ชั้น", "combo", 1),
        ("zone", "โซน", "combo", 1),
    ]),
    ("04", "สถานะและหมายเหตุ", [
        ("status", "สถานะครุภัณฑ์", "combo", 2),
        ("notes", "หมายเหตุ", "textbox", 2),
    ]),
]

COMBO_OPTIONS = {
    "floor": ["ชั้น 1", "ชั้น 2", "ชั้น 3", "ชั้น 4", "ชั้น 5", "ชั้น 6"],
    "zone": ["Zone A", "Zone B", "Zone C"],
    "status": ["พร้อมใช้งาน", "ชำรุด", "อยู่ระหว่างซ่อมแซม",
               "รอจำหน่าย", "จำหน่ายแล้ว", "ไม่ใช้งาน"],
}

FIELD_LABELS = {
    "asset_number": "เลขครุภัณฑ์", "asset_name": "ชื่อ", "brand": "ยี่ห้อ",
    "category": "ประเภท", "purchase_date": "วันที่ได้มา",
    "department": "หน่วยงาน", "responsible_work": "งานที่รับผิดชอบ",
    "holding_work": "งานที่ถือครอง", "location": "สถานที่",
    "floor": "ชั้น", "zone": "โซน", "room": "ห้อง",
    "status": "สถานะ", "notes": "หมายเหตุ",
}

# สไตล์ CTkComboBox ที่ใช้ร่วมกันทั้งระบบ
# หมายเหตุ: CTkComboBox ไม่รองรับ button_color="transparent" (จะทำให้ widget สร้างไม่สำเร็จ
# และทำให้ทั้งหน้าค้าง) ห้ามใช้ค่านี้ ให้ใช้สีจริงเท่านั้น
COMBO_STYLE = dict(
    border_color=BORDER,
    fg_color=WHITE,
    button_color=NAVY,
    button_hover_color=NAVY_DARK,
    text_color=TEXT,
    dropdown_fg_color=WHITE,
    dropdown_text_color=TEXT,
    dropdown_hover_color="#E8ECF3",
)


class NavyComboBox(ctk.CTkComboBox):
    """CTkComboBox ที่ลูกศร dropdown เป็นสีขาวเสมอ (ปกติลูกศรจะใช้สีเดียวกับตัวอักษร)"""

    ARROW_COLOR = "#FFFFFF"

    def _draw(self, no_color_updates=False):
        super()._draw(no_color_updates)
        try:
            self._canvas.itemconfig("dropdown_arrow", fill=self.ARROW_COLOR)
        except Exception:
            pass


def display_value(asset, key):
    if key == "created_at":
        return format_datetime(asset.get(key))
    return format_value(asset.get(key))


def layout_fields(fields):
    """จัดตำแหน่งฟิลด์ลง grid 2 คอลัมน์ คืนค่า (field, row, col, columnspan)"""
    row, col = 0, 0
    for field in fields:
        span = field[3]
        if span == 2:
            if col == 1:
                row += 1
                col = 0
            yield field, row, 0, 2
            row += 1
            col = 0
        else:
            yield field, row, col, 1
            col += 1
            if col == 2:
                row += 1
                col = 0


def format_value(value):
    """แปลงค่าให้แสดงผลสวยงาม: None/ว่าง -> '-', ตัวเลขทศนิยมที่เป็นจำนวนเต็ม -> int"""
    if value is None or value == "":
        return "-"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


# เขตเวลาที่ใช้แสดงผลวันเวลา
#   None = ใช้เขตเวลาของเครื่องคอมพิวเตอร์ที่เปิดโปรแกรม (ค่าเริ่มต้น)
#   ถ้าต้องการบังคับเป็นเวลาไทยเสมอ ให้เปลี่ยนเป็น: timezone(timedelta(hours=7))
DISPLAY_TZ = None

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def parse_db_datetime(value):
    """
    แปลงวันเวลาจากฐานข้อมูลเป็น datetime ตามเขตเวลาที่แสดงผล
    - Supabase เก็บเวลาเป็น UTC: ค่าที่ไม่มีข้อมูลเขตเวลาจึงถือว่าเป็น UTC
    - ค่าที่เป็นวันที่ล้วน (เช่น 2026-11-03) ไม่มีเวลา จะคืนค่า None
    """
    if not value:
        return None

    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if len(text) <= 10:      # วันที่ล้วน ไม่มีเวลา
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(DISPLAY_TZ) if DISPLAY_TZ else dt.astimezone()


def format_datetime(value):
    """วันเวลาจากฐานข้อมูล -> 'YYYY-MM-DD HH:MM:SS' ตามเวลาท้องถิ่น"""
    if not value:
        return "-"
    dt = parse_db_datetime(value)
    if dt:
        return dt.strftime(DATETIME_FORMAT)
    return str(value)[:19].replace("T", " ")


def build_transfer_timestamp(date_text):
    """
    วันที่โอนที่ผู้ใช้กรอก (YYYY-MM-DD) + เวลาปัจจุบันของเครื่อง -> ข้อความ ISO พร้อมเขตเวลา
    เพื่อเก็บลงฐานข้อมูลให้มีเวลาด้วย
    """
    chosen_date = datetime.strptime(date_text, "%Y-%m-%d").date()
    now = datetime.now().astimezone()
    return datetime.combine(chosen_date, now.time(), tzinfo=now.tzinfo).isoformat(timespec="seconds")


def format_transfer_datetime(item):
    """
    วันที่-เวลาของรายการโอนย้ายสำหรับแสดงในตาราง
    - ถ้า transfer_date มีเวลาอยู่แล้ว -> แสดงตามเวลาท้องถิ่น
    - ถ้าเป็นวันที่ล้วน และมี created_at -> ใช้วันที่เดิม + เวลาที่บันทึกรายการ
    - ไม่เช่นนั้นแสดงเฉพาะวันที่
    """
    raw = item.get("transfer_date")
    dt = parse_db_datetime(raw)
    if dt:
        return dt.strftime(DATETIME_FORMAT)

    created = parse_db_datetime(item.get("created_at"))
    if raw and created:
        return f"{str(raw)[:10]} {created.strftime('%H:%M:%S')}"

    return format_value(raw)


def format_transfer_date(item):
    """วันที่โอนสำหรับแสดงในตาราง (เฉพาะวันที่ ไม่แสดงเวลา)"""
    raw = item.get("transfer_date")
    dt = parse_db_datetime(raw)
    if dt:
        return dt.strftime("%Y-%m-%d")
    return format_value(raw)


def status_color(status, fallback=TEXT):
    if status in STATUS_AVAILABLE:
        return GREEN
    if status in STATUS_DAMAGED:
        return RED
    if status in STATUS_REPAIRING:
        return ORANGE
    return fallback


def to_none(value):
    """ข้อความว่าง หรือ 'ไม่ระบุ' -> None (เก็บเป็น NULL ในฐานข้อมูล)"""
    value = (value or "").strip()
    return None if value in ("", NOT_SPECIFIED) else value


def combo_values(options, current):
    values = [NOT_SPECIFIED] + list(options)
    if current and current not in values:
        values.insert(1, current)
    return values


# ชื่อหน้า (หัวข้อบน header) -> คีย์ของเมนูด้านซ้าย ใช้ไฮไลท์เมนูที่กำลังเปิดอยู่
MENU_BY_TITLE = {
    "Dashboard": "dashboard",
    "เพิ่มรายการครุภัณฑ์": "add",
    "บันทึกโอนย้าย": "transfer",
    "ประวัติการโอนย้าย": "transfer_history",
    "ประวัติการทำรายการ": "logs",
}

# สีของเมนูด้านซ้าย
MENU_ACTIVE_BG = "#30499B"       # พื้นของเมนูที่เลือกอยู่
MENU_HOVER_BG = "#2B4388"        # พื้นตอนเอาเมาส์ชี้เมนูที่ยังไม่เลือก
MENU_TEXT = "#C9D5EE"            # ตัวอักษรเมนูปกติ
MENU_TEXT_ACTIVE = "#FFFFFF"     # ตัวอักษรเมนูที่เลือกอยู่


ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


# =========================================================
# HELPER
# =========================================================

def center_window(window, width, height):
    window.update_idletasks()
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()

    x = (screen_width - width) // 2
    y = (screen_height - height) // 2

    window.geometry(f"{width}x{height}+{x}+{y}")


def bind_enter(widgets, command):
    """
    ให้ช่องกรอก (CTkEntry) กด Enter เพื่อสั่งงาน (รวม Enter ของแป้นตัวเลข)
    command ต้องเป็นฟังก์ชันที่ไม่รับพารามิเตอร์
    """
    def handler(event=None):
        command()
        return "break"

    for widget in widgets:
        for sequence in ("<Return>", "<KP_Enter>"):
            widget.bind(sequence, handler)


def bind_ctrl_enter(textbox, command):
    """ช่องหมายเหตุหลายบรรทัด: Enter = ขึ้นบรรทัดใหม่, Ctrl+Enter = สั่งงาน"""
    def handler(event=None):
        command()
        return "break"

    for sequence in ("<Control-Return>", "<Control-KP_Enter>"):
        textbox.bind(sequence, handler)


def focus_later(window, widget):
    """โฟกัสช่องกรอกหลังหน้าจอวาดเสร็จ (เรียกทันทีจะไม่ติดบางครั้ง)"""
    def _focus():
        try:
            widget.focus_set()
        except Exception:
            pass

    window.after(150, _focus)


def configure_table_columns(frame, columns, uniform_name):
    """
    กำหนดคอลัมน์ grid ให้ Header และ Body ใช้ค่าเดียวกันทุกประการ
    columns = [(ชื่อหัวข้อ, weight, minsize), ...]
    """
    for col_idx, (_, weight, minsize) in enumerate(columns):
        frame.grid_columnconfigure(
            col_idx,
            weight=weight,
            minsize=minsize,
            uniform=uniform_name
        )


# =========================================================
# LOGIN WINDOW
# =========================================================

class LoginWindow(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title(f"RSRM Asset ({CURRENT_VERSION}) - เข้าสู่ระบบ")
        self.configure(fg_color=BG)
        self.resizable(False, False)

        center_window(self, 1050, 650)
        self.create_login_ui()

    def create_login_ui(self):
        main = ctk.CTkFrame(
            self,
            fg_color=WHITE,
            corner_radius=20
        )
        main.pack(fill="both", expand=True, padx=35, pady=35)

        # LEFT PANEL
        left = ctk.CTkFrame(
            main,
            fg_color=NAVY,
            corner_radius=16,
            width=430
        )
        left.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        left.pack_propagate(False)

        ctk.CTkLabel(
            left,
            text="CRA",
            font=(FONT, 54, "bold"),
            text_color=WHITE
        ).pack(pady=(110, 5))

        ctk.CTkLabel(
            left,
            text="ASSET MANAGEMENT",
            font=(FONT, 21, "bold"),
            text_color=WHITE
        ).pack()

        ctk.CTkFrame(
            left,
            fg_color=ORANGE,
            height=4,
            width=75
        ).pack(pady=20)

        ctk.CTkLabel(
            left,
            text="ระบบบริหารจัดการครุภัณฑ์\nราชวิทยาลัยจุฬาภรณ์",
            font=(FONT, 15),
            text_color="#DCE5F7",
            justify="center"
        ).pack(pady=5)

        ctk.CTkLabel(
            left,
            text="CHULABHORN ROYAL ACADEMY",
            font=(FONT, 10),
            text_color="#AABBDD"
        ).pack(side="bottom", pady=30)

        # RIGHT PANEL
        right = ctk.CTkFrame(
            main,
            fg_color=WHITE,
            corner_radius=16
        )
        right.pack(side="right", fill="both", expand=True, padx=35, pady=35)

        ctk.CTkLabel(
            right,
            text="Welcome Back",
            font=(FONT, 29, "bold"),
            text_color=NAVY
        ).pack(anchor="w", pady=(65, 5))

        ctk.CTkLabel(
            right,
            text="เข้าสู่ระบบเพื่อใช้งานระบบบริหารจัดการครุภัณฑ์",
            font=(FONT, 13),
            text_color=MUTED
        ).pack(anchor="w", pady=(0, 30))

        ctk.CTkLabel(
            right,
            text="รหัสพนักงาน",
            font=(FONT, 13, "bold"),
            text_color=TEXT
        ).pack(anchor="w")

        self.employee_entry = ctk.CTkEntry(
            right,
            height=45,
            placeholder_text="กรอกรหัสพนักงาน",
            font=(FONT, 13),
            border_color=BORDER
        )
        self.employee_entry.pack(fill="x", pady=(8, 20))

        ctk.CTkLabel(
            right,
            text="รหัสผ่าน",
            font=(FONT, 13, "bold"),
            text_color=TEXT
        ).pack(anchor="w")

        self.password_entry = ctk.CTkEntry(
            right,
            height=45,
            placeholder_text="กรอกรหัสผ่าน",
            show="●",
            font=(FONT, 13),
            border_color=BORDER
        )
        self.password_entry.pack(fill="x", pady=(8, 25))

        # Enter ที่ช่องรหัสพนักงาน: ถ้ายังไม่กรอกรหัสผ่านให้ไปช่องรหัสผ่านต่อ ถ้ากรอกแล้วให้เข้าสู่ระบบเลย
        def on_employee_enter():
            if self.password_entry.get().strip():
                self.login()
            else:
                self.password_entry.focus_set()

        bind_enter([self.employee_entry], on_employee_enter)
        bind_enter([self.password_entry], self.login)
        focus_later(self, self.employee_entry)

        ctk.CTkButton(
            right,
            text="เข้าสู่ระบบ",
            height=46,
            corner_radius=9,
            fg_color=NAVY,
            hover_color=NAVY_DARK,
            font=(FONT, 14, "bold"),
            command=self.login
        ).pack(fill="x")

        ctk.CTkLabel(
            right,
            text="CRA ASSET MANAGEMENT SYSTEM",
            font=(FONT, 11),
            text_color=MUTED
        ).pack(side="bottom", pady=15)

    def login(self):
        employee_id = self.employee_entry.get().strip()
        password = self.password_entry.get().strip()

        if not employee_id or not password:
            messagebox.showwarning(
                "ข้อมูลไม่ครบถ้วน",
                "กรุณากรอกรหัสพนักงานและรหัสผ่าน"
            )
            return

        try:
            user = login_user(employee_id, password)

            if not user:
                messagebox.showerror(
                    "เข้าสู่ระบบไม่สำเร็จ",
                    "รหัสพนักงานหรือรหัสผ่านไม่ถูกต้อง"
                )
                return

            log_action(
                employee_id,
                "LOGIN",
                "เข้าสู่ระบบ CRA Asset Management"
            )

            self.destroy()

            app = MainDashboard(user)
            app.mainloop()

        except Exception as e:
            messagebox.showerror(
                "เกิดข้อผิดพลาด",
                f"ไม่สามารถเข้าสู่ระบบได้\n{e}"
            )


# =========================================================
# โหลดไอคอน Line Icons สำหรับเมนูด้านซ้ายและปุ่มจัดการ
# =========================================================
ICONS = {
    "dashboard": ctk.CTkImage(Image.open(resource_path("icons/dashboard.png")), size=(18, 18)),
    "add": ctk.CTkImage(Image.open(resource_path("icons/add.png")), size=(18, 18)),
    "transfer": ctk.CTkImage(Image.open(resource_path("icons/transfer.png")), size=(18, 18)),
    "history": ctk.CTkImage(Image.open(resource_path("icons/history.png")), size=(18, 18)),
    "edit": ctk.CTkImage(Image.open(resource_path("icons/edit.png")), size=(16, 16)),
}


def make_eye_icon(color=NAVY, size=18):
    """วาดไอคอนรูปตาด้วยโค้ด (ไม่ต้องมีไฟล์ icons/view.png)"""
    scale = 8
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = max(2, int(s * 0.09))
    d.ellipse((s * 0.08, s * 0.27, s * 0.92, s * 0.73), outline=color, width=w)
    r = s * 0.13
    d.ellipse((s / 2 - r, s / 2 - r, s / 2 + r, s / 2 + r), fill=color)
    img = img.resize((size * 4, size * 4), Image.LANCZOS)
    return ctk.CTkImage(img, size=(size, size))


ICONS["view"] = make_eye_icon()


# =========================================================
# MAIN DASHBOARD
# =========================================================

class MainDashboard(ctk.CTk):

    def __init__(self, user):
        super().__init__()

        self.user = user
        self.current_page = None
        self.form_fields = {}
        self.all_assets = []
        self.filtered_assets = []
        self.assets_stale = False      # True = ข้อมูลครุภัณฑ์ในหน่วยความจำเก่าแล้ว ต้องโหลดใหม่
        self.dashboard_page = 0
        self.stat_values = {}
        self._dashboard_token = None
        self.menu_items = {}

        self.title(f"RSRM Asset ({CURRENT_VERSION}) - ระบบบริหารจัดการครุภัณฑ์")
        self.configure(fg_color=BG)
        self.minsize(1100, 700)

        center_window(self, 1400, 850)

        self.create_layout()
        self.show_dashboard()

        # 📌 ตรวจสอบเวอร์ชันหลังเปิดโปรแกรม 2 วินาที
        self.after(2000, lambda: check_for_updates(self))

    def create_layout(self):
        self.sidebar = ctk.CTkFrame(
            self,
            width=245,
            fg_color=NAVY,
            corner_radius=0
        )
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.create_sidebar()

        self.main_area = ctk.CTkFrame(
            self,
            fg_color=BG,
            corner_radius=0
        )
        self.main_area.pack(
            side="right",
            fill="both",
            expand=True
        )

        self.header = ctk.CTkFrame(
            self.main_area,
            height=75,
            fg_color=WHITE,
            corner_radius=0
        )
        self.header.pack(fill="x")
        self.header.pack_propagate(False)

        self.header_title = ctk.CTkLabel(
            self.header,
            text="Dashboard",
            font=(FONT, 20, "bold"),
            text_color=NAVY
        )
        self.header_title.pack(side="left", padx=30)

        self.user_label = ctk.CTkLabel(
            self.header,
            text=self.get_user_name(),
            font=(FONT, 13, "bold"),
            text_color=TEXT
        )
        self.user_label.pack(side="right", padx=30)

        self.content = ctk.CTkFrame(
            self.main_area,
            fg_color=BG,
            corner_radius=0
        )
        self.content.pack(
            fill="both",
            expand=True,
            padx=25,
            pady=20
        )

    def create_sidebar(self):
        ctk.CTkLabel(
            self.sidebar,
            text="CRA",
            font=(FONT, 35, "bold"),
            text_color=WHITE
        ).pack(pady=(30, 0))

        ctk.CTkLabel(
            self.sidebar,
            text="ASSET MANAGEMENT",
            font=(FONT, 12, "bold"),
            text_color=WHITE
        ).pack(pady=(0, 5))

        ctk.CTkLabel(
            self.sidebar,
            text="CHULABHORN ROYAL ACADEMY",
            font=(FONT, 9),
            text_color="#B9C8E5"
        ).pack(pady=(0, 30))

        # 📌 เพิ่มส่วนแสดงเลขเวอร์ชันตรงนี้
        ctk.CTkLabel(
            self.sidebar,
            text=f"Version {CURRENT_VERSION}",
            font=(FONT, 10, "bold"),
            text_color="#F36C21"
        ).pack(pady=(0, 15))

        ctk.CTkFrame(
            self.sidebar,
            height=1,
            fg_color="#52699B"
        ).pack(fill="x", padx=20, pady=5)

        self.menu_button("dashboard", "    Dashboard", ICONS["dashboard"], self.show_dashboard)
        self.menu_button("add", "    เพิ่มครุภัณฑ์", ICONS["add"], self.show_add_asset)
        self.menu_button("transfer", "    บันทึกโอนย้าย", ICONS["transfer"], self.show_transfer)
        self.menu_button("transfer_history", "    ประวัติการโอนย้าย", ICONS["history"], self.show_transfer_history)
        self.menu_button("logs", "    ประวัติการทำรายการ", ICONS["history"], self.show_logs)

        ctk.CTkFrame(
            self.sidebar,
            fg_color="transparent"
        ).pack(fill="both", expand=True)

        ctk.CTkButton(
            self.sidebar,
            text="ออกจากระบบ",
            fg_color=ORANGE,
            hover_color="#D85A14",
            text_color=WHITE,
            height=42,
            corner_radius=8,
            font=(FONT, 13, "bold"),
            command=self.logout
        ).pack(fill="x", padx=18, pady=25)

    def menu_button(self, key, text, icon, command):
        """เมนูด้านซ้าย: แถบสีส้มเล็ก ๆ ด้านซ้าย + พื้นสว่างขึ้นเมื่อเป็นเมนูที่เลือกอยู่"""
        row = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=46)
        row.pack(fill="x", padx=15, pady=4)
        row.pack_propagate(False)

        bar = ctk.CTkFrame(row, width=4, fg_color="transparent", corner_radius=2)
        bar.pack(side="left", fill="y", padx=(0, 6), pady=9)

        button = ctk.CTkButton(
            row,
            text=text,
            image=icon,
            compound="left",
            anchor="w",
            height=46,
            corner_radius=8,
            fg_color="transparent",
            hover_color=MENU_HOVER_BG,
            text_color=MENU_TEXT,
            font=(FONT, 13),
            command=command
        )
        button.pack(side="left", fill="both", expand=True)

        self.menu_items[key] = (button, bar)

    def highlight_menu(self, active_key):
        """ไฮไลท์เมนูที่กำลังเปิดอยู่ และคืนสีเมนูอื่นเป็นปกติ"""
        for key, (button, bar) in self.menu_items.items():
            try:
                if key == active_key:
                    button.configure(
                        fg_color=MENU_ACTIVE_BG,
                        hover_color=MENU_ACTIVE_BG,
                        text_color=MENU_TEXT_ACTIVE,
                        font=(FONT, 13, "bold")
                    )
                    bar.configure(fg_color=ORANGE)
                else:
                    button.configure(
                        fg_color="transparent",
                        hover_color=MENU_HOVER_BG,
                        text_color=MENU_TEXT,
                        font=(FONT, 13)
                    )
                    bar.configure(fg_color="transparent")
            except Exception:
                pass

    def get_user_name(self):
        first = self.user.get("first_name", "")
        last = self.user.get("last_name", "")
        if first or last:
            return f"{first} {last}".strip()
        return self.user.get("employee_id", "ผู้ใช้งาน")

    def clear_content(self, title):
        self._dashboard_token = None

        # ป้องกันหน้าเดิมที่มี widget พัง ลบไม่ออก แล้วทำให้เมนูทั้งหมดกดไม่ได้
        for widget in self.content.winfo_children():
            try:
                widget.destroy()
            except Exception:
                try:
                    widget.pack_forget()
                except Exception:
                    pass

        self.header_title.configure(text=title)
        self.current_page = title
        self.highlight_menu(MENU_BY_TITLE.get(title))

    def page_heading(self, title, subtitle):
        ctk.CTkLabel(
            self.content,
            text=title,
            font=(FONT, 24, "bold"),
            text_color=NAVY
        ).pack(anchor="w")

        ctk.CTkLabel(
            self.content,
            text=subtitle,
            font=(FONT, 13),
            text_color=MUTED
        ).pack(anchor="w", pady=(3, 18))

    def ensure_assets(self):
        """ให้แน่ใจว่ามีข้อมูลครุภัณฑ์ล่าสุดในหน่วยความจำ (ใช้กับหน้าโอนย้าย)"""
        if self.all_assets and not self.assets_stale:
            return
        try:
            self.all_assets = fetch_assets() or []
            self.assets_stale = False
        except Exception as e:
            messagebox.showerror(
                "Database Error",
                f"ไม่สามารถโหลดข้อมูลครุภัณฑ์ได้\n{e}",
                parent=self
            )

    # DASHBOARD
    def show_dashboard(self):
        self.clear_content("Dashboard")
        self.page_heading(
            "ภาพรวมระบบครุภัณฑ์",
            "CRA Asset Management System | ศูนย์รวมสรุปข้อมูลและจัดการรายการครุภัณฑ์"
        )

        token = object()
        self._dashboard_token = token
        self.all_assets = []
        self.filtered_assets = []
        self.dashboard_page = 0
        self.stat_values = {}

        stats = ctk.CTkFrame(self.content, fg_color="transparent")
        stats.pack(fill="x", pady=(0, 15))
        stats.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.stat_card(stats, 0, "ครุภัณฑ์ทั้งหมด", "-", NAVY, "total")
        self.stat_card(stats, 1, "พร้อมใช้งาน", "-", GREEN, "available")
        self.stat_card(stats, 2, "ชำรุด", "-", RED, "damaged")
        self.stat_card(stats, 3, "อยู่ระหว่างซ่อม", "-", ORANGE, "repairing")

        search_bar = ctk.CTkFrame(self.content, fg_color=WHITE, corner_radius=10)
        search_bar.pack(fill="x", pady=(0, 12))

        self.dashboard_search_entry = ctk.CTkEntry(
            search_bar,
            height=38,
            placeholder_text="ค้นหาเลขครุภัณฑ์ ชื่อครุภัณฑ์ ยี่ห้อ หรือหน่วยงาน",
            font=(FONT, 12),
            border_color=BORDER
        )
        self.dashboard_search_entry.pack(
            side="left", fill="x", expand=True, padx=15, pady=10
        )
        self.dashboard_search_entry.bind(
            "<Return>", lambda event: self.apply_dashboard_filter()
        )

        ctk.CTkButton(
            search_bar,
            text="ค้นหา",
            width=90,
            height=38,
            fg_color=NAVY,
            font=(FONT, 12, "bold"),
            command=self.apply_dashboard_filter
        ).pack(side="right", padx=15)

        table_frame = ctk.CTkFrame(
            self.content,
            fg_color=WHITE,
            corner_radius=12,
            border_width=1,
            border_color=BORDER
        )
        table_frame.pack(fill="both", expand=True, pady=(5, 0))

        ctk.CTkLabel(
            table_frame,
            text="รายการครุภัณฑ์ทั้งหมดในระบบ",
            font=(FONT, 16, "bold"),
            text_color=NAVY
        ).pack(anchor="w", padx=20, pady=(15, 10))

        self.dashboard_table_container = ctk.CTkFrame(table_frame, fg_color="transparent")
        self.dashboard_table_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        ctk.CTkLabel(
            self.dashboard_table_container,
            text="กำลังโหลดข้อมูล...",
            font=(FONT, 14),
            text_color=MUTED
        ).pack(pady=80)

        self.update_idletasks()
        self.load_assets_async(token)

    def load_assets_async(self, token):
        result_queue = queue.Queue()

        def worker():
            try:
                result_queue.put(("ok", fetch_assets()))
            except Exception as e:
                result_queue.put(("err", e))

        threading.Thread(target=worker, daemon=True).start()

        def poll():
            if self._dashboard_token is not token:
                return

            try:
                status, payload = result_queue.get_nowait()
            except queue.Empty:
                self.after(80, poll)
                return

            if status == "err":
                self.all_assets = []
                messagebox.showerror(
                    "Database Error",
                    f"ไม่สามารถโหลดข้อมูลครุภัณฑ์ได้\n{payload}"
                )
            else:
                self.all_assets = payload or []
                self.assets_stale = False

            self.filtered_assets = self.all_assets
            self.dashboard_page = 0
            self.update_stat_cards()
            self.create_asset_table(self.dashboard_table_container, self.filtered_assets)

        poll()

    def update_stat_cards(self):
        assets = self.all_assets
        values = {
            "total": len(assets),
            "available": sum(1 for a in assets if a.get("status") in STATUS_AVAILABLE),
            "damaged": sum(1 for a in assets if a.get("status") in STATUS_DAMAGED),
            "repairing": sum(1 for a in assets if a.get("status") in STATUS_REPAIRING),
        }
        for key, value in values.items():
            label = self.stat_values.get(key)
            if label is not None:
                label.configure(text=str(value))

    def apply_dashboard_filter(self):
        keyword = self.dashboard_search_entry.get().strip().lower()

        if keyword:
            self.filtered_assets = [
                a for a in self.all_assets
                if keyword in " ".join(
                    str(a.get(k) or "")
                    for k in ("asset_number", "asset_name", "brand", "department", "location")
                ).lower()
            ]
        else:
            self.filtered_assets = self.all_assets

        self.dashboard_page = 0
        self.create_asset_table(self.dashboard_table_container, self.filtered_assets)

    def go_dashboard_page(self, page):
        self.dashboard_page = page
        self.create_asset_table(self.dashboard_table_container, self.filtered_assets)

    def stat_card(self, parent, column, title, value, color, key=None):
        card = ctk.CTkFrame(
            parent,
            fg_color=WHITE,
            corner_radius=12,
            border_width=1,
            border_color=BORDER
        )
        card.grid(
            row=0,
            column=column,
            sticky="nsew",
            padx=6,
            pady=5
        )

        ctk.CTkLabel(
            card,
            text=title,
            font=(FONT, 13),
            text_color=MUTED
        ).pack(anchor="w", padx=18, pady=(18, 5))

        value_label = ctk.CTkLabel(
            card,
            text=str(value),
            font=(FONT, 34, "bold"),
            text_color=color
        )
        value_label.pack(anchor="w", padx=18, pady=(0, 18))

        if key:
            self.stat_values[key] = value_label

    # ASSET FORM
    def show_add_asset(self):
        self.clear_content("เพิ่มรายการครุภัณฑ์")
        self.page_heading(
            "เพิ่มรายการครุภัณฑ์ใหม่",
            "กรอกรายละเอียดครุภัณฑ์เพื่อบันทึกเข้าสู่ฐานข้อมูล"
        )

        scroll = ctk.CTkScrollableFrame(
            self.content,
            fg_color="transparent"
        )
        scroll.pack(fill="both", expand=True)

        self.form_fields = {}

        grid = ctk.CTkFrame(scroll, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure((0, 1), weight=1)

        self.create_asset_card(
            grid, 0, 0, "01", "ข้อมูลครุภัณฑ์",
            [
                ("asset_number", "เลขครุภัณฑ์", "entry", None),
                ("asset_name", "ชื่อครุภัณฑ์", "entry", None),
                ("brand", "ยี่ห้อ", "entry", None),
                ("purchase_date", "วันที่ได้มา (YYYY-MM-DD)", "entry", None)
            ]
        )

        self.create_asset_card(
            grid, 0, 1, "02", "หน่วยงานและผู้รับผิดชอบ",
            [
                ("department", "หน่วยงาน", "combo", ["เลือกหน่วยงาน", "สำนักบริหารวิจัยและนวัตกรรม"]),
                ("responsible_work", "งานที่รับผิดชอบดูแล", "entry", None),
                ("holding_work", "งานที่ถือครอง", "entry", None)
            ]
        )

        self.create_asset_card(
            grid, 1, 0, "03", "สถานที่ตั้ง",
            [
                ("location", "สถานที่ตั้ง", "combo", ["เลือกสถานที่ตั้ง", "อาคารสำนักงาน", "อาคารเรียน", "อาคารวิจัย"]),
                ("floor", "ชั้น", "combo", ["เลือกชั้น", "ชั้น 1", "ชั้น 2", "ชั้น 3", "ชั้น 4", "ชั้น 5", "ชั้น 6"]),
                ("zone", "โซน", "combo", ["เลือกโซน", "Zone A", "Zone B", "Zone C"]),
                ("room", "ห้อง", "entry", None)
            ]
        )

        self.create_asset_card(
            grid, 1, 1, "04", "สถานะและรายละเอียดเพิ่มเติม",
            [
                ("status", "สถานะครุภัณฑ์", "combo", ["พร้อมใช้งาน", "ชำรุด", "อยู่ระหว่างซ่อมแซม", "รอจำหน่าย", "จำหน่ายแล้ว", "ไม่ใช้งาน"]),
                ("notes", "หมายเหตุ", "textbox", None)
            ]
        )

        button_area = ctk.CTkFrame(scroll, fg_color="transparent")
        button_area.pack(fill="x", pady=20)

        ctk.CTkButton(
            button_area,
            text="ล้างข้อมูล",
            width=110,
            height=42,
            fg_color="#E8ECF3",
            hover_color="#DCE2EC",
            text_color=TEXT,
            font=(FONT, 13),
            command=self.clear_form
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            button_area,
            text="ยกเลิก",
            width=110,
            height=42,
            fg_color="#E8ECF3",
            hover_color="#DCE2EC",
            text_color=TEXT,
            font=(FONT, 13),
            command=self.show_dashboard
        ).pack(side="right", padx=5)

        ctk.CTkButton(
            button_area,
            text="บันทึกข้อมูล",
            width=150,
            height=42,
            fg_color=NAVY,
            hover_color=NAVY_DARK,
            font=(FONT, 13, "bold"),
            command=self.save_asset
        ).pack(side="right", padx=5)

        # Enter ในช่องกรอก = บันทึกข้อมูล | ช่องหมายเหตุใช้ Ctrl+Enter
        bind_enter(
            [w for w in self.form_fields.values() if isinstance(w, ctk.CTkEntry)],
            self.save_asset
        )
        for w in self.form_fields.values():
            if isinstance(w, ctk.CTkTextbox):
                bind_ctrl_enter(w, self.save_asset)
        if "asset_number" in self.form_fields:
            focus_later(self, self.form_fields["asset_number"])

    def create_asset_card(self, parent, row, column, number, title, fields):
        card = ctk.CTkFrame(
            parent,
            fg_color=WHITE,
            corner_radius=12,
            border_width=1,
            border_color=BORDER
        )
        card.grid(row=row, column=column, sticky="nsew", padx=7, pady=7)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(18, 12))

        ctk.CTkLabel(
            header,
            text=number,
            font=(FONT, 13, "bold"),
            text_color=ORANGE
        ).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            header,
            text=title,
            font=(FONT, 15, "bold"),
            text_color=NAVY
        ).pack(side="left")

        for key, label, field_type, options in fields:
            field_box = ctk.CTkFrame(card, fg_color="transparent")
            field_box.pack(fill="x", padx=18, pady=(3, 10))

            ctk.CTkLabel(
                field_box,
                text=label,
                font=(FONT, 12, "bold"),
                text_color=TEXT
            ).pack(anchor="w", pady=(0, 5))

            if field_type == "entry":
                widget = ctk.CTkEntry(
                    field_box,
                    height=38,
                    placeholder_text=f"กรอก{label}",
                    font=(FONT, 12),
                    border_color=BORDER
                )
            elif field_type == "combo":
                widget = NavyComboBox(
                    field_box,
                    values=options,
                    height=38,
                    font=(FONT, 12),
                    dropdown_font=(FONT, 12),
                    state="readonly",
                    **COMBO_STYLE
                )
                widget.set(options[0])
            elif field_type == "textbox":
                widget = ctk.CTkTextbox(
                    field_box,
                    height=95,
                    font=(FONT, 12),
                    border_color=BORDER,
                    border_width=1
                )

            widget.pack(fill="x")
            self.form_fields[key] = widget

    def clear_form(self):
        for key, widget in self.form_fields.items():
            if isinstance(widget, ctk.CTkTextbox):
                widget.delete("1.0", "end")
            elif isinstance(widget, ctk.CTkComboBox):
                if key == "status":
                    widget.set("พร้อมใช้งาน")
                elif key == "department":
                    widget.set("เลือกหน่วยงาน")
                elif key == "location":
                    widget.set("เลือกสถานที่ตั้ง")
                elif key == "floor":
                    widget.set("เลือกชั้น")
                elif key == "zone":
                    widget.set("เลือกโซน")
            else:
                widget.delete(0, "end")

    def save_asset(self):
        data = {}
        for key, widget in self.form_fields.items():
            if isinstance(widget, ctk.CTkTextbox):
                value = widget.get("1.0", "end").strip()
            else:
                value = widget.get().strip()

            if value.startswith("เลือก"):
                value = ""

            data[key] = value if value else None

        required_fields = {
            "asset_number": "เลขครุภัณฑ์",
            "asset_name": "ชื่อครุภัณฑ์",
            "purchase_date": "วันที่ได้มา",
            "department": "หน่วยงาน",
            "location": "สถานที่ตั้ง",
            "status": "สถานะครุภัณฑ์"
        }

        missing = [
            label for key, label in required_fields.items()
            if not data.get(key)
        ]

        if missing:
            messagebox.showwarning(
                "กรุณากรอกข้อมูลให้ครบ",
                "กรุณาตรวจสอบข้อมูลต่อไปนี้:\n\n" + "\n".join(missing)
            )
            return

        try:
            datetime.strptime(data["purchase_date"], "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning(
                "รูปแบบวันที่ไม่ถูกต้อง",
                "กรุณาระบุวันที่ในรูปแบบ YYYY-MM-DD\nตัวอย่าง 2026-10-01"
            )
            return

        try:
            insert_asset(data)
            self.assets_stale = True

            log_action(
                self.user.get("employee_id"),
                "INSERT_ASSET",
                f"เพิ่มครุภัณฑ์ {data['asset_number']} - {data['asset_name']}"
            )

            messagebox.showinfo(
                "บันทึกสำเร็จ",
                "บันทึกข้อมูลครุภัณฑ์เรียบร้อยแล้ว"
            )
            self.clear_form()

        except Exception as e:
            messagebox.showerror(
                "บันทึกไม่สำเร็จ",
                f"ไม่สามารถบันทึกข้อมูลได้\n\n{e}"
            )

    # ตารางแสดงรายการครุภัณฑ์
    def create_asset_table(self, parent, assets):
        for widget in parent.winfo_children():
            widget.destroy()

        columns = [
            ("ลำดับ",        5,  60),
            ("เลขครุภัณฑ์", 14, 130),
            ("ชื่อครุภัณฑ์", 20, 200),
            ("ยี่ห้อ",        11, 100),
            ("หน่วยงาน",     18, 180),
            ("สถานที่ตั้ง",    14, 120),
            ("สถานะ",         10, 90),
            ("จัดการ",        11, 110),
        ]

        COL_SEQ, COL_NUMBER, COL_STATUS, COL_ACTION = 0, 1, 6, 7

        total = len(assets)
        pages = max(1, -(-total // PAGE_SIZE))
        page = min(max(self.dashboard_page, 0), pages - 1)
        self.dashboard_page = page
        start = page * PAGE_SIZE
        end = min(start + PAGE_SIZE, total)
        page_assets = assets[start:end]

        table_wrapper = ctk.CTkFrame(parent, fg_color="transparent")
        table_wrapper.pack(fill="both", expand=True, padx=10, pady=10)

        header_frame = ctk.CTkFrame(
            table_wrapper, fg_color="#E8ECF5", corner_radius=8, height=40
        )
        header_frame.pack(fill="x", pady=(0, 5), padx=(0, SCROLLBAR_SPACE))
        header_frame.pack_propagate(False)
        header_frame.grid_propagate(False)
        header_frame.grid_rowconfigure(0, weight=1)
        configure_table_columns(header_frame, columns, "asset_cols")

        for col_idx, (title, _, _) in enumerate(columns):
            ctk.CTkLabel(
                header_frame,
                text=title,
                font=(FONT, 12, "bold"),
                text_color=NAVY,
                anchor="center"
            ).grid(row=0, column=col_idx, sticky="nsew", padx=4)

        if total > 0:
            pager = ctk.CTkFrame(table_wrapper, fg_color="transparent", height=44)
            pager.pack(side="bottom", fill="x", pady=(6, 0))

            ctk.CTkLabel(
                pager,
                text=f"แสดง {start + 1}–{end} จาก {total} รายการ",
                font=(FONT, 12), text_color=MUTED
            ).pack(side="left", padx=6)

            ctk.CTkButton(
                pager, text="ถัดไป", width=90, height=32, corner_radius=8,
                fg_color="#E8ECF5", hover_color="#D6DEEE",
                text_color=NAVY, font=(FONT, 12),
                state="normal" if page < pages - 1 else "disabled",
                command=lambda: self.go_dashboard_page(page + 1)
            ).pack(side="right", padx=(6, 6))

            ctk.CTkLabel(
                pager, text=f"หน้า {page + 1} / {pages}",
                font=(FONT, 12, "bold"), text_color=NAVY
            ).pack(side="right", padx=10)

            ctk.CTkButton(
                pager, text="ก่อนหน้า", width=90, height=32, corner_radius=8,
                fg_color="#E8ECF5", hover_color="#D6DEEE",
                text_color=NAVY, font=(FONT, 12),
                state="normal" if page > 0 else "disabled",
                command=lambda: self.go_dashboard_page(page - 1)
            ).pack(side="right", padx=(6, 0))

        body_scroll = ctk.CTkScrollableFrame(
            table_wrapper, fg_color=WHITE, corner_radius=8
        )
        body_scroll.pack(fill="both", expand=True)
        configure_table_columns(body_scroll, columns, "asset_cols")

        if not page_assets:
            ctk.CTkLabel(
                body_scroll,
                text="ไม่พบข้อมูลครุภัณฑ์",
                font=(FONT, 13),
                text_color=MUTED
            ).grid(row=0, column=0, columnspan=len(columns), pady=35)
            return

        for row_idx, asset in enumerate(page_assets):
            row_bg = "#FFFFFF" if row_idx % 2 == 0 else "#F7F9FC"

            values = [
                start + row_idx + 1,
                asset.get("asset_number"),
                asset.get("asset_name"),
                asset.get("brand"),
                asset.get("department"),
                asset.get("location"),
                asset.get("status"),
            ]

            for col_idx, value in enumerate(values):
                if col_idx == COL_STATUS:
                    text_color = status_color(value)
                elif col_idx == COL_SEQ:
                    text_color = MUTED
                else:
                    text_color = TEXT

                ctk.CTkLabel(
                    body_scroll,
                    text=format_value(value),
                    font=(FONT, 12, "bold" if col_idx == COL_NUMBER else "normal"),
                    text_color=text_color,
                    anchor="center" if col_idx in (COL_SEQ, COL_NUMBER, COL_STATUS) else "w",
                    fg_color=row_bg,
                    corner_radius=0,
                    height=34
                ).grid(row=row_idx, column=col_idx, sticky="nsew", padx=2, pady=1)

            action_wrapper = ctk.CTkFrame(
                body_scroll, fg_color=row_bg, corner_radius=0, height=34
            )
            action_wrapper.grid(row=row_idx, column=COL_ACTION, sticky="nsew", padx=2, pady=1)
            action_wrapper.grid_propagate(False)

            btn_box = ctk.CTkFrame(action_wrapper, fg_color="transparent")
            btn_box.pack(expand=True)

            ctk.CTkButton(
                btn_box,
                text="",
                image=ICONS["view"],
                fg_color="#E8ECF5",
                hover_color="#D6DEEE",
                height=28,
                width=34,
                corner_radius=6,
                command=lambda a=asset: self.open_view_dialog(a)
            ).pack(side="left", padx=3)

            ctk.CTkButton(
                btn_box,
                text="",
                image=ICONS["edit"],
                fg_color=NAVY,
                hover_color=NAVY_DARK,
                height=28,
                width=34,
                corner_radius=6,
                command=lambda a=asset: self.open_edit_dialog(a)
            ).pack(side="left", padx=3)

    def create_dialog_shell(self, asset, mode_text, mode_bg, mode_fg):
        asset_number = format_value(asset.get("asset_number"))
        original_status = asset.get("status") or ""

        dialog = ctk.CTkToplevel(self)
        dialog.title(f"{mode_text}: {asset_number}")
        dialog.configure(fg_color=BG)
        dialog.resizable(False, False)

        height = min(860, self.winfo_screenheight() - 100)
        center_window(dialog, 900, height)
        dialog.transient(self)
        dialog.after(150, dialog.grab_set)
        dialog.after(150, dialog.focus_force)
        dialog.bind("<Escape>", lambda e: dialog.destroy())

        header = ctk.CTkFrame(dialog, fg_color=WHITE, corner_radius=0, height=96)
        header.pack(fill="x")
        header.pack_propagate(False)

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left", fill="both", expand=True, padx=28, pady=16)

        top_row = ctk.CTkFrame(title_box, fg_color="transparent")
        top_row.pack(anchor="w")

        ctk.CTkLabel(
            top_row, text=f"เลขครุภัณฑ์  {asset_number}",
            font=(FONT, 12), text_color=MUTED
        ).pack(side="left")

        ctk.CTkLabel(
            top_row, text=f"  {mode_text}  ",
            font=(FONT, 10, "bold"), text_color=mode_fg,
            fg_color=mode_bg, corner_radius=8, height=20
        ).pack(side="left", padx=10)

        ctk.CTkLabel(
            title_box, text=format_value(asset.get("asset_name")),
            font=(FONT, 20, "bold"), text_color=NAVY,
            wraplength=640, justify="left"
        ).pack(anchor="w", pady=(4, 0))

        status_badge = ctk.CTkLabel(
            header,
            text=original_status or "ไม่ระบุสถานะ",
            font=(FONT, 12, "bold"), text_color=WHITE,
            fg_color=status_color(original_status, fallback=MUTED),
            corner_radius=14, width=120, height=30
        )
        status_badge.pack(side="right", padx=28)

        ctk.CTkFrame(dialog, fg_color=BORDER, height=1, corner_radius=0).pack(fill="x")

        footer = ctk.CTkFrame(dialog, fg_color=WHITE, corner_radius=0, height=74)
        footer.pack(side="bottom", fill="x")
        footer.pack_propagate(False)
        ctk.CTkFrame(dialog, fg_color=BORDER, height=1, corner_radius=0).pack(side="bottom", fill="x")

        scroll = ctk.CTkScrollableFrame(dialog, fg_color=BG, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=10, pady=(8, 0))

        return dialog, status_badge, scroll, footer

    def dialog_section(self, parent, number, title):
        card = ctk.CTkFrame(
            parent, fg_color=WHITE, corner_radius=12,
            border_width=1, border_color=BORDER
        )
        card.pack(fill="x", padx=8, pady=7)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=22, pady=(16, 4))

        ctk.CTkLabel(
            head, text=number,
            font=(FONT, 13, "bold"), text_color=ORANGE
        ).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            head, text=title,
            font=(FONT, 15, "bold"), text_color=NAVY
        ).pack(side="left")

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=14, pady=(4, 12))
        body.grid_columnconfigure((0, 1), weight=1, uniform="dlg_cols")
        return body

    def open_view_dialog(self, asset):
        dialog, _badge, scroll, footer = self.create_dialog_shell(
            asset, "ดูข้อมูล", "#E8ECF5", NAVY
        )

        for number, title, fields in ASSET_SECTIONS:
            body = self.dialog_section(scroll, number, title)

            for (key, label, _kind, _span), row, col, cspan in layout_fields(fields):
                cell = ctk.CTkFrame(body, fg_color="transparent")
                cell.grid(row=row, column=col, columnspan=cspan,
                          sticky="nsew", padx=8, pady=(6, 10))

                ctk.CTkLabel(
                    cell, text=label,
                    font=(FONT, 11), text_color=MUTED
                ).pack(anchor="w")

                if key == "status":
                    value_color = status_color(asset.get(key), fallback=TEXT)
                else:
                    value_color = TEXT

                ctk.CTkLabel(
                    cell, text=display_value(asset, key),
                    font=(FONT, 14, "bold" if key in ("asset_number", "asset_name", "status") else "normal"),
                    text_color=value_color,
                    wraplength=380 if cspan == 1 else 800,
                    justify="left", anchor="w"
                ).pack(anchor="w", pady=(3, 0))

        def go_edit():
            dialog.destroy()
            self.open_edit_dialog(asset)

        ctk.CTkButton(
            footer, text="แก้ไขข้อมูล",
            width=150, height=42, corner_radius=9,
            fg_color=NAVY, hover_color=NAVY_DARK,
            font=(FONT, 13, "bold"), command=go_edit
        ).pack(side="right", padx=(8, 28), pady=16)

        ctk.CTkButton(
            footer, text="ปิด",
            width=110, height=42, corner_radius=9,
            fg_color="#E8ECF3", hover_color="#DCE2EC",
            text_color=TEXT, font=(FONT, 13),
            command=dialog.destroy
        ).pack(side="right", padx=8, pady=16)

    def edit_field(self, parent, inputs, asset, key, label, kind, span, row, col,
                   status_callback=None):
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.grid(row=row, column=col, columnspan=span,
                  sticky="nsew", padx=8, pady=(6, 10))

        wrap = 330 if span == 1 else 740

        ctk.CTkLabel(
            cell, text=label,
            font=(FONT, 12, "bold"), text_color=TEXT
        ).pack(anchor="w")

        if kind == "locked":
            box = ctk.CTkFrame(cell, fg_color="#F1F3F8", corner_radius=8)
            box.pack(fill="x", pady=(6, 0))

            ctk.CTkLabel(
                box, text=display_value(asset, key),
                font=(FONT, 13, "bold"), text_color=MUTED, anchor="w"
            ).pack(side="left", padx=12, pady=9)

            ctk.CTkLabel(
                box, text="แก้ไขไม่ได้",
                font=(FONT, 10), text_color=MUTED
            ).pack(side="right", padx=12)
            return

        old_row = ctk.CTkFrame(cell, fg_color="transparent")
        old_row.pack(fill="x", pady=(3, 6))

        ctk.CTkLabel(
            old_row, text="เดิม",
            font=(FONT, 10), text_color=MUTED,
            fg_color="#EEF2F9", corner_radius=6, width=36, height=20
        ).pack(side="left", anchor="n", padx=(0, 8))

        ctk.CTkLabel(
            old_row, text=display_value(asset, key),
            font=(FONT, 12), text_color=MUTED,
            wraplength=wrap, justify="left", anchor="w"
        ).pack(side="left", fill="x", expand=True)

        if kind == "entry":
            widget = ctk.CTkEntry(
                cell, height=38, font=(FONT, 12), border_color=BORDER,
                placeholder_text="ข้อมูลใหม่ (เว้นว่าง = คงค่าเดิม)"
            )
            widget.bind(
                "<KeyRelease>",
                lambda e, w=widget: w.configure(
                    border_color=ORANGE if w.get().strip() else BORDER
                )
            )

        elif kind == "combo":
            options = list(COMBO_OPTIONS.get(key, []))
            current = asset.get(key)
            if current and current not in options:
                options.insert(0, current)

            widget = NavyComboBox(
                cell,
                values=[KEEP_CURRENT] + options,
                height=38,
                font=(FONT, 12),
                dropdown_font=(FONT, 12),
                state="readonly",
                **COMBO_STYLE
            )
            widget.set(KEEP_CURRENT)

            def on_pick(value, w=widget):
                w.configure(border_color=ORANGE if value != KEEP_CURRENT else BORDER)
                if status_callback:
                    status_callback(value)

            widget.configure(command=on_pick)

        else:
            widget = ctk.CTkTextbox(
                cell, height=90, font=(FONT, 12),
                border_color=BORDER, border_width=1
            )
            widget.bind(
                "<KeyRelease>",
                lambda e, w=widget: w.configure(
                    border_color=ORANGE if w.get("1.0", "end").strip() else BORDER
                )
            )

        widget.pack(fill="x")
        inputs[key] = (kind, widget)

    def open_edit_dialog(self, asset):
        asset_number = format_value(asset.get("asset_number"))
        original_status = asset.get("status") or ""
        inputs = {}

        dialog, status_badge, scroll, footer = self.create_dialog_shell(
            asset, "แก้ไขข้อมูล", "#FDEBDD", ORANGE
        )

        ctk.CTkLabel(
            scroll,
            text='เว้นว่าง = คงค่าเดิม   •   พิมพ์ "-" = ล้างค่า   •   ช่องที่แก้ไขจะมีขอบสีส้ม',
            font=(FONT, 11), text_color=MUTED
        ).pack(anchor="w", padx=14, pady=(4, 0))

        def on_status_change(value):
            if value == KEEP_CURRENT:
                status_badge.configure(
                    text=original_status or "ไม่ระบุสถานะ",
                    fg_color=status_color(original_status, fallback=MUTED)
                )
            else:
                status_badge.configure(
                    text=value, fg_color=status_color(value, fallback=MUTED)
                )

        for number, title, fields in ASSET_SECTIONS:
            body = self.dialog_section(scroll, number, title)

            for (key, label, kind, _span), row, col, cspan in layout_fields(fields):
                self.edit_field(
                    body, inputs, asset, key, label, kind, cspan, row, col,
                    status_callback=on_status_change if key == "status" else None
                )

        def collect_updates():
            updates = {}
            for key, (kind, widget) in inputs.items():
                if kind == "textbox":
                    raw = widget.get("1.0", "end").strip()
                else:
                    raw = widget.get().strip()

                if raw == "" or raw == KEEP_CURRENT:
                    continue

                updates[key] = None if raw == CLEAR_TOKEN else raw

            for protected in ("asset_number", "id", "created_at"):
                updates.pop(protected, None)
            return updates

        def save_updates():
            updates = collect_updates()

            if "asset_name" in updates and updates["asset_name"] is None:
                messagebox.showwarning(
                    "ข้อมูลไม่ถูกต้อง", "ชื่อครุภัณฑ์ห้ามเว้นว่าง", parent=dialog
                )
                return

            if updates.get("purchase_date"):
                try:
                    datetime.strptime(updates["purchase_date"], "%Y-%m-%d")
                except ValueError:
                    messagebox.showwarning(
                        "รูปแบบวันที่ไม่ถูกต้อง",
                        "กรุณาระบุวันที่ในรูปแบบ YYYY-MM-DD\nตัวอย่าง 2026-10-01",
                        parent=dialog
                    )
                    return

            for key in list(updates.keys()):
                old = asset.get(key)
                if (old if old != "" else None) == updates[key]:
                    del updates[key]

            if not updates:
                messagebox.showinfo(
                    "ไม่มีการเปลี่ยนแปลง",
                    "ยังไม่มีข้อมูลใหม่ที่แตกต่างจากข้อมูลเดิม",
                    parent=dialog
                )
                return

            changes = [
                f"{FIELD_LABELS.get(k, k)}: {format_value(asset.get(k))} → {format_value(v)}"
                for k, v in updates.items()
            ]

            if not messagebox.askyesno(
                "ยืนยันการแก้ไข",
                "ต้องการบันทึกการเปลี่ยนแปลงต่อไปนี้ใช่หรือไม่?\n\n" + "\n".join(changes),
                parent=dialog
            ):
                return

            try:
                query = supabase.table(ASSET_TABLE).update(updates)

                if asset.get("id") is not None:
                    query = query.eq("id", asset.get("id"))
                else:
                    query = query.eq("asset_number", asset.get("asset_number"))

                query.execute()

                log_action(
                    self.user.get("employee_id"),
                    "UPDATE_ASSET",
                    f"อัพเดทครุภัณฑ์ {asset_number} (" + ", ".join(changes) + ")"
                )

                messagebox.showinfo(
                    "สำเร็จ", "อัพเดทข้อมูลครุภัณฑ์เรียบร้อยแล้ว", parent=dialog
                )
                dialog.destroy()
                self.show_dashboard()
            except Exception as e:
                messagebox.showerror(
                    "เกิดข้อผิดพลาด",
                    f"ไม่สามารถอัพเดทข้อมูลได้\n{e}",
                    parent=dialog
                )

        ctk.CTkButton(
            footer, text="บันทึกการแก้ไข",
            width=160, height=42, corner_radius=9,
            fg_color=NAVY, hover_color=NAVY_DARK,
            font=(FONT, 13, "bold"), command=save_updates
        ).pack(side="right", padx=(8, 28), pady=16)

        # Enter ในช่องกรอก = บันทึกการแก้ไข | ช่องหมายเหตุใช้ Ctrl+Enter
        bind_enter([w for kind, w in inputs.values() if kind == "entry"], save_updates)
        for kind, w in inputs.values():
            if kind == "textbox":
                bind_ctrl_enter(w, save_updates)
        first_entry = next((w for kind, w in inputs.values() if kind == "entry"), None)
        if first_entry is not None:
            focus_later(dialog, first_entry)

        ctk.CTkButton(
            footer, text="ยกเลิก",
            width=110, height=42, corner_radius=9,
            fg_color="#E8ECF3", hover_color="#DCE2EC",
            text_color=TEXT, font=(FONT, 13),
            command=dialog.destroy
        ).pack(side="right", padx=8, pady=16)

    # =========================================================
    # TRANSFER PAGE
    # =========================================================
    def show_transfer(self):
        self.clear_content("บันทึกโอนย้าย")
        self.page_heading(
            "บันทึกการโอนย้ายครุภัณฑ์",
            "ระบบบันทึกการโอนออก (ตัดจำหน่าย/ย้ายออก) และการโอนเข้า (รับทรัพย์สินจากหน่วยงานอื่น)"
        )

        # ให้แน่ใจว่ามีรายการครุภัณฑ์ล่าสุดสำหรับค้นหา (ไม่เหลือรายการที่ถูกโอนออกไปแล้ว)
        self.ensure_assets()

        mode_var = ctk.StringVar(value="โอนออก")

        container = ctk.CTkFrame(self.content, fg_color="transparent")
        container.pack(fill="both", expand=True)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(1, weight=1)

        switcher_frame = ctk.CTkFrame(container, fg_color=WHITE, corner_radius=10, height=50)
        switcher_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        switcher_frame.pack_propagate(False)

        content_frame = ctk.CTkFrame(container, fg_color="transparent")
        content_frame.grid(row=1, column=0, sticky="nsew")
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_rowconfigure(0, weight=1)

        def update_tab_styles():
            mode = mode_var.get()
            if mode == "โอนออก":
                btn_out.configure(fg_color=NAVY, text_color=WHITE)
                btn_in.configure(fg_color="transparent", text_color=TEXT)
            else:
                btn_in.configure(fg_color=NAVY, text_color=WHITE)
                btn_out.configure(fg_color="transparent", text_color=TEXT)

        def render_transfer_mode():
            for widget in content_frame.winfo_children():
                widget.destroy()

            update_tab_styles()
            mode = mode_var.get()
            if mode == "โอนออก":
                self.render_transfer_out_ui(content_frame)
            else:
                self.render_transfer_in_ui(content_frame)

        btn_out = ctk.CTkButton(
            switcher_frame, text="โอนออก (ย้ายไปหน่วยงานอื่น)",
            font=(FONT, 13, "bold"), height=36, corner_radius=8,
            command=lambda: [mode_var.set("โอนออก"), render_transfer_mode()]
        )
        btn_out.pack(side="left", fill="x", expand=True, padx=12, pady=7)

        btn_in = ctk.CTkButton(
            switcher_frame, text="โอนเข้า (รับโอนจากหน่วยงานอื่น)",
            font=(FONT, 13, "bold"), height=36, corner_radius=8,
            command=lambda: [mode_var.set("โอนเข้า"), render_transfer_mode()]
        )
        btn_in.pack(side="right", fill="x", expand=True, padx=12, pady=7)

        render_transfer_mode()

    # UI สำหรับ "โอนออก"
    def render_transfer_out_ui(self, parent):
        parent.grid_columnconfigure(0, weight=3)
        parent.grid_columnconfigure(1, weight=2)
        parent.grid_rowconfigure(0, weight=1)

        selected_assets = []
        attached_file_ref = {"path": None, "new_name": None}

        # การ์ดซ้าย: ค้นหาและเลือกรายการ
        left_card = ctk.CTkFrame(parent, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=5)

        ctk.CTkLabel(left_card, text="1. ค้นหาและเลือกครุภัณฑ์ที่ต้องการโอนออก", font=(FONT, 14, "bold"), text_color=NAVY).pack(anchor="w", padx=20, pady=(18, 10))

        search_box = ctk.CTkFrame(left_card, fg_color="transparent")
        search_box.pack(fill="x", padx=20, pady=(0, 10))

        search_entry = ctk.CTkEntry(search_box, height=38, placeholder_text="พิมพ์ค้นหา เช่น เลขครุภัณฑ์, ชื่อ หรือยี่ห้อ", font=(FONT, 12), border_color=BORDER)
        search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        result_scroll = ctk.CTkScrollableFrame(left_card, fg_color="#F8FAFC", corner_radius=10, border_width=1, border_color=BORDER)
        result_scroll.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        selected_preview_frame = ctk.CTkScrollableFrame(left_card, fg_color=WHITE, corner_radius=8, border_width=1, border_color=BORDER, height=130)
        selected_preview_frame.pack(fill="x", padx=20, pady=(0, 15))

        def refresh_selected_preview():
            for w in selected_preview_frame.winfo_children():
                w.destroy()
            ctk.CTkLabel(selected_preview_frame, text=f"รายการที่เลือกโอนออก ({len(selected_assets)} รายการ):", font=(FONT, 12, "bold"), text_color=ORANGE).pack(anchor="w", padx=5, pady=5)
            if not selected_assets:
                ctk.CTkLabel(selected_preview_frame, text="ยังไม่ได้เลือกรายการครุภัณฑ์", font=(FONT, 11), text_color=MUTED).pack(anchor="w", padx=5, pady=2)
                return
            for idx, item in enumerate(selected_assets):
                row_f = ctk.CTkFrame(selected_preview_frame, fg_color="#F1F5F9", corner_radius=6, height=32)
                row_f.pack(fill="x", padx=2, pady=2)
                row_f.pack_propagate(False)
                txt = f"{idx+1}. [{format_value(item.get('asset_number'))}] {item.get('asset_name')}"
                ctk.CTkLabel(row_f, text=txt, font=(FONT, 11), text_color=TEXT, anchor="w").pack(side="left", padx=8)

                def remove_item(it=item):
                    if it in selected_assets:
                        selected_assets.remove(it)
                    refresh_selected_preview()

                ctk.CTkButton(row_f, text="✕", width=24, height=22, fg_color=RED, hover_color="#B33939", font=(FONT, 10, "bold"), command=remove_item).pack(side="right", padx=5)

        def toggle_select(item, checkbox_var):
            if checkbox_var.get() == 1:
                if item not in selected_assets:
                    selected_assets.append(item)
            else:
                if item in selected_assets:
                    selected_assets.remove(item)
            refresh_selected_preview()

        def do_search():
            kw = search_entry.get().strip().lower()
            for w in result_scroll.winfo_children():
                w.destroy()
            if not kw:
                ctk.CTkLabel(result_scroll, text="กรุณากรอกคำค้นหา", font=(FONT, 12), text_color=MUTED).pack(pady=20)
                return
            matched = [
                a for a in self.all_assets
                if kw in str(a.get("asset_number") or "").lower() or
                   kw in str(a.get("asset_name") or "").lower() or
                   kw in str(a.get("brand") or "").lower()
            ]
            if not matched:
                ctk.CTkLabel(result_scroll, text="ไม่พบรายการครุภัณฑ์ที่ตรงกัน", font=(FONT, 12), text_color=RED).pack(pady=20)
                return

            # จำกัดจำนวนที่แสดงเพื่อไม่ให้หน้าจอค้างเมื่อผลค้นหามีเยอะ
            LIMIT = 50
            ctk.CTkLabel(result_scroll, text=f"ผลการค้นหา {len(matched)} รายการ" + (f" (แสดง {LIMIT} รายการแรก กรุณาค้นหาให้เจาะจงขึ้น)" if len(matched) > LIMIT else "") + ":", font=(FONT, 12, "bold"), text_color=NAVY).pack(anchor="w", padx=10, pady=5)
            for item in matched[:LIMIT]:
                item_card = ctk.CTkFrame(result_scroll, fg_color=WHITE, corner_radius=8, border_width=1, border_color=BORDER)
                item_card.pack(fill="x", padx=5, pady=4)
                info_txt = f"[{format_value(item.get('asset_number'))}] {item.get('asset_name')} ({format_value(item.get('brand'))})"
                ctk.CTkLabel(item_card, text=info_txt, font=(FONT, 11), text_color=TEXT, anchor="w").pack(side="left", fill="x", expand=True, padx=10, pady=8)
                chk_var = ctk.IntVar(value=1 if item in selected_assets else 0)
                ctk.CTkCheckBox(item_card, text="เลือก", variable=chk_var, font=(FONT, 11), command=lambda it=item, v=chk_var: toggle_select(it, v), width=60).pack(side="right", padx=10)

        search_entry.bind("<Return>", lambda e: do_search())
        ctk.CTkButton(search_box, text="ค้นหา", width=80, height=38, fg_color=NAVY, font=(FONT, 12, "bold"), command=do_search).pack(side="right")
        ctk.CTkLabel(result_scroll, text="พิมพ์คำค้นหาแล้วกดปุ่มค้นหาเพื่อแสดงรายการ", font=(FONT, 12), text_color=MUTED).pack(pady=20)
        refresh_selected_preview()

        # การ์ดขวา
        right_card = ctk.CTkFrame(parent, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        right_card.grid(row=0, column=1, sticky="nsew", padx=(0, 0), pady=5)

        ctk.CTkLabel(right_card, text="2. ข้อมูลการโอนออกและเอกสารแนบ", font=(FONT, 14, "bold"), text_color=NAVY).pack(anchor="w", padx=20, pady=(18, 10))

        form_frame = ctk.CTkFrame(right_card, fg_color="transparent")
        form_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        ctk.CTkLabel(form_frame, text="หน่วยงานปลายทางที่รับโอน", font=(FONT, 12, "bold"), text_color=TEXT).pack(anchor="w", pady=(5, 2))
        dest_dept_entry = ctk.CTkEntry(form_frame, height=38, placeholder_text="ระบุชื่อหน่วยงานปลายทาง", font=(FONT, 12), border_color=BORDER)
        dest_dept_entry.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(form_frame, text="วันที่ทำการโอน (YYYY-MM-DD)", font=(FONT, 12, "bold"), text_color=TEXT).pack(anchor="w", pady=(5, 2))
        transfer_date_entry = ctk.CTkEntry(form_frame, height=38, font=(FONT, 12), border_color=BORDER)
        transfer_date_entry.pack(fill="x", pady=(0, 10))
        transfer_date_entry.insert(0, datetime.now().strftime("%Y-%m-%d"))

        ctk.CTkLabel(form_frame, text="เอกสารแนบ (เฉพาะไฟล์ PDF เท่านั้น)", font=(FONT, 12, "bold"), text_color=TEXT).pack(anchor="w", pady=(5, 2))
        file_status_lbl = ctk.CTkLabel(form_frame, text="ยังไม่ได้เลือกไฟล์ PDF แนบ", font=(FONT, 11), text_color=MUTED, anchor="w")
        file_status_lbl.pack(anchor="w", pady=(2, 5))

        def browse_and_rename_file():
            file_path = filedialog.askopenfilename(
                title="เลือกไฟล์เอกสารแนบ (PDF)",
                filetypes=[("PDF Files", "*.pdf")]
            )
            if file_path:
                ext = os.path.splitext(file_path)[1]
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                new_filename = f"TRANSFER_OUT_{timestamp_str}{ext}"
                attached_file_ref["path"] = file_path
                attached_file_ref["new_name"] = new_filename
                file_status_lbl.configure(text=f"ไฟล์แนบ: {new_filename}", text_color=GREEN)

        ctk.CTkButton(form_frame, text="เลือกไฟล์ PDF แนบ", height=35, fg_color="#E8ECF3", hover_color="#DCE2EC", text_color=TEXT, font=(FONT, 12, "bold"), command=browse_and_rename_file).pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(form_frame, text="หมายเหตุ / สาเหตุการโอนออก", font=(FONT, 12, "bold"), text_color=TEXT).pack(anchor="w", pady=(5, 2))
        note_box = ctk.CTkTextbox(form_frame, height=80, font=(FONT, 12), border_color=BORDER, border_width=1)
        note_box.pack(fill="x", pady=(0, 15))

        def execute_transfer_out():
            if not selected_assets:
                messagebox.showwarning("ยังไม่ได้เลือกครุภัณฑ์", "กรุณาเลือกรายการครุภัณฑ์ที่ต้องการโอนออกอย่างน้อย 1 รายการ", parent=self)
                return
            dest_dept = dest_dept_entry.get().strip()
            t_date = transfer_date_entry.get().strip()
            notes = note_box.get("1.0", "end").strip()

            if not dest_dept:
                messagebox.showwarning("ข้อมูลไม่ครบถ้วน", "กรุณาระบุหน่วยงานปลายทาง", parent=self)
                return
            if not attached_file_ref["path"]:
                messagebox.showwarning("ยังไม่ได้แนบเอกสาร", "ระบบบังคับให้อัปโหลดเอกสารแนบประเภท PDF เท่านั้น", parent=self)
                return

            try:
                datetime.strptime(t_date, "%Y-%m-%d")
            except ValueError:
                messagebox.showwarning("รูปแบบวันที่ไม่ถูกต้อง", "กรุณากรอกวันที่ในรูปแบบ YYYY-MM-DD", parent=self)
                return

            if not messagebox.askyesno("ยืนยันการโอนออก", f"ต้องการโอนออกจำนวน {len(selected_assets)} รายการ ไปยัง '{dest_dept}' ใช่หรือไม่?\n\nรายการที่โอนออกจะถูกตัดออกจากระบบ", parent=self, default="no"):
                return

            try:
                final_filename = attached_file_ref["new_name"]

                success = upload_pdf_to_supabase(attached_file_ref["path"], final_filename)
                if not success:
                    messagebox.showerror("ข้อผิดพลาด", "ไม่สามารถอัปโหลดไฟล์ PDF ขึ้นสู่ Supabase Storage ได้", parent=self)
                    return

                asset_summary_text = f"โอนออก {len(selected_assets)} รายการ: " + ", ".join([f"[{format_value(t.get('asset_number'))}] {t.get('asset_name')}" for t in selected_assets])

                supabase.table("transfer_logs").insert({
                    "transfer_type": "โอนออก",
                    "employee_id": self.user.get("employee_id"),
                    "dest_department": dest_dept,
                    "transfer_date": build_transfer_timestamp(t_date),
                    "assets_detail": asset_summary_text,
                    "file_name": final_filename,
                    "notes": notes
                }).execute()

                for target in selected_assets:
                    q = supabase.table(ASSET_TABLE).delete()
                    if target.get("id") is not None:
                        q = q.eq("id", target.get("id"))
                    else:
                        q = q.eq("asset_number", target.get("asset_number"))
                    q.execute()

                self.assets_stale = True

                log_action(
                    self.user.get("employee_id"),
                    "TRANSFER_OUT_MULTI",
                    f"โอนออกครุภัณฑ์จำนวน {len(selected_assets)} รายการ ไปยัง: {dest_dept} | วันที่โอน: {t_date}"
                )

                messagebox.showinfo("สำเร็จ", "บันทึกการโอนออกและตัดรายการออกจากระบบเรียบร้อยแล้ว", parent=self)
                self.show_transfer()
            except Exception as e:
                messagebox.showerror("เกิดข้อผิดพลาด", f"ไม่สามารถดำเนินการโอนออกได้\n{e}", parent=self)

        ctk.CTkButton(right_card, text="ยืนยันการโอนออก", height=42, fg_color=RED, hover_color="#B33939", font=(FONT, 13, "bold"), command=execute_transfer_out).pack(fill="x", padx=20, pady=15)

        # Enter ในช่องกรอก = ยืนยันการโอนออก (มีหน้าต่างยืนยันอีกชั้น) | หมายเหตุใช้ Ctrl+Enter
        bind_enter([dest_dept_entry, transfer_date_entry], execute_transfer_out)
        bind_ctrl_enter(note_box, execute_transfer_out)

    # UI สำหรับ "โอนเข้า"
    def render_transfer_in_ui(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        in_fields = {}
        attached_file_ref = {"path": None, "new_name": None}

        grid = ctk.CTkFrame(scroll, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure((0, 1), weight=1)

        def create_in_card(row, column, number, title, fields):
            card = ctk.CTkFrame(grid, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
            card.grid(row=row, column=column, sticky="nsew", padx=7, pady=7)

            header = ctk.CTkFrame(card, fg_color="transparent")
            header.pack(fill="x", padx=18, pady=(18, 12))

            ctk.CTkLabel(header, text=number, font=(FONT, 13, "bold"), text_color=ORANGE).pack(side="left", padx=(0, 10))
            ctk.CTkLabel(header, text=title, font=(FONT, 15, "bold"), text_color=NAVY).pack(side="left")

            for key, label, field_type, options in fields:
                field_box = ctk.CTkFrame(card, fg_color="transparent")
                field_box.pack(fill="x", padx=18, pady=(3, 10))

                ctk.CTkLabel(field_box, text=label, font=(FONT, 12, "bold"), text_color=TEXT).pack(anchor="w", pady=(0, 5))

                if field_type == "entry":
                    widget = ctk.CTkEntry(field_box, height=38, placeholder_text=f"กรอก{label}", font=(FONT, 12), border_color=BORDER)
                    if key == "purchase_date":
                        widget.insert(0, datetime.now().strftime("%Y-%m-%d"))
                elif field_type == "combo":
                    widget = NavyComboBox(
                        field_box,
                        values=options,
                        height=38,
                        font=(FONT, 12),
                        dropdown_font=(FONT, 12),
                        state="readonly",
                        **COMBO_STYLE
                    )
                    widget.set(options[0])
                elif field_type == "textbox":
                    widget = ctk.CTkTextbox(field_box, height=85, font=(FONT, 12), border_color=BORDER, border_width=1)
                elif field_type == "file":
                    file_box = ctk.CTkFrame(field_box, fg_color="transparent")
                    file_box.pack(fill="x")
                    file_status_lbl = ctk.CTkLabel(file_box, text="ยังไม่ได้เลือกไฟล์ PDF แนบ", font=(FONT, 11), text_color=MUTED, anchor="w")
                    file_status_lbl.pack(anchor="w", pady=(0, 5))

                    def browse_pdf(lbl=file_status_lbl):
                        file_path = filedialog.askopenfilename(title="เลือกไฟล์เอกสารแนบ (PDF)", filetypes=[("PDF Files", "*.pdf")])
                        if file_path:
                            ext = os.path.splitext(file_path)[1]
                            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                            new_filename = f"TRANSFER_IN_{timestamp_str}{ext}"
                            attached_file_ref["path"] = file_path
                            attached_file_ref["new_name"] = new_filename
                            lbl.configure(text=f"ไฟล์แนบ: {new_filename}", text_color=GREEN)

                    ctk.CTkButton(file_box, text="เลือกไฟล์ PDF แนบ", height=35, fg_color="#E8ECF3", hover_color="#DCE2EC", text_color=TEXT, font=(FONT, 12, "bold"), command=browse_pdf).pack(fill="x")
                    continue

                widget.pack(fill="x")
                in_fields[key] = widget

        create_in_card(0, 0, "01", "ข้อมูลพื้นฐานครุภัณฑ์รับโอน", [
            ("asset_number", "เลขครุภัณฑ์", "entry", None),
            ("asset_name", "ชื่อครุภัณฑ์", "entry", None),
            ("brand", "ยี่ห้อ", "entry", None),
            ("category", "ประเภท", "entry", None)
        ])

        create_in_card(0, 1, "02", "หน่วยงานและการโอนย้าย", [
            ("department", "หน่วยงาน", "entry", None),
            ("source_department", "หน่วยงานต้นสังกัดเดิม (ผู้โอนให้)", "entry", None),
            ("purchase_date", "วันที่รับโอน (YYYY-MM-DD)", "entry", None),
            ("responsible_work", "หน่วยงานที่รับผิดชอบดูแล", "entry", None),
            ("holding_work", "หน่วยงานที่ถือครอง", "entry", None)
        ])

        create_in_card(1, 0, "03", "สถานที่ตั้ง", [
            ("location", "สถานที่ตั้ง", "combo", ["เลือกสถานที่ตั้ง", "อาคารสำนักงาน", "อาคารเรียน", "อาคารวิจัย"]),
            ("floor", "ชั้น", "combo", ["เลือกชั้น", "ชั้น 1", "ชั้น 2", "ชั้น 3", "ชั้น 4", "ชั้น 5", "ชั้น 6"]),
            ("zone", "โซน", "combo", ["เลือกโซน", "Zone A", "Zone B", "Zone C"]),
            ("room", "ห้อง", "entry", None)
        ])

        create_in_card(1, 1, "04", "เอกสารแนบและหมายเหตุ", [
            ("transfer_file", "เอกสารแนบ (เฉพาะไฟล์ PDF เท่านั้น)", "file", None),
            ("notes", "หมายเหตุ", "textbox", None)
        ])

        button_area = ctk.CTkFrame(scroll, fg_color="transparent")
        button_area.pack(fill="x", pady=20)

        def execute_transfer_in():
            data = {}
            for k, widget in in_fields.items():
                val = widget.get("1.0", "end").strip() if isinstance(widget, ctk.CTkTextbox) else widget.get().strip()
                if val.startswith("เลือก"):
                    val = ""
                data[k] = val if val else None

            if not data.get("asset_number") or not data.get("asset_name") or not data.get("department") or not data.get("source_department"):
                messagebox.showwarning("ข้อมูลไม่ครบถ้วน", "กรุณากรอกเลขครุภัณฑ์ ชื่อครุภัณฑ์ หน่วยงาน และหน่วยงานต้นสังกัดเดิมให้ครบถ้วน", parent=self)
                return

            # เลขครุภัณฑ์ในฐานข้อมูลเป็นชนิด numeric
            asset_no = str(data["asset_number"]).replace(",", "").replace(" ", "")
            if not asset_no.isdigit():
                messagebox.showwarning("ข้อมูลไม่ถูกต้อง", "เลขครุภัณฑ์ต้องเป็นตัวเลขเท่านั้น", parent=self)
                return
            data["asset_number"] = int(asset_no)

            if data.get("purchase_date"):
                try:
                    datetime.strptime(data["purchase_date"], "%Y-%m-%d")
                except ValueError:
                    messagebox.showwarning("รูปแบบวันที่ไม่ถูกต้อง", "กรุณากรอกวันที่ในรูปแบบ YYYY-MM-DD", parent=self)
                    return

            if not attached_file_ref["path"]:
                messagebox.showwarning("ยังไม่ได้แนบเอกสาร", "ระบบบังคับให้อัปโหลดเอกสารแนบประเภท PDF เท่านั้น", parent=self)
                return

            try:
                # 1) อัปโหลดเอกสารก่อน (ถ้าล้มเหลวจะยังไม่เพิ่มครุภัณฑ์เข้าระบบ)
                final_filename = attached_file_ref["new_name"]
                success = upload_pdf_to_supabase(attached_file_ref["path"], final_filename)
                if not success:
                    messagebox.showerror("ข้อผิดพลาด", "ไม่สามารถอัปโหลดไฟล์ PDF ขึ้นสู่ Supabase Storage ได้", parent=self)
                    return

                # 2) เพิ่มครุภัณฑ์ (source_department ไม่ใช่คอลัมน์ของ asset_list จึงต้องแยกออก)
                source_department = data.pop("source_department", None)
                data["status"] = "พร้อมใช้งาน"
                insert_asset(data)

                # 3) บันทึกประวัติการโอนเข้า
                supabase.table("transfer_logs").insert({
                    "transfer_type": "โอนเข้า",
                    "employee_id": self.user.get("employee_id"),
                    "dest_department": source_department or "-",
                    "transfer_date": build_transfer_timestamp(data.get("purchase_date") or datetime.now().strftime("%Y-%m-%d")),
                    "assets_detail": f"[{data['asset_number']}] {data['asset_name']}",
                    "file_name": final_filename,
                    "notes": data.get("notes") or "-"
                }).execute()

                self.assets_stale = True

                log_action(
                    self.user.get("employee_id"),
                    "TRANSFER_IN",
                    f"รับโอนเข้าครุภัณฑ์ {data['asset_number']} - {data['asset_name']}"
                )

                messagebox.showinfo("สำเร็จ", "บันทึกรับโอนเข้าครุภัณฑ์เรียบร้อยแล้ว", parent=self)
                self.show_transfer()
            except Exception as e:
                messagebox.showerror("เกิดข้อผิดพลาด", f"ไม่สามารถบันทึกรับโอนเข้าได้\n{e}", parent=self)

        ctk.CTkButton(
            button_area,
            text="ยืนยันการรับโอนเข้า (เพิ่มลงระบบ)",
            height=42,
            fg_color=GREEN,
            hover_color="#1b6e47",
            font=(FONT, 13, "bold"),
            command=execute_transfer_in
        ).pack(fill="x", padx=5)

        # Enter ในช่องกรอก = บันทึกรับโอนเข้า | หมายเหตุใช้ Ctrl+Enter
        bind_enter([w for w in in_fields.values() if isinstance(w, ctk.CTkEntry)], execute_transfer_in)
        for w in in_fields.values():
            if isinstance(w, ctk.CTkTextbox):
                bind_ctrl_enter(w, execute_transfer_in)
        if "asset_number" in in_fields:
            focus_later(self, in_fields["asset_number"])

    # ---------------------------------------------------------
    # หน้าจอ "ประวัติการโอนย้าย"
    # ---------------------------------------------------------
    def show_transfer_history(self):
        self.clear_content("ประวัติการโอนย้าย")
        self.page_heading(
            "ประวัติการโอนย้ายครุภัณฑ์ทั้งหมด",
            "แสดงรายการประวัติการโอนย้ายออกและการรับโอนเข้าครุภัณฑ์ภายในหน่วยงาน"
        )

        try:
            raw_transfers = fetch_transfer_logs() or []
            all_transfers = sorted(
                raw_transfers,
                key=lambda x: (format_transfer_datetime(x), str(x.get("id", ""))),
                reverse=True
            )
        except Exception as e:
            all_transfers = []
            messagebox.showerror("Database Error", f"ไม่สามารถโหลดประวัติการโอนย้ายได้\n{e}", parent=self)

        HISTORY_PAGE_SIZE = 25
        self.transfer_history_page = 0

        toolbar = ctk.CTkFrame(self.content, fg_color=WHITE, corner_radius=10, height=55)
        toolbar.pack(fill="x", pady=(0, 10))
        toolbar.pack_propagate(False)

        search_entry = ctk.CTkEntry(
            toolbar, height=38, font=(FONT, 12), border_color=BORDER,
            placeholder_text="ค้นหาเลขครุภัณฑ์, ชื่อ, หน่วยงาน หรือผู้ทำรายการ",
        )
        search_entry.pack(side="left", fill="x", expand=True, padx=15, pady=8)

        filter_combo = NavyComboBox(
            toolbar,
            values=["ทั้งหมด", "โอนออก", "โอนเข้า"],
            height=38,
            width=140,
            font=(FONT, 12),
            dropdown_font=(FONT, 12),
            state="readonly",
            **COMBO_STYLE
        )
        filter_combo.set("ทั้งหมด")
        filter_combo.pack(side="left", padx=(0, 10), pady=8)

        def clear_filter():
            search_entry.delete(0, "end")
            filter_combo.set("ทั้งหมด")
            self.transfer_history_page = 0
            render_rows()

        ctk.CTkButton(
            toolbar, text="ล้างค่า", width=80, height=38,
            fg_color="#E8ECF3", hover_color="#DCE2EC", text_color=TEXT,
            font=(FONT, 12, "bold"), command=clear_filter
        ).pack(side="left", padx=(0, 15), pady=8)

        table_card = ctk.CTkFrame(self.content, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        table_card.pack(fill="both", expand=True)

        columns = [
            ("ลำดับ", 5, 60),
            ("ประเภท", 10, 90),
            ("วันที่โอน", 12, 110),
            ("หน่วยงานปลายทาง/ต้นทาง", 18, 160),
            ("รายละเอียดครุภัณฑ์", 35, 300),
            ("เอกสารแนบ", 15, 140),
            ("ผู้ทำรายการ", 12, 100),
        ]

        header = ctk.CTkFrame(
            table_card, fg_color="#E8ECF5", corner_radius=8, height=40
        )
        header.pack(fill="x", padx=(12, 12 + SCROLLBAR_SPACE), pady=(12, 0))
        header.pack_propagate(False)
        header.grid_propagate(False)
        header.grid_rowconfigure(0, weight=1)
        configure_table_columns(header, columns, "transfer_cols")

        for col_idx, (title, _, _) in enumerate(columns):
            ctk.CTkLabel(
                header, text=title, font=(FONT, 12, "bold"), text_color=NAVY, anchor="center"
            ).grid(row=0, column=col_idx, sticky="nsew", padx=4)

        pager_frame = ctk.CTkFrame(table_card, fg_color="transparent", height=44)
        pager_frame.pack(side="bottom", fill="x", padx=15, pady=6)

        body = ctk.CTkScrollableFrame(table_card, fg_color=WHITE)
        body.pack(fill="both", expand=True, padx=12, pady=8)
        configure_table_columns(body, columns, "transfer_cols")

        def preview_pdf(filename):
            if not filename or filename == "-":
                messagebox.showwarning("ไม่พบเอกสาร", "รายการนี้ไม่มีไฟล์เอกสารแนบ", parent=self)
                return
            try:
                res = supabase.storage.from_("transfer-documents").get_public_url(filename)
                public_url = res if isinstance(res, str) else res.get("publicUrl")
                if public_url:
                    import webbrowser
                    webbrowser.open(public_url)
                else:
                    messagebox.showerror("ข้อผิดพลาด", "ไม่สามารถสร้างลิงก์สำหรับเปิดเอกสารได้", parent=self)
            except Exception as e:
                messagebox.showerror("ข้อผิดพลาด", f"ไม่สามารถเปิดไฟล์เอกสารจากระบบคลาวด์ได้\n{e}", parent=self)

        def render_rows(*args):
            for w in body.winfo_children():
                w.destroy()
            for w in pager_frame.winfo_children():
                w.destroy()

            kw = search_entry.get().strip().lower()
            selected_type = filter_combo.get()

            filtered = []
            for item in all_transfers:
                t_type = item.get("transfer_type", "")
                if selected_type != "ทั้งหมด" and t_type != selected_type:
                    continue

                search_blob = " ".join([
                    str(item.get("transfer_type") or ""),
                    format_transfer_datetime(item),
                    str(item.get("dest_department") or ""),
                    str(item.get("assets_detail") or ""),
                    str(item.get("file_name") or ""),
                    str(item.get("employee_id") or "")
                ]).lower()

                if kw and kw not in search_blob:
                    continue
                filtered.append(item)

            total = len(filtered)
            pages = max(1, -(-total // HISTORY_PAGE_SIZE))
            if self.transfer_history_page >= pages:
                self.transfer_history_page = max(0, pages - 1)

            start = self.transfer_history_page * HISTORY_PAGE_SIZE
            end = min(start + HISTORY_PAGE_SIZE, total)
            page_logs = filtered[start:end]

            if total > 0:
                ctk.CTkLabel(
                    pager_frame,
                    text=f"แสดง {start + 1}–{end} จาก {total} รายการ",
                    font=(FONT, 12), text_color=MUTED
                ).pack(side="left", padx=6)

                def go_page(p):
                    self.transfer_history_page = p
                    render_rows()

                ctk.CTkButton(
                    pager_frame, text="ถัดไป", width=90, height=32, corner_radius=8,
                    fg_color="#E8ECF5", hover_color="#D6DEEE", text_color=NAVY, font=(FONT, 12),
                    state="normal" if self.transfer_history_page < pages - 1 else "disabled",
                    command=lambda: go_page(self.transfer_history_page + 1)
                ).pack(side="right", padx=(6, 0))

                ctk.CTkLabel(
                    pager_frame, text=f"หน้า {self.transfer_history_page + 1} / {pages}",
                    font=(FONT, 12, "bold"), text_color=NAVY
                ).pack(side="right", padx=10)

                ctk.CTkButton(
                    pager_frame, text="ก่อนหน้า", width=90, height=32, corner_radius=8,
                    fg_color="#E8ECF5", hover_color="#D6DEEE", text_color=NAVY, font=(FONT, 12),
                    state="normal" if self.transfer_history_page > 0 else "disabled",
                    command=lambda: go_page(self.transfer_history_page - 1)
                ).pack(side="right", padx=(6, 0))

            if not page_logs:
                ctk.CTkLabel(body, text="ไม่พบประวัติการโอนย้ายที่ตรงกับเงื่อนไข", font=(FONT, 13), text_color=MUTED).grid(row=0, column=0, columnspan=len(columns), pady=40)
                return

            for row_idx, item in enumerate(page_logs):
                row_bg = "#FFFFFF" if row_idx % 2 == 0 else "#F7F9FC"
                t_type = item.get("transfer_type", "-")
                type_color = RED if t_type == "โอนออก" else GREEN

                raw_detail = str(item.get("assets_detail") or "-")
                formatted_detail = raw_detail
                if "โอนออก" in raw_detail and ":" in raw_detail:
                    parts = raw_detail.split(":", 1)
                    header_txt = parts[0].strip()
                    items_txt = parts[1].strip()
                    item_list = [it.strip() for it in items_txt.split(",") if it.strip()]
                    if len(item_list) > 1:
                        formatted_detail = f"{header_txt}:\n" + "\n".join([f"• {it}" for it in item_list])

                seq_number = start + row_idx + 1
                values = [
                    str(seq_number),
                    t_type,
                    format_transfer_date(item),
                    item.get("dest_department", "-"),
                    formatted_detail,
                    item.get("file_name", "-"),
                    item.get("employee_id", "-"),
                ]

                for col_idx, value in enumerate(values):
                    if col_idx == 5:
                        file_name_str = str(value or "-")
                        if file_name_str != "-":
                            ctk.CTkButton(
                                body, text=file_name_str, font=(FONT, 11, "underline"),
                                text_color="#1D4ED8", fg_color=row_bg, hover_color="#E2E8F0",
                                anchor="center", height=32, corner_radius=4,
                                command=lambda fn=file_name_str: preview_pdf(fn)
                            ).grid(row=row_idx, column=col_idx, sticky="nsew", padx=4, pady=2)
                        else:
                            ctk.CTkLabel(
                                body, text="-", font=(FONT, 12), text_color=MUTED,
                                anchor="center", fg_color=row_bg, corner_radius=4, height=36
                            ).grid(row=row_idx, column=col_idx, sticky="nsew", padx=4, pady=2)
                    else:
                        txt_color = type_color if col_idx == 1 else TEXT
                        is_seq = (col_idx == 0)
                        ctk.CTkLabel(
                            body,
                            text=format_value(value),
                            font=(FONT, 12, "bold" if col_idx == 1 or is_seq else "normal"),
                            text_color=MUTED if is_seq else txt_color,
                            anchor="center" if col_idx in (0, 1, 2, 5, 6) else "w",
                            justify="left",
                            fg_color=row_bg,
                            corner_radius=4,
                            height=36,
                            wraplength=280 if col_idx == 4 else 0
                        ).grid(row=row_idx, column=col_idx, sticky="nsew", padx=4, pady=2)

        search_entry.bind("<KeyRelease>", lambda e: [setattr(self, 'transfer_history_page', 0), render_rows()])
        filter_combo.configure(command=lambda _: [setattr(self, 'transfer_history_page', 0), render_rows()])

        render_rows()

    # LOG HISTORY
    def show_logs(self):
        self.clear_content("ประวัติการทำรายการ")
        self.page_heading(
            "ประวัติการทำรายการ",
            "ตรวจสอบกิจกรรมการใช้งานระบบ"
        )

        try:
            all_logs = fetch_logs() or []
        except Exception as e:
            all_logs = []
            messagebox.showerror(
                "Database Error",
                f"ไม่สามารถโหลดประวัติได้\n{e}",
                parent=self
            )

        LOG_PAGE_SIZE = 30
        self.log_page = 0

        toolbar = ctk.CTkFrame(self.content, fg_color=WHITE, corner_radius=10, height=55)
        toolbar.pack(fill="x", pady=(0, 10))
        toolbar.pack_propagate(False)

        search_entry = ctk.CTkEntry(
            toolbar, height=38, font=(FONT, 12), border_color=BORDER,
            placeholder_text="ค้นหารหัสพนักงาน, กิจกรรม หรือรายละเอียด",
        )
        search_entry.pack(side="left", fill="x", expand=True, padx=15, pady=8)

        filter_combo = NavyComboBox(
            toolbar,
            values=list(LOG_FILTERS.keys()),
            height=38,
            width=160,
            font=(FONT, 12),
            dropdown_font=(FONT, 12),
            state="readonly",
            **COMBO_STYLE
        )
        filter_combo.set("ทั้งหมด")
        filter_combo.pack(side="left", padx=(0, 10), pady=8)

        def clear_filter():
            search_entry.delete(0, "end")
            filter_combo.set("ทั้งหมด")
            self.log_page = 0
            render_rows()

        ctk.CTkButton(
            toolbar, text="ล้างค่า", width=80, height=38,
            fg_color="#E8ECF3", hover_color="#DCE2EC", text_color=TEXT,
            font=(FONT, 12, "bold"), command=clear_filter
        ).pack(side="left", padx=(0, 15), pady=8)

        table_card = ctk.CTkFrame(self.content, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        table_card.pack(fill="both", expand=True)

        columns = [
            ("ลำดับ",        5,  60),
            ("วันที่และเวลา", 18, 160),
            ("รหัสพนักงาน",  12, 120),
            ("กิจกรรม",      14, 130),
            ("รายละเอียด",    40, 300),
        ]

        header = ctk.CTkFrame(
            table_card, fg_color="#EDF1F7", corner_radius=8, height=40
        )
        header.pack(fill="x", padx=(12, 12 + SCROLLBAR_SPACE), pady=(12, 0))
        header.pack_propagate(False)
        header.grid_propagate(False)
        header.grid_rowconfigure(0, weight=1)
        configure_table_columns(header, columns, "log_cols")

        for col_idx, (title, _, _) in enumerate(columns):
            ctk.CTkLabel(
                header,
                text=title,
                font=(FONT, 12, "bold"),
                text_color=NAVY,
                anchor="center"
            ).grid(row=0, column=col_idx, sticky="nsew", padx=4)

        pager_frame = ctk.CTkFrame(table_card, fg_color="transparent", height=44)
        pager_frame.pack(side="bottom", fill="x", padx=15, pady=6)

        body = ctk.CTkScrollableFrame(table_card, fg_color=WHITE)
        body.pack(fill="both", expand=True, padx=12, pady=8)
        configure_table_columns(body, columns, "log_cols")

        def render_rows(*args):
            for w in body.winfo_children():
                w.destroy()
            for w in pager_frame.winfo_children():
                w.destroy()

            kw = search_entry.get().strip().lower()
            action_prefixes = LOG_FILTERS.get(filter_combo.get())

            filtered = []
            for log in all_logs:
                action_code = str(log.get("action") or "")

                if action_prefixes and not action_code.startswith(action_prefixes):
                    continue

                search_blob = " ".join([
                    str(log.get("created_at") or ""),
                    str(log.get("employee_id") or ""),
                    action_code,
                    str(log.get("details") or "")
                ]).lower()

                if kw and kw not in search_blob:
                    continue
                filtered.append(log)

            total = len(filtered)
            pages = max(1, -(-total // LOG_PAGE_SIZE))
            if self.log_page >= pages:
                self.log_page = max(0, pages - 1)

            start = self.log_page * LOG_PAGE_SIZE
            end = min(start + LOG_PAGE_SIZE, total)
            page_logs = filtered[start:end]

            if total > 0:
                ctk.CTkLabel(
                    pager_frame,
                    text=f"แสดง {start + 1}–{end} จาก {total} รายการ",
                    font=(FONT, 12), text_color=MUTED
                ).pack(side="left", padx=6)

                def go_page(p):
                    self.log_page = p
                    render_rows()

                ctk.CTkButton(
                    pager_frame, text="ถัดไป", width=90, height=32, corner_radius=8,
                    fg_color="#E8ECF5", hover_color="#D6DEEE", text_color=NAVY, font=(FONT, 12),
                    state="normal" if self.log_page < pages - 1 else "disabled",
                    command=lambda: go_page(self.log_page + 1)
                ).pack(side="right", padx=(6, 0))

                ctk.CTkLabel(
                    pager_frame, text=f"หน้า {self.log_page + 1} / {pages}",
                    font=(FONT, 12, "bold"), text_color=NAVY
                ).pack(side="right", padx=10)

                ctk.CTkButton(
                    pager_frame, text="ก่อนหน้า", width=90, height=32, corner_radius=8,
                    fg_color="#E8ECF5", hover_color="#D6DEEE", text_color=NAVY, font=(FONT, 12),
                    state="normal" if self.log_page > 0 else "disabled",
                    command=lambda: go_page(self.log_page - 1)
                ).pack(side="right", padx=(6, 0))

            if not page_logs:
                ctk.CTkLabel(
                    body,
                    text="ยังไม่พบประวัติการทำรายการที่ตรงกับเงื่อนไข",
                    font=(FONT, 13),
                    text_color=MUTED
                ).grid(row=0, column=0, columnspan=len(columns), pady=40)
                return

            for row_idx, log in enumerate(page_logs):
                row_bg = "#FFFFFF" if row_idx % 2 == 0 else "#F7F9FC"
                created_at = format_datetime(log.get("created_at"))
                seq_number = start + row_idx + 1

                values = [
                    str(seq_number),
                    created_at,
                    log.get("employee_id"),
                    log.get("action"),
                    log.get("details"),
                ]

                for col_idx, value in enumerate(values):
                    is_seq = (col_idx == 0)
                    ctk.CTkLabel(
                        body,
                        text=str(value or "-"),
                        font=(FONT, 12, "bold" if is_seq else "normal"),
                        text_color=MUTED if is_seq else TEXT,
                        anchor="center" if col_idx in (0, 1, 2) else "w",
                        justify="left",
                        fg_color=row_bg,
                        corner_radius=4,
                        height=34,
                        wraplength=520 if col_idx == 4 else 0
                    ).grid(row=row_idx, column=col_idx, sticky="nsew", padx=4, pady=2)

        search_entry.bind("<KeyRelease>", lambda e: [setattr(self, 'log_page', 0), render_rows()])
        filter_combo.configure(command=lambda _: [setattr(self, 'log_page', 0), render_rows()])

        render_rows()

    def empty_state(self, title, description):
        frame = ctk.CTkFrame(self.content, fg_color=WHITE, corner_radius=12)
        frame.pack(fill="both", expand=True)

        ctk.CTkLabel(
            frame,
            text=title,
            font=(FONT, 19, "bold"),
            text_color=NAVY
        ).pack(pady=(100, 10))

        ctk.CTkLabel(
            frame,
            text=description,
            font=(FONT, 13),
            text_color=MUTED,
            wraplength=600
        ).pack()

    def logout(self):
        confirm = messagebox.askyesno(
            "ออกจากระบบ",
            "คุณต้องการออกจากระบบใช่หรือไม่?"
        )
        if confirm:
            try:
                log_action(
                    self.user.get("employee_id"),
                    "LOGOUT",
                    "ออกจากระบบ CRA Asset Management"
                )
            except Exception:
                pass

            self.destroy()
            login = LoginWindow()
            login.mainloop()


# =========================================================
# APPLICATION ENTRY
# =========================================================

def run_app():
    app = LoginWindow()
    app.mainloop()


if __name__ == "__main__":
    run_app()