"""
admin_data_sync.py
-------------------
獨立的「CRM 資料同步」管理工具，與一般同仁使用的 customer_search.py 分開部署。
用途：業務人員從 CRM 系統匯出 Excel 後，以「客戶代號」為 key，
      比對並更新雲端 Google Sheets 資料庫，同時保留系統內自行維護的
      拜訪紀錄欄位不被覆蓋。

使用方式：
  streamlit run admin_data_sync.py
建議：另外部署一個獨立網址（不要跟一般同仁查詢頁共用），並在
      Streamlit secrets 設定 admin_password，避免非管理人員誤觸寫入。
"""

import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import io

st.set_page_config(page_title="CRM 資料同步工具（管理用）", layout="wide")
st.title("🔄 CRM 資料同步工具")
st.caption("以「客戶代號」為 key，比對 CRM 匯出的 Excel 並更新雲端客戶資料庫")

# ============ 基本設定（可依實際狀況調整） ============

# 比對用的主鍵欄位
KEY_COLUMN = "客戶代號"

# 這些欄位是「系統內自行維護」的欄位，CRM 匯入時絕對不覆蓋
LOCAL_ONLY_COLUMNS = ["拜訪次數", "拜訪紀錄", "最近一次拜訪日期"]

# 需要補零檢查的欄位與其正確長度（電話/統編從 CRM 匯出時，Excel 也常見遺失開頭 0 的問題）
ZERO_PAD_COLUMNS = {"電話": 10, "行動電話": 10, "統一編號": 8}

# 如果 CRM 匯出的欄位名稱跟系統 Google Sheets 的欄位名稱不同，
# 在這裡填入對照表，程式會自動改名，例如：
# CRM_COLUMN_MAPPING = {"客戶編號": "客戶代號", "公司電話": "電話"}
CRM_COLUMN_MAPPING = {}


# ============ 密碼保護 ============

def check_password():
    admin_password = st.secrets.get("admin_password", None)
    if not admin_password:
        st.error("尚未於 Streamlit secrets 設定 admin_password，請先設定後再使用本工具。")
        st.stop()

    if st.session_state.get("admin_unlocked"):
        return

    st.subheader("🔒 管理權限驗證")
    pwd = st.text_input("請輸入管理密碼", type="password")
    if st.button("登入"):
        if pwd == admin_password:
            st.session_state.admin_unlocked = True
            st.rerun()
        else:
            st.error("密碼錯誤")
    st.stop()


check_password()


# ============ Google Sheets 連線 ============

@st.cache_resource
def get_sheet():
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        creds_dict,
        ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(creds)
    # 【請確保與 customer_search.py 使用相同的 SPREADSHEET_ID】
    SPREADSHEET_ID = "1r-nFgfVwVRZRNQ5LmvnonvMFHJTTFe1lwOYZ_F57N5M"
    return client.open_by_key(SPREADSHEET_ID).sheet1


def pad_zero(x, length):
    x = str(x).strip()
    if x.isdigit() and len(x) < length:
        return x.zfill(length)
    return x


def load_sheet_df(sheet):
    all_data = sheet.get_all_values()
    if not all_data:
        return pd.DataFrame(), []
    header = all_data[0]
    data = all_data[1:]
    df = pd.DataFrame(data, columns=header)
    df[KEY_COLUMN] = df[KEY_COLUMN].astype(str).str.strip()
    return df, header


# ============ 步驟一：上傳 CRM 匯出檔 ============

st.divider()
st.subheader("步驟一：上傳 CRM 匯出的 Excel 檔")

uploaded_file = st.file_uploader("選擇 CRM 匯出的 .xlsx 檔案", type=["xlsx"])

if not uploaded_file:
    st.info("請先上傳 CRM 匯出的 Excel 檔案以開始比對。")
    st.stop()

try:
    crm_df = pd.read_excel(uploaded_file, dtype=str)
except Exception as e:
    st.error(f"讀取 Excel 失敗：{e}")
    st.stop()

crm_df = crm_df.rename(columns=CRM_COLUMN_MAPPING)
crm_df.columns = [str(c).strip() for c in crm_df.columns]

if KEY_COLUMN not in crm_df.columns:
    st.error(f"上傳的 Excel 中找不到「{KEY_COLUMN}」欄位，請確認匯出格式，或於 CRM_COLUMN_MAPPING 補上對照。")
    st.stop()

crm_df[KEY_COLUMN] = crm_df[KEY_COLUMN].astype(str).str.strip()
crm_df = crm_df[crm_df[KEY_COLUMN] != ""]

# 對 CRM 資料也套用補零修正，避免 Excel 匯出過程弄丟開頭的 0
for col, length in ZERO_PAD_COLUMNS.items():
    if col in crm_df.columns:
        crm_df[col] = crm_df[col].apply(lambda x: pad_zero(x, length))

st.success(f"已讀取 CRM 資料共 {len(crm_df)} 筆")

# ============ 讀取目前雲端資料 ============

sheet = get_sheet()
sheet_df, sheet_header = load_sheet_df(sheet)

if sheet_df.empty:
    st.error("目前雲端資料庫是空的或讀取失敗，請確認 Google Sheets 連線正常。")
    st.stop()

# 目前資料庫也套用同一套補零，確保比對基準一致（新舊都補過，才不會誤判差異）
for col, length in ZERO_PAD_COLUMNS.items():
    if col in sheet_df.columns:
        sheet_df[col] = sheet_df[col].apply(lambda x: pad_zero(x, length))

