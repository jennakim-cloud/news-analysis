import io
import re
import html
import time
import requests
import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

# --- [기존 설정값 및 가중치, 매핑 테이블 동일하게 유지] ---
# ... (MAX_WORKERS, WEIGHTS, SENTIMENT_DICT, GROUP_MAP 등)

# --- [기본 분석 함수 동일하게 유지] ---
# ... (analyze_article_content, clean_html_text, run_search 등)

# --- 페이지 설정 ---
st.set_page_config(page_title="영향력 & 리스크 뉴스 클리핑", layout="wide")
st.title("🚀 글로벌 이슈 파급력 & 리스크 모니터링")
st.caption("자동으로 연결된 네이버 API를 통해 실시간 데이터를 분석합니다.")

# 1. 사이드바 구성 (입력창 제거, 상태만 표시)
with st.sidebar:
    st.header("🔐 시스템 상태")
    try:
        # Secrets가 정상적으로 로드되는지 확인
        client_id = st.secrets["naver"]["client_id"]
        client_secret = st.secrets["naver"]["client_secret"]
        st.success("API 서버에 연결되었습니다.")
    except Exception as e:
        st.error("Secrets 설정을 확인해주세요.")
        st.stop() # 설정이 안 되어 있으면 앱 중단
    
    st.divider()
    st.markdown("**리스크 관리 사전**")
    st.caption(f"호재 키워드: {', '.join(SENTIMENT_DICT['positive'][:5])}...")
    st.caption(f"위기 키워드: {', '.join(SENTIMENT_DICT['negative'][:5])}...")

# 2. 메인 UI 구성 (검색창 상단 고정)
st.divider()
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    query = st.text_input("검색 키워드 입력", placeholder="예: 무신사, K-패션")
with col2:
    days = st.selectbox("검색 기간", options=[1, 3, 7, 14, 30], index=2, format_func=lambda x: f"최근 {x}일")
with col3:
    st.write("") # 간격 맞춤용
    search_button = st.button("🔍 데이터 분석 시작", use_container_width=True, type="primary")

# 3. 실행 로직 (자동으로 client_id, client_secret 전달)
if search_button:
    if not query:
        st.warning("키워드를 입력해주세요.")
    else:
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # run_search 함수 실행 (인증 정보를 자동으로 st.secrets에서 가져와 전달)
        with st.spinner(f"'{query}'에 대한 글로벌 파급력 분석 중..."):
            df = run_search(
                query=query.strip(),
                client_id=st.secrets["naver"]["client_id"],
                client_secret=st.secrets["naver"]["client_secret"],
                progress_bar=progress_bar,
                status_text=status_text,
                days=days
            )
            
            if df is not None and not df.empty:
                st.session_state["df"] = df
                st.session_state["query"] = query
                st.success("분석이 완료되었습니다!")
            else:
                st.error("검색 결과가 없거나 오류가 발생했습니다.")

# 4. 결과 대시보드 표시 (기존 코드 유지)
if "df" in st.session_state:
    # ... (대시보드 시각화 및 테이블 렌더링 로직)
