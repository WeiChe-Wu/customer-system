import streamlit as st
import gspread
import pandas as pd
import json
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="北營業務客戶維護系統 (雲端版)", layout="wide")
st.title("☁️ 雲端客戶資料維護系統")

# --- 雲端連線設定 ---
@st.cache_resource
def get_sheet():
    # 這是從 Streamlit Cloud 後台讀取機密金鑰的寫法
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"])
    client = gspread.authorize(creds)
    return client.open("customer_list_cloud").sheet1

@st.cache_data(ttl=60) # 每60秒自動重新讀取一次最新資料
def load_data():
    sheet = get_sheet()
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    
    # 強制將客戶代號轉為字串，並確保它保留前導 0
    # 假設你的代號長度是 7 碼 (例如 0802017)
    if '客戶代號' in df.columns:
        df['客戶代號'] = df['客戶代號'].astype(str).str.zfill(7) 
    return df

# 初始化資料
df = load_data()

# --- 篩選面板 (側邊欄) ---
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

# --- 查詢介面 ---
query = st.text_input("搜尋客戶 (代號/簡稱/全稱)：", placeholder="輸入關鍵字")

if query:
    mask = (temp_df['客戶簡稱'].astype(str).str.contains(query, case=False) | 
            temp_df['客戶全稱'].astype(str).str.contains(query, case=False) | 
            temp_df['客戶代號'].astype(str).str.contains(query, case=False))
    results = temp_df[mask]
else:
    results = temp_df

# --- 顯示與維護 ---
if not results.empty:
    for idx, row in results.iterrows():
        with st.expander(f"🏢 [{row.get('轄區')}] {row['客戶簡稱']} ({row['客戶代號']})"):
            # 顯示基本資料... (同之前代碼)
            # ...
            
            # 維護區
            new_count = st.text_input("拜訪次數", value=row.get('拜訪次數', ''), key=f"count_{idx}")
            new_record = st.text_input("拜訪紀錄", value=row.get('拜訪紀錄', ''), key=f"rec_{idx}")
            new_date = st.text_input("最近一次拜訪日期", value=row.get('最近一次拜訪日期', ''), key=f"date_{idx}")
            
            if st.button("上傳至雲端", key=f"save_{idx}"):
                sheet = get_sheet()
                # 找到對應的列 (getRow 是從 1 開始，df 是從 0 開始，且試算表有標題列，所以 +2)
                row_num = df[df['客戶代號'] == row['客戶代號']].index[0] + 2
                
                # 更新特定儲存格 (假設 Column 12, 13, 14 分別是拜訪次數等)
                # 這裡需要對應你試算表實際的欄位順序
                sheet.update_cell(row_num, 12, new_count) 
                sheet.update_cell(row_num, 13, new_record)
                sheet.update_cell(row_num, 14, new_date)
                
                st.success("✅ 已同步至 Google Sheets！")
                st.cache_data.clear() # 強制更新快取