# 寫入前備份下載
backup_buffer = io.BytesIO()
sheet_df.to_excel(backup_buffer, index=False, engine="openpyxl")
st.download_button(
    "⬇️ 下載目前資料庫備份（建議在寫入前先下載）",
    data=backup_buffer.getvalue(),
    file_name="客戶資料庫_異動前備份.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

# ============ 步驟二：比對並產生預覽 ============

st.divider()
st.subheader("步驟二：比對差異（預覽，尚未寫入）")

# 實際會更新的欄位：CRM 檔案與雲端資料庫都有、且不是本地維護欄位、也不是 key 欄位本身
compare_columns = [
    c for c in crm_df.columns
    if c in sheet_df.columns and c not in LOCAL_ONLY_COLUMNS and c != KEY_COLUMN
]

if not compare_columns:
    st.warning("CRM 檔案與雲端資料庫之間沒有可比對更新的共同欄位，請確認欄位名稱是否一致。")
    st.stop()

existing_keys = set(sheet_df[KEY_COLUMN])
key_to_row_idx = {k: i for i, k in enumerate(sheet_df[KEY_COLUMN])}  # 0-based，對應 sheet 實際列需 +2

update_rows = []   # 既有客戶、且有欄位不同 -> 要更新
new_rows = []       # CRM 有、資料庫沒有 -> 要新增

for _, crm_row in crm_df.iterrows():
    key = crm_row[KEY_COLUMN]
    if key in existing_keys:
        sheet_row = sheet_df.loc[key_to_row_idx[key]]
        changes = {}
        for col in compare_columns:
            old_val = str(sheet_row.get(col, "")).strip()
            new_val = str(crm_row.get(col, "")).strip()
            if old_val != new_val:
                changes[col] = (old_val, new_val)
        if changes:
            update_rows.append({"key": key, "row_idx": key_to_row_idx[key], "changes": changes})
    else:
        new_rows.append(crm_row)

# CRM 已找不到、但資料庫還存在的客戶（僅供參考，不自動處理）
crm_keys = set(crm_df[KEY_COLUMN])
missing_in_crm = sorted(existing_keys - crm_keys)

col_a, col_b, col_c = st.columns(3)
col_a.metric("將更新既有客戶", f"{len(update_rows)} 筆")
col_b.metric("將新增新客戶", f"{len(new_rows)} 筆")
col_c.metric("CRM 中已找不到（僅提示）", f"{len(missing_in_crm)} 筆")

if update_rows:
    st.markdown("**📝 將更新的客戶（欄位變更明細）**")
    preview_rows = []
    for u in update_rows:
        for col, (old, new) in u["changes"].items():
            preview_rows.append({
                "客戶代號": u["key"],
                "變更欄位": col,
                "原值": old,
                "新值": new,
            })
    st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, height=300)

if new_rows:
    st.markdown("**➕ 將新增的客戶**")
    st.dataframe(pd.DataFrame(new_rows)[[KEY_COLUMN] + [c for c in compare_columns if c in crm_df.columns]],
                 use_container_width=True, height=250)

if missing_in_crm:
    with st.expander(f"ℹ️ CRM 匯出資料中已找不到的客戶代號（{len(missing_in_crm)} 筆，僅供參考，不會自動刪除）"):
        st.write(missing_in_crm)

if not update_rows and not new_rows:
    st.success("✅ 比對完成，資料庫與 CRM 匯出內容一致，沒有需要更新的項目。")
    st.stop()

# ============ 步驟三：確認寫入 ============

st.divider()
st.subheader("步驟三：確認寫入")

confirm = st.checkbox("我已檢查以上異動內容，確認無誤，同意寫入雲端資料庫")

if st.button("🚀 執行寫入", disabled=not confirm, type="primary"):
    with st.spinner("寫入中，請勿關閉視窗..."):
        try:
            # --- 更新既有客戶（批次寫入，避免逐筆呼叫 API 觸發流量限制） ---
            cell_list = []
            for u in update_rows:
                target_row = u["row_idx"] + 2  # +2：跳過標題列，轉為 1-based 列號
                for col, (old, new) in u["changes"].items():
                    col_num = sheet_header.index(col) + 1
                    cell_list.append(gspread.Cell(target_row, col_num, new))

            if cell_list:
                # value_input_option='RAW'：務必用 RAW，避免 Google Sheets 自動把
                # 「0912345678」這類字串重新解析成數字，導致開頭的 0 又被吃掉
                sheet.update_cells(cell_list, value_input_option="RAW")

            # --- 新增新客戶（批次 append） ---
            if new_rows:
                new_matrix = []
                for crm_row in new_rows:
                    row_values = []
                    for col in sheet_header:
                        if col in LOCAL_ONLY_COLUMNS:
                            row_values.append("")  # 本地維護欄位，新客戶預設空白
                        else:
                            row_values.append(str(crm_row.get(col, "")).strip())
                    new_matrix.append(row_values)
                sheet.append_rows(new_matrix, value_input_option="RAW")

            st.cache_data.clear()
            st.success(f"✅ 寫入完成！更新 {len(update_rows)} 筆、新增 {len(new_rows)} 筆。")
            st.info("提醒：一般查詢系統的資料快取最多 60 秒內會自動更新，無需重新部署。")
        except Exception as e:
            st.error(f"寫入失敗：{e}")
