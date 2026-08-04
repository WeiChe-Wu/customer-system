import streamlit as st
import gspread
import pandas as pd
from oauth2client.service_account import ServiceAccountCredentials
import datetime

# --- 網頁設定 ---
st.set_page_config(page_title="北營業務客戶維護系統", layout="wide")
st.title("☁️ 雲端老客戶拜訪名單維護系統")

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


# --- 通用補零函式 ---
# 用「已知欄位應有長度」補零，比「長度剛好少一碼才補」更穩健，
# 未來若同一筆資料意外少兩碼以上也能救回來。
# 長期建議：在 Google Sheets 把「電話」「行動電話」「統一編號」欄位格式設為「純文字」，
# 從源頭避免資料被自動轉成數字而遺失開頭的 0，此函式僅作為顯示層的保險修正。
def pad_zero(x, length):
    x = str(x).strip()
    if x.isdigit() and len(x) < length:
        return x.zfill(length)
    return x


# --- 資料讀取 (含手機、統編補0邏輯) ---
@st.cache_data(ttl=60)
def get_all_data():
    sheet = get_sheet()
    all_data = sheet.get_all_values()
    if not all_data:
        return pd.DataFrame()

    header = all_data[0]
    data = all_data[1:]
    df = pd.DataFrame(data, columns=header)

    # 【手機/電話補0】台灣手機、市話(含區碼)正確長度為 10 碼
    if '行動電話' in df.columns:
        df['行動電話'] = df['行動電話'].apply(lambda x: pad_zero(x, 10))
    if '電話' in df.columns:
        df['電話'] = df['電話'].apply(lambda x: pad_zero(x, 10))

    # 【統編補0】台灣統一編號固定為 8 碼
    if '統一編號' in df.columns:
        df['統一編號'] = df['統一編號'].apply(lambda x: pad_zero(x, 8))

    if '客戶代號' in df.columns:
        df['客戶代號'] = df['客戶代號'].astype(str).str.strip()

    return df


# 載入資料
df = get_all_data()

# 【讀取防呆】連線失敗或欄位異常時，顯示友善訊息並中止，避免同仁看到原始錯誤訊息
if df.empty or '經營業務' not in df.columns:
    st.error("⚠️ 目前無法讀取客戶資料，請確認 Google Sheets 連線或欄位設定，並聯繫系統維護人員。")
    st.stop()

# --- 初始化收合狀態 ---
if 'all_expanded' not in st.session_state:
    st.session_state.all_expanded = False

# 【搜尋歷史】記住本次瀏覽器連線期間搜尋過的關鍵字，方便快速再查一次
if 'search_history' not in st.session_state:
    st.session_state.search_history = []

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

# --- 搜尋邏輯 (含地址關鍵字) ---
query = st.text_input(
    "搜尋客戶 (代號/簡稱/全稱/地址)：",
    placeholder="輸入關鍵字，例如：代號、路名或行政區",
    key="search_query",
)

# 【搜尋歷史顯示】點擊即可快速重新查詢，並可一鍵清除
if st.session_state.search_history:
    hist_col, clear_col = st.columns([10, 1])
    with hist_col:
        st.caption("🕘 最近搜尋：")
        chip_cols = st.columns(len(st.session_state.search_history))
        for i, term in enumerate(st.session_state.search_history):
            with chip_cols[i]:
                if st.button(term, key=f"hist_{i}"):
                    st.session_state.search_query = term
                    st.rerun()
    with clear_col:
        if st.button("🗑️", key="clear_history", help="清除搜尋紀錄"):
            st.session_state.search_history = []
            st.rerun()

# 將本次有效搜尋加入歷史紀錄（去重、最多保留 8 筆、最新的排最前面）
if query:
    history = st.session_state.search_history
    if query in history:
        history.remove(query)
    history.insert(0, query)
    st.session_state.search_history = history[:8]

