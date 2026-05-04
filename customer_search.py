import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import datetime

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
    # 【請確保填入正確的 SPREADSHEET_ID】
    SPREADSHEET_ID = "1r-nFgfVwVRZRNQ5LmvnonvMFHJTTFe1lwOYZ_F57N5M" 
    return client.open_by_key(SPREADSHEET_ID).sheet1

# --- 資料讀取 (含補0邏輯) ---
@st.cache_data(ttl=60)
def get_all_data():
    sheet = get_sheet()
    # 使用 get_all_values 避免 gspread 自動將 09 開頭轉為數字
    all_data = sheet.get_all_values()
    if not all_data:
        return pd.DataFrame()
    
    header = all_data[0]
    data = all_data[1:]
    df = pd.DataFrame(data, columns=header)
    
    # 【補0功能】針對行動電話與電話，若只有 9 碼且為數字，自動補 0
    def fix_phone(x):
        x = str(x).strip()
        if x and x.isdigit() and len(x) == 9:
            return "0" + x
        return x

    if '行動電話' in df.columns:
        df['行動電話'] = df['行動電話'].apply(fix_phone)
    if '電話' in df.columns:
        df['電話'] = df['電話'].apply(fix_phone)
    if '客戶代號' in df.columns:
        # 客戶代號視需求補0，若不確定長度則維持現狀
        df['客戶代號'] = df['客戶代號'].astype(str).str.strip()
        
    return df

# 載入資料
df = get_all_data()

# --- 初始化收合狀態 ---
if 'all_expanded' not in st.session_state:
    st.session_state.all_expanded = False

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
search_results = temp_df
if query:
    mask = (search_results['客戶簡稱'].astype(str).str.contains(query, case=False) | 
            search_results['客戶全稱'].astype(str).str.contains(query, case=False) | 
            search_results['客戶代號'].astype(str).str.contains(query, case=False))
    search_results = search_results[mask]

display_results = search_results.head(50)

# --- 一鍵收合按鈕 ---
if st.button("切換全部 展開/收合"):
    st.session_state.all_expanded = not st.session_state.all_expanded
    st.rerun()

# --- 顯示與維護 ---
if not display_results.empty:
    st.write(f"找到 {len(display_results)} 筆資料")
    
    for idx, row in display_results.iterrows():
        title = f"🏢 [{row.get('轄區', '')}] {row.get('客戶簡稱', '無')} ({row.get('客戶代號', '')})"
        
        with st.expander(title, expanded=st.session_state.all_expanded):
            # 1. 基本資料顯示
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**客戶代號：** {row.get('客戶代號', '')}")
                st.markdown(f"**行動電話：** {row.get('行動電話', '')}")
                st.markdown(f"**客戶全稱：** {row.get('客戶全稱', '')}")
                st.markdown(f"**負責人：** {row.get('負責人', '')}")
                st.markdown(f"**聯絡人：** {row.get('聯絡人', '')}")
            with col2:
                st.markdown(f"**經營業務：** {row.get('經營業務', '')}")
                st.markdown(f"**成交業務：** {row.get('成交業務', '')}")
                st.markdown(f"**行業別：** {row.get('行業別', '')}")
                st.markdown(f"**統編：** {row.get('統一編號', '')}")
                st.markdown(f"**地址：** {row.get('地址', '')}")
            
            st.divider()
            st.subheader("📝 業務維護")
            
            # 2. 維護欄位
            new_count = st.text_input("拜訪次數", value=str(row.get('拜訪次數', '')), key=f"count_{idx}")
            new_record = st.text_input("拜訪紀錄", value=str(row.get('拜訪紀錄', '')), key=f"rec_{idx}")
            
            # 【日期選擇開窗功能】
            raw_date = str(row.get('最近一次拜訪日期', '')).strip()
            try:
                if raw_date and raw_date != 'None' and '-' in raw_date:
                    default_date = datetime.datetime.strptime(raw_date, '%Y-%m-%d').date()
                else:
                    default_date = datetime.date.today()
            except:
                default_date = datetime.date.today()

            selected_date = st.date_input("最近一次拜訪日期", value=default_date, key=f"date_{idx}")
            new_date_str = selected_date.strftime('%Y-%m-%d')
            
            # 3. 上傳按鈕
            if st.button("上傳至雲端", key=f"save_{idx}"):
                try:
                    sheet = get_sheet()
                    # 根據客戶代號定位行號
                    target_row = df[df['客戶代號'] == str(row['客戶代號'])].index[0] + 2
                    
                    # 更新至試算表 (請確認 12, 13, 14 欄位是否正確)
                    sheet.update_cell(target_row, 12, new_count)
                    sheet.update_cell(target_row, 13, new_record)
                    sheet.update_cell(target_row, 14, new_date_str)
                    
                    st.success(f"✅ 更新成功！日期：{new_date_str}")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"同步失敗: {e}")
else:
    st.info("請輸入搜尋條件或調整篩選器。")
