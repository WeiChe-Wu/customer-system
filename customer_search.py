import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="北營業務客戶維護系統 (極速版)", layout="wide")
st.title("☁️ 雲端客戶資料維護系統 (極速版)")

# --- 雲端連線設定 ---
@st.cache_resource
def get_sheet():
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
    client = gspread.authorize(creds)
    return client.open("客戶名單雲端版").sheet1

# --- 改用按需載入 ---
@st.cache_data(ttl=600)
def get_all_data():
    sheet = get_sheet()
    # 讀取整張表
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    if '客戶代號' in df.columns:
        df['客戶代號'] = df['客戶代號'].astype(str).str.strip()
    return df

# 初始化邏輯：不自動顯示全部資料，只有在必要時讀取
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
query = st.text_input("搜尋客戶 (輸入關鍵字後按 Enter)：", placeholder="例如：代號或簡稱")

# 只有在有篩選或搜尋的情況下才顯示
if not query and selected_sales == "全部" and selected_area == "全部":
    st.info("💡 請在左側選取業務/轄區，或使用上方搜尋框來查詢資料。")
else:
    if query:
        mask = (temp_df['客戶簡稱'].astype(str).str.contains(query, case=False) | 
                temp_df['客戶全稱'].astype(str).str.contains(query, case=False) | 
                temp_df['客戶代號'].astype(str).str.contains(query, case=False))
        results = temp_df[mask]
    else:
        results = temp_df

    # --- 顯示與維護 ---
    if not results.empty:
        st.write(f"找到 {len(results)} 筆相符資料")
        for idx, row in results.iterrows():
            with st.expander(f"🏢 [{row.get('轄區')}] {row['客戶簡稱']} ({row['客戶代號']})"):
                # (顯示資料與維護欄位邏輯同前一版)
                # ... [略] ...
                if st.button("上傳至雲端", key=f"save_{idx}"):
                    sheet = get_sheet()
                    # 這裡找到原始行號 (重新計算 index)
                    target_row = df[df['客戶代號'] == row['客戶代號']].index[0] + 2
                    sheet.update_cell(target_row, 12, st.session_state[f"count_{idx}"])
                    sheet.update_cell(target_row, 13, st.session_state[f"rec_{idx}"])
                    sheet.update_cell(target_row, 14, st.session_state[f"date_{idx}"])
                    st.success("✅ 已同步至 Google Sheets！")
                    st.cache_data.clear() # 強制更新快取
    else:
        st.warning("查無相符資料。")