search_results = temp_df
if query:
    mask = (search_results['客戶簡稱'].astype(str).str.contains(query, case=False) |
            search_results['客戶全稱'].astype(str).str.contains(query, case=False) |
            search_results['客戶代號'].astype(str).str.contains(query, case=False) |
            search_results['地址'].astype(str).str.contains(query, case=False))
    search_results = search_results[mask]

display_results = search_results.head(50)

# --- 一鍵收合按鈕 ---
if st.button("切換全部 展開/收合"):
    st.session_state.all_expanded = not st.session_state.all_expanded
    st.rerun()

# --- 顯示與維護 ---
if not display_results.empty:
    # 【筆數顯示修正】原本用 display_results（已被 head(50) 截斷）計算筆數，
    # 導致超過 50 筆時畫面永遠只顯示「找到 50 筆」。改用 search_results 顯示實際符合筆數。
    total_count = len(search_results)
    shown_count = len(display_results)
    if total_count > shown_count:
        st.write(f"共符合 {total_count} 筆資料，以下顯示前 {shown_count} 筆，請輸入更精確的關鍵字縮小範圍")
    else:
        st.write(f"找到 {total_count} 筆資料")

    for idx, row in display_results.iterrows():
        title = f"🏢 [{row.get('轄區', '')}] {row.get('客戶簡稱', '無')} ({row.get('客戶代號', '')})"

        with st.expander(title, expanded=st.session_state.all_expanded):
            # 1. 基本資料顯示
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**客戶代號：** {row.get('客戶代號', '')}")
                st.markdown(f"**電話：** {row.get('電話', '')}")
                st.markdown(f"**行動電話：** {row.get('行動電話', '')}")
                st.markdown(f"**客戶全稱：** {row.get('客戶全稱', '')}")
                st.markdown(f"**負責人：** {row.get('負責人', '')}")
                st.markdown(f"**聯絡人：** {row.get('聯絡人', '')}")
                st.markdown(f"**網路人數：** {row.get('網路人數', '')}")
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
            except Exception:
                default_date = datetime.date.today()

            selected_date = st.date_input("最近一次拜訪日期", value=default_date, key=f"date_{idx}")
            new_date_str = selected_date.strftime('%Y-%m-%d')

            # 3. 上傳按鈕
            if st.button("上傳至雲端", key=f"save_{idx}"):
                try:
                    sheet = get_sheet()

                    # 【重複代號防呆】客戶代號若重複，只會更新第一筆，需提醒使用者
                    matches = df[df['客戶代號'] == str(row['客戶代號'])]
                    if len(matches) > 1:
                        st.warning(
                            f"⚠️ 客戶代號「{row['客戶代號']}」在資料表中重複出現 {len(matches)} 次，"
                            f"請確認資料是否需要清理，本次僅更新第一筆符合的資料。"
                        )
                    # 根據客戶代號定位行號（+2：跳過標題列，並轉換為 1-based 列號）
                    target_row = matches.index[0] + 2

                    # 【動態欄位定位】改用欄位名稱查找實際欄號，避免日後表格欄位順序調整
                    # 導致寫死的欄號（12,13,14）對應到錯誤欄位
                    sheet_header = sheet.row_values(1)

                    def col_idx(name, header):
                        return header.index(name) + 1  # gspread 欄位從 1 開始

                    sheet.update_cell(target_row, col_idx('拜訪次數', sheet_header), new_count)
                    sheet.update_cell(target_row, col_idx('拜訪紀錄', sheet_header), new_record)
                    sheet.update_cell(target_row, col_idx('最近一次拜訪日期', sheet_header), new_date_str)

                    st.success(f"✅ 更新成功！日期：{new_date_str}")
                    st.cache_data.clear()
                except ValueError as e:
                    st.error(f"同步失敗：試算表缺少對應欄位 - {e}")
                except Exception as e:
                    st.error(f"同步失敗: {e}")
else:
    st.info("請輸入搜尋條件或調整篩選器。")
