from supabase import create_client, Client

# ==========================================================
# SUPABASE CONFIGURATION
# ==========================================================

SUPABASE_URL = "https://ooottypjctuuqzwkuqvo.supabase.co"
SUPABASE_KEY = "sb_publishable_tevCVLzVOxnh8sF3FKtqQA_sACizNGV"

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


# ==========================================================
# FETCH ASSETS
# ==========================================================

def fetch_assets():
    """ดึงข้อมูลครุภัณฑ์ทั้งหมด"""
    response = (
        supabase
        .table("asset_list")
        .select("*")
        .order("asset_number")
        .execute()
    )
    return response.data or []


# ==========================================================
# LOGIN
# ==========================================================

def login_user(employee_id, password):
    """ตรวจสอบบัญชีผู้ใช้งาน"""
    response = (
        supabase
        .table("users")
        .select("*")
        .eq("employee_id", employee_id)
        .eq("password", password)
        .limit(1)
        .execute()
    )

    if response.data:
        return response.data[0]

    return None


# ==========================================================
# INSERT ASSET
# ==========================================================

def insert_asset(data):
    """บันทึกข้อมูลครุภัณฑ์"""
    try:
        response = (
            supabase
            .table("asset_list")
            .insert(data)
            .execute()
        )
        return response.data
    except Exception as e:
        raise Exception(f"ไม่สามารถบันทึกครุภัณฑ์ได้: {e}") from e


# ==========================================================
# AUDIT LOG
# ==========================================================

def log_action(employee_id, action, details):
    """บันทึกประวัติการใช้งาน"""
    try:
        data = {
            "employee_id": employee_id,
            "action": action,
            "details": details
        }
        supabase.table("system_logs").insert(data).execute()
        return True
    except Exception as e:
        print(f"Log Error: {e}")
        return False


# ==========================================================
# FETCH LOGS
# ==========================================================

def fetch_logs(limit=100):
    """ดึงประวัติการใช้งาน"""
    response = (
        supabase
        .table("system_logs")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return response.data or []

# ==========================================================
# TRANSFER LOGS
# ==========================================================

def fetch_transfer_logs(limit=100):
    """ดึงประวัติการโอนย้ายครุภัณฑ์"""
    try:
        response = (
            supabase
            .table("transfer_logs")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data or []
    except Exception as e:
        print(f"Fetch Transfer Logs Error: {e}")
        return []

def insert_transfer_log(data):
    """บันทึกประวัติการโอนย้ายครุภัณฑ์"""
    try:
        response = (
            supabase
            .table("transfer_logs")
            .insert(data)
            .execute()
        )
        return response.data
    except Exception as e:
        raise Exception(f"ไม่สามารถบันทึกประวัติการโอนย้ายได้: {e}") from e

# ==========================================================
# upload pdf
# ==========================================================

def upload_pdf_to_supabase(local_path, filename):
    try:
        with open(local_path, "rb") as f:
            file_bytes = f.read()
        
        # อัปโหลดไฟล์ไปยัง bucket ชื่อ 'transfer-documents'
        response = supabase.storage.from_("transfer-documents").upload(
            path=filename,
            file=file_bytes,
            file_options={"content-type": "application/pdf", "upsert": "true"}
        )
        print("Upload Response:", response)
        return True
    except Exception as e:
        print(f"Upload to Supabase Storage Error Detail: {e}")
        return False