import os
import streamlit as st
import mysql.connector
import pandas as pd
import folium
from folium.plugins import LocateControl
from streamlit_folium import st_folium
import streamlit.components.v1 as components
from math import radians, cos, sin, asin, sqrt
# 👇 내 위치를 파이썬 변수로 가져오기 위한 핵심 라이브러리
from streamlit_js_eval import get_geolocation

# -----------------------------------------------------------------------------
# 설정
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="블루핸즈 근처 조회",
    page_icon="🚘",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "user": os.getenv("MYSQL_USER", "root"),
    "password": os.getenv("MYSQL_PASSWORD", "root"),
    "database": os.getenv("MYSQL_DB", "bluehands_db"),
    "charset": "utf8mb4",
}


def get_conn():
    return mysql.connector.connect(**DB_CONFIG)


# =============================================================================
# [Marker.py] 거리 계산 로직 (Haversine)
# =============================================================================

def haversine(lon1, lat1, lon2, lat2):
    """
    lon1, lat1: 내 위치 (또는 기준점)
    lon2, lat2: 가게 위치
    """
    # 값이 하나라도 없으면 계산 불가
    if any(x is None for x in [lon1, lat1, lon2, lat2]):
        return None

    R = 6371  # 지구 반지름 (km)
    lon1, lat1, lon2, lat2 = map(radians, [float(lon1), float(lat1), float(lon2), float(lat2)])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * asin(sqrt(a))
    return c * R


def add_markers_to_map(m, rows, user_lat=None, user_lng=None):
    """
    지도에 마커 추가 함수
    user_lat, user_lng: 실제 GPS 좌표 (있으면 거리 계산, 없으면 경고 표시)
    """
    fg = folium.FeatureGroup(name="검색 결과")

    for row in rows:
        shop_lat = row.get("latitude")
        shop_lng = row.get("longitude")

        # 좌표 없는 데이터 건너뜀
        if shop_lat is None or shop_lng is None:
            continue

        try:
            lat, lng = float(shop_lat), float(shop_lng)
        except (TypeError, ValueError):
            continue

        name = row.get("name", "지점")
        addr = row.get("address", "")
        phone = row.get("phone", "")

        # -----------------------------------------------------------
        # 📏 거리 계산 로직 (수정됨)
        # 내 위치(user_lat/lng)가 있으면 그것과 계산
        # -----------------------------------------------------------
        dist_str = ""

        if user_lat is not None and user_lng is not None:
            # 내 위치 <-> 가게 위치
            dist_km = haversine(user_lng, user_lat, lng, lat)

            if dist_km is not None:
                if dist_km < 1:
                    dist_str = f"🚶 내 위치에서 {int(dist_km * 1000)}m"
                else:
                    dist_str = f"🚗 내 위치에서 {dist_km:.1f}km"
        else:
            dist_str = "⚠️ 위치 권한 필요 (거리 계산 불가)"

        # 팝업 HTML
        html = f"""
        <div style="width:220px; font-family:sans-serif;">
            <h4 style="margin:0; color:#0054a6;">{name}</h4>
            <p style="font-size:12px; margin:5px 0;">{addr}</p>
            <p style="font-size:12px; margin:0; color:blue;">📞 {phone}</p>
            <div style="margin-top:5px; border-top:1px solid #ddd; padding-top:5px;">
                <span style="color:red; font-weight:bold; font-size:13px;">{dist_str}</span>
            </div>
        </div>
        """

        folium.Marker(
            [lat, lng],
            popup=folium.Popup(html, max_width=300),
            tooltip=f"{name}",
            icon=folium.Icon(color="blue", icon="car", prefix="fa"),
        ).add_to(fg)

    fg.add_to(m)


# =============================================================================
# [selectbox.py] DB 조회 함수들
# =============================================================================

@st.cache_data(ttl=600)
def get_bluehands_data(search_text):
    conn = None
    try:
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        query = "SELECT name, latitude, longitude, address, phone FROM bluehands"
        params = []
        if search_text:
            query += " WHERE name LIKE %s OR address LIKE %s"
            pattern = f"%{search_text}%"
            params = [pattern, pattern]
        cursor.execute(query, params)
        return cursor.fetchall()
    except Exception as e:
        return []
    finally:
        if conn: conn.close()


@st.cache_data(ttl=600)
def get_shop_list():
    conn = get_conn()
    try:
        # regions 테이블 조인이 되어있다고 가정
        return pd.read_sql("""
            SELECT DISTINCT a.name AS shop_name, b.name AS region_name
            FROM bluehands a
            JOIN `regions` b ON a.`region_id` = b.id
            WHERE a.name IS NOT NULL
            ORDER BY b.name, a.name
            LIMIT 500
        """, conn)
    except:
        # 조인 실패 시 백업 쿼리 (regions 테이블 문제 대비)
        return pd.read_sql("SELECT name AS shop_name, '지역' AS region_name FROM bluehands LIMIT 100", conn)
    finally:
        conn.close()


def get_base_shop(selected_shop):
    conn = get_conn()
    try:
        # region_name 가져오는 부분은 테이블 구조에 맞게 유지
        return pd.read_sql("""
            SELECT a.*, b.name AS region_name
            FROM bluehands a
            JOIN `regions` b ON a.`region_id` = b.id
            WHERE a.name = %s
            LIMIT 1
        """, conn, params=(selected_shop,))
    finally:
        conn.close()


