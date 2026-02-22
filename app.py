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

# 1. 설정값 및 가중치 (이전과 동일)
MAX_WORKERS = 10
REQUEST_TIMEOUT = 6
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}

WEIGHTS = {"그룹 A": 10.0, "그룹 B": 5.0, "그룹 C": 2.0, "": 1.0, "PICK_MULTIPLIER": 1.5, "TITLE_BONUS": 3.0}
SENTIMENT_DICT = {
    "positive": ["성장", "흑자", "혁신", "인기", "급증", "돌풍", "1위", "상생", "호조", "성공", "확대", "유치"],
    "negative": ["논란", "위기", "적자", "하락", "감소", "조사", "의혹", "비판", "중단", "우려", "갈등", "부진"]
}

# [기존 FIXED_MAP, OID_MAP, GROUP_MAP 생략 - 실제 코드엔 포함하세요]

# --- 핵심 분석 함수들 ---
def analyze_article_content(link, query):
    if "naver.com" not in link: return 0.0, 0.0
    try:
        res = requests.get(link, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        soup = BeautifulSoup(res.text, 'html.parser')
        content = soup.select_one('#newsct_article, #articeBody')
        if content:
            text = content.get_text()
            freq_score = min(text.count(query) * 0.3, 5.0)
            pos = sum(text.count(w) for w in SENTIMENT_DICT["positive"])
            neg = sum(text.count(w) for w in SENTIMENT_DICT["negative"])
            sentiment_val = (pos - neg) / (pos + neg) if (pos + neg) > 0 else 0.0
            return freq_score, sentiment_val
    except: pass
    return 0.0, 0.0

# --- 페이지 설정 ---
st.set_page_config(page_title="영향력 & 리스크 뉴스 클리핑", layout="wide")
st.title("🚀 글로벌 이슈 파급력 & 리스크 모니터링")
st.caption("키워드를 입력하면 주요 매체 가중치와 본문 분석을 통해 파급력 지수를 산출합니다.")

# 2. 검색 입력창 (이 부분이 제목 바로 아래에 보여야 합니다)
st.divider()
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    query = st.text_input("검색 키워드 입력", placeholder="예: 무신사, K-패션")
with col2:
    days = st.selectbox("검색 기간", options=[1, 3, 7, 14, 30], index=2, format_func=lambda x: f"최근 {x}일")
with col3:
    st.write("") # 간격 맞춤용
    search_button = st.button("🔍 데이터 분석 시작", use_container_width=True, type="primary")

# 3. 사이드바 API 설정
with st.sidebar:
    st.header("🔑 API 설정")
    client_id = st.text_input("Naver Client ID", type="password")
    client_secret = st.text_input("Naver Client Secret", type="password")
    st.info("네이버 개발자 센터에서 발급받은 키를 입력하세요.")

# 4. 실행 로직
if search_button:
    if not query:
        st.warning("키워드를 입력해주세요.")
    elif not client_id or not client_secret:
        st.error("사이드바에 네이버 API 키를 입력해주세요.")
    else:
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # [기존 run_search 로직을 호출하여 df 생성]
        # 예시를 위해 단순화된 흐름으로 기재 (실제로는 이전의 run_search 전체 코드가 여기 들어감)
        with st.spinner("데이터 수집 및 AI 분석 중..."):
            # 임시 데이터 생성 예시 (실제 연동 시 run_search 함수 실행)
            # df = run_search(query, client_id, client_secret, progress_bar, status_text, days)
            # st.session_state["df"] = df
            st.success("수집이 완료되었습니다!")

# 5. 결과 대시보드 표시
if "df" in st.session_state:
    df = st.session_state["df"]
    # [이전에 드린 대시보드 시각화 및 테이블 렌더링 코드 위치]
