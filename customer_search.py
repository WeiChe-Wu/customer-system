import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials

# --- 網頁設定 ---
st.set_page_config(page_title="北營業務客戶維護系統", layout="wide")
st.title("☁️ 雲端客戶資料維護系統")

# --- 雲端連線設定 ---
@st.cache_resource
def get_sheet():
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        creds_dict, 
        ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(creds)
    # 【請填入你的試算表 ID】
    SPREADSHEET_ID = "https://docs.google.com/spreadsheets/d/1r-nFgfVwVRZRNQ5LmvnonvMFHJTTFe1lwOYZ_F57N5M/edit?gid=0#gid=0"
    return client.open_by_key(SPREADSHEET_ID).sheet1

# --- 資料讀取 ---
@st.cache_data(ttl=60)
def get_all_data():
    sheet = get_sheet()
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    # 強制轉為文字以保留開頭 0
    if '客戶代號' in df.columns:
        df['客戶代號'] = df['客戶代號'].astype(str).str.strip()
    return df

# 載入資料
df = get_all_data()

# --- 側邊欄篩選 ---
st.sidebar.header("🎯 篩選面板")
sales_list = ["全部"] + sorted([s for s in df['經營業務'].unique() if s])
selected_sales = st.sidebar.selectbox("經營業務：", sales_list)

temp_df = df.copy()
if selected_sales != "全部":
    temp_df = temp_df[temp_df['經營業務'] == selected_sales]

area_list = ["全部"] + sorted([a for a in temp_df['轄區'].unique() if a])
selected_area = st.sidebar.selectbox("轄區：", area_list)

if selected_area != "全部":
    temp_df = temp_df[temp_df['轄區'] == selected_area]

# --- 搜尋邏輯 ---
query = st.text_input("搜尋客戶 (代號/簡稱/全稱)：", placeholder="輸入關鍵字")
results = temp_df
if query:
    mask = (results['客戶簡稱'].astype(str).str.contains(query, case=False) | 
            results['客戶全稱'].astype(str).str.contains(query, case=False) | 
            results['客戶代號'].astype(str).str.contains(query, case=False))
    results = results[mask]

# --- 顯示與維護 ---
if not results.empty:
    st.write(f"找到 {len(results)} 筆資料")
    
    for idx, row in results.iterrows():
        # 顯示區塊
        with st.expander(f"🏢 [{row.get('轄區', '')}] {row.get('客戶簡稱', '無名稱')} ({row.get('客戶代號', '')})"):
            st.markdown(f"**全稱：** {row.get('客戶全稱', '無')}")
            
            # 輸入框 (預設填入舊資料)
            new_count = st.text_input("拜訪次數", value=str(row.get('拜訪次數', '')), key=f"count_{idx}")
            new_record = st.text_input("拜訪紀錄", value=str(row.get('拜訪紀錄', '')), key=f"rec_{idx}")
            new_date = st.text_input("最近一次拜訪日期", value=str(row.get('最近一次拜訪日期', '')), key=f"date_{idx}")
            
            # 更新按鈕
            if st.button("上傳至雲端", key=f"save_{idx}"):
                try:
                    sheet = get_sheet()
                    # 找到該筆資料在 Google Sheets 的行號 (Index + 2)
                    target_row = df[df['客戶代號'] == str(row['客戶代號'])].index[0] + 2
                    
                    # 【注意】這裡的 12, 13, 14 請對應試算表實際欄位
                    sheet.update_cell(target_row, 12, new_count)
                    sheet.update_cell(target_row, 13, new_record)
                    sheet.update_cell(target_row, 14, new_date)
                    
                    st.success("✅ 已更新！")
                    st.cache_data.clear() # 清除快取強制更新
                except Exception as e:
                    st.error(f"同步失敗: {e}")
else:
    st.info("請輸入條件進行搜尋。")