def get_nearby_four(selected_shop, base_lat, base_lng):
    conn = get_conn()
    try:
        # MySQL 5.7+ 필요 (ST_Distance_Sphere)
        return pd.read_sql("""
            SELECT a.name, b.name AS region_name, a.latitude, a.longitude,
                   ST_Distance_Sphere(POINT(a.longitude, a.latitude), POINT(%s, %s)) AS distance_m
            FROM bluehands a
            JOIN `regions` b ON a.`region_id` = b.id
            WHERE a.latitude IS NOT NULL AND a.longitude IS NOT NULL
              AND NOT (a.name = %s)
            ORDER BY distance_m
            LIMIT 4
        """, conn, params=(base_lng, base_lat, selected_shop))
    finally:
        conn.close()


def scroll_down():
    js = """<script>setTimeout(function(){window.parent.scrollTo({top: 600, behavior:'smooth'});}, 300);</script>"""
    components.html(js, height=0)


# =============================================================================
# [App.py] UI 시작
# =============================================================================

# 1. 헤더
st.markdown("""
<div class="main-header" style="background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 50%, #3d7ab5 100%); padding: 2rem; border-radius: 20px; margin-bottom: 2rem; text-align: center; color: white;">
    <h1>🚘 내 위치 기준 거리 계산기</h1>
    <p>브라우저 상단의 [위치 허용]을 눌러야 정확한 거리가 나옵니다.</p>
</div>
""", unsafe_allow_html=True)

# 2. [핵심] 사용자 실제 GPS 위치 가져오기 (리다이렉트 X, 파이썬 변수로 직행)
# ---------------------------------------------------------------------------
loc = get_geolocation()  # 브라우저에 위치 요청
user_lat = None
user_lng = None

if loc and 'coords' in loc:
    user_lat = loc['coords']['latitude']
    user_lng = loc['coords']['longitude']
    st.success(f"📍 GPS 연결 성공: 현재 위치 ({user_lat:.4f}, {user_lng:.4f}) 기준으로 거리를 계산합니다.")
else:
    st.warning("⚠️ 아직 위치 권한이 없거나 로딩 중입니다. (기본값: 서울 시청 기준)")
# ---------------------------------------------------------------------------


# 3. 검색창 (지점 선택)
name_list_df = get_shop_list()
options = ["(전체)"] + name_list_df["shop_name"].tolist()

# 라벨 생성 (지역명 포함)
shop_to_label = {}
if not name_list_df.empty:
    shop_to_label = dict(zip(
        name_list_df["shop_name"],
        name_list_df["shop_name"] + " (" + name_list_df["region_name"] + ")"
    ))

selected_shop = st.selectbox(
    "지점을 선택하세요 (선택 시 해당 지점 + 가까운 4곳 표시)",
    options,
    format_func=lambda x: x if x == "(전체)" else shop_to_label.get(x, x),
)

search_query = st.text_input("또는 지역명 직접 검색 (예: 강남)", key="text_search")

# 검색 시 스크롤 이동
if "last_search" not in st.session_state: st.session_state.last_search = ""
if search_query and search_query != st.session_state.last_search:
    st.session_state.last_search = search_query
    scroll_down()

# 4. 데이터 준비 (마커용)
marker_rows = []
map_center = [37.5665, 126.9780]  # 기본값

# (A) 셀렉트박스로 지점을 선택했을 때
if selected_shop != "(전체)":
    base_df = get_base_shop(selected_shop)
    if not base_df.empty:
        # 선택한 지점 정보
        st.subheader(f"선택: {selected_shop}")
        base_lat = base_df.loc[0, "latitude"]
        base_lng = base_df.loc[0, "longitude"]

        # 지도 중심을 선택한 지점으로 이동
        if base_lat and base_lng:
            map_center = [float(base_lat), float(base_lng)]

            # 마커 리스트에 추가 (선택한 지점)
            marker_rows.append(base_df.iloc[0].to_dict())

            # 주변 4곳 가져오기
            near_df = get_nearby_four(selected_shop, base_lat, base_lng)
            if not near_df.empty:
                st.caption("가까운 지점 4곳")
                # 주변 지점 마커 추가
                for _, r in near_df.iterrows():
                    marker_rows.append(r.to_dict())

                # 테이블 표시
                st.dataframe(near_df[["name", "region_name", "distance_m"]], hide_index=True)

# (B) 텍스트로 검색했을 때
if search_query:
    data_list = get_bluehands_data(search_query)
    if data_list:
        marker_rows = data_list  # 검색 결과로 덮어쓰기 (혹은 추가)
        # 검색 결과 첫 번째로 지도 중심 이동
        if data_list[0].get('latitude'):
            map_center = [float(data_list[0]['latitude']), float(data_list[0]['longitude'])]

# (C) GPS가 있고, 아무것도 선택 안 했으면 -> 내 위치가 지도 중심
if selected_shop == "(전체)" and not search_query and user_lat:
    map_center = [user_lat, user_lng]

# 5. 지도 그리기
st.markdown("### 📍 지도 보기")

# 지도 생성
m = folium.Map(location=map_center, zoom_start=13)
LocateControl().add_to(m)  # 지도 우측 상단 파란색 위치 버튼

# 내 위치가 확인되었다면 빨간색 마커로 표시
if user_lat and user_lng:
    folium.Marker(
        [user_lat, user_lng],
        popup="현재 내 위치",
        icon=folium.Icon(color="red", icon="user", prefix="fa")
    ).add_to(m)

# 검색된(또는 선택된) 마커들 지도에 찍기 + 거리 계산
if marker_rows:
    add_markers_to_map(m, marker_rows, user_lat, user_lng)

st_folium(m, height=500, use_container_width=True)