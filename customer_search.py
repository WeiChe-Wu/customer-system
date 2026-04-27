import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials

# 頁面設定
st.set_page_config(page_title="雲端客戶維護系統", layout="wide")
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
    # 請確保試算表名稱正確
    return client.open("customer_list_cloud").sheet1

# --- 資料讀取 (加快取) ---
@st.cache_data(ttl=600)
def get_all_data():
    sheet = get_sheet()
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
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

if query:
    mask = (temp_df['客戶簡稱'].astype(str).str.contains(query, case=False) | 
            temp_df['客戶全稱'].astype(str).str.contains(query, case=False) | 
            temp_df['客戶代號'].astype(str).str.contains(query, case=False))
    results = temp_df[mask]
else:
    results = temp_df

 --- 顯示與維護 ---
if not results.empty:
    st.write(f"找到 {len(results)} 筆相符資料 (僅顯示前 50 筆)")
    display_results = results.head(50)
    
    for idx, row in display_results.iterrows():
        row_dict = row.to_dict()
        with st.expander(f"🏢 [{row_dict.get('轄區', '')}] {row_dict.get('客戶簡稱', '無名稱')} ({row_dict.get('客戶代號', '')})"):
            st.write(f"全稱：{row_dict.get('客戶全稱', '')}")
            
            # 輸入框
            new_count = st.text_input("拜訪次數", value=str(row_dict.get('拜訪次數', '')), key=f"count_{idx}")
            new_record = st.text_input("拜訪紀錄", value=str(row_dict.get('拜訪紀錄', '')), key=f"rec_{idx}")
            new_date = st.text_input("最近一次拜訪日期", value=str(row_dict.get('最近一次拜訪日期', '')), key=f"date_{idx}")
            
            if st.button("上傳至雲端", key=f"save_{idx}"):
                try:
                    sheet = get_sheet()
                    # 重新計算行號 (原始 DataFrame 的 index + 2)
                    target_row = df[df['客戶代號'] == str(row_dict.get('客戶代號'))].index[0] + 2
                    
                    # 寫入資料 (請確認欄位順序 12, 13, 14 是否對應)
                    sheet.update_cell(target_row, 12, new_count)
                    sheet.update_cell(target_row, 13, new_record)
                    sheet.update_cell(target_row, 14, new_date)
                    
                    st.success("✅ 已同步至 Google Sheets！")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"同步失敗: {e}")
else:
    st.warning("查無資料。")
