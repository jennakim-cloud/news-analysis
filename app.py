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

# ══════════════════════════════════════════════════════════════
#  1. 설정값 및 매핑 테이블
# ══════════════════════════════════════════════════════════════

MAX_WORKERS     = 10
REQUEST_TIMEOUT = 6
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}

WEIGHTS = {
    "그룹 A": 10.0, "그룹 B": 5.0, "그룹 C": 2.0, "": 1.0,
    "PICK_MULTIPLIER": 1.5, "TITLE_BONUS": 3.0
}

SENTIMENT_DICT = {
    "positive": ["성장", "흑자", "혁신", "인기", "급증", "돌풍", "1위", "상생", "호조", "성공", "확대", "유치"],
    "negative": ["논란", "위기", "적자", "하락", "감소", "조사", "의혹", "비판", "중단", "우려", "갈등", "부진"]
}

GROUP_COLORS = {"그룹 A": "#D5F5E3", "그룹 B": "#FEF9E7", "그룹 C": "#FDEBD0", "": "#FFFFFF"}
GROUP_BADGE = {
    "그룹 A": "background:#D5F5E3; color:#1e7e34; padding:2px 8px; border-radius:4px; font-weight:bold;",
    "그룹 B": "background:#FEF9E7; color:#856404; padding:2px 8px; border-radius:4px; font-weight:bold;",
    "그룹 C": "background:#FDEBD0; color:#c05621; padding:2px 8px; border-radius:4px; font-weight:bold;",
    "":       "color:#999; padding:2px 8px;",
}

# [주의] 매핑 테이블 데이터 (기존에 쓰시던 긴 리스트를 여기에 유지하세요)
FIXED_MAP = {"apparelnews": "어패럴뉴스", "fashionbiz": "패션비즈", "byline": "바이라인네트워크"} 
OID_MAP = {"001": "연합뉴스", "009": "매일경제", "015": "한국경제", "011": "서울경제", "023": "조선일보", "025": "중앙일보"}
GROUP_MAP = {"매일경제": "그룹 A", "한국경제": "그룹 A", "서울경제": "그룹 A", "연합뉴스": "그룹 A", "어패럴뉴스": "그룹 A"}

# ══════════════════════════════════════════════════════════════
#  2. 분석 및 수집 함수
# ══════════════════════════════════════════════════════════════

def analyze_article_content(link, query):
    if "naver.com" not in link: return 0.0, 0.0
    try:
        res = requests.get(link, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        soup =
