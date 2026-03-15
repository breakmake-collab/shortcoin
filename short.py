import streamlit as st
import ccxt
import pandas as pd
import pandas_ta as ta
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="VIP SHORT SCANNER", layout="centered")

# 2. 아이폰 17 최적화 및 숏 전용 디자인
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    h1 { font-size: 1.1rem !important; text-align: center; margin-bottom: 15px; color: #ff4b4b; }
    
    .status-container {
        display: flex;
        justify-content: space-between;
        background: #1e2129;
        padding: 10px 5px;
        border-radius: 10px;
        margin-bottom: 15px;
        border: 1px solid #4b1e1e;
    }
    .status-item { text-align: center; flex: 1; border-right: 1px solid #3e424b; }
    .status-item:last-child { border-right: none; }
    .status-label { font-size: 0.65rem; color: #848e9c; display: block; }
    .status-value { font-size: 0.85rem; font-weight: bold; color: #ff4b4b; }

    .info-guide {
        background-color: #1a1515;
        padding: 12px;
        border-radius: 8px;
        border-left: 3px solid #ff4b4b;
        margin-bottom: 15px;
    }
    .info-title { font-size: 0.75rem; font-weight: bold; color: #ff4b4b; margin-bottom: 6px; display: block; }
    .info-item { font-size: 0.68rem; color: #d1d4dc; line-height: 1.5; display: block; }

    .stButton>button { 
        height: 3.5em; font-size: 0.85rem; border-radius: 8px;
        background-color: #ff4b4b; color: white; font-weight: bold; margin-top: 5px;
    }
    .update-time { font-size: 0.65rem; color: #848e9c; text-align: center; margin-top: 10px; }
    .stDataFrame { font-size: 0.65rem !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 사이드바 설정 ---
st.sidebar.header("📉 SHORT CONFIG")
rsi_limit = st.sidebar.number_input("1H RSI 이상 (과매수)", 1, 100, 90)

# --- 메인 화면 ---
st.title("🏹 BITGET VIP SHORT SCANNER")

# 한 줄 지표 요약
st.markdown(f"""
<div class="status-container">
    <div class="status-item"><span class="status-label">최소 RSI</span><span class="status-value">≥ {rsi_limit}</span></div>
    <div class="status-item"><span class="status-label">거래량</span><span class="status-value">전봉대비 감소</span></div>
    <div class="status-item"><span class="status-label">포지션</span><span class="status-value">SHORT</span></div>
</div>
""", unsafe_allow_html=True)

# 지표 설명 가이드
st.markdown("""
<div class="info-guide">
    <span class="info-title">📊 숏 전략 가이드</span>
    <span class="info-item">• <b>RSI 90↑:</b> 초과매수 상태로 곧 하락 조정 임박</span>
    <span class="info-item">• <b>거래량 감소:</b> 가격 상승 에너지가 고갈된 상태</span>
    <span class="info-item">• <b>🔮다이버:</b> 고점은 높으나 지표는 낮아지는 반전 신호</span>
    <span class="info-item">• <b>✅진입:</b> 5분봉이 이평선 아래로 안착 시 타점</span>
</div>
""", unsafe_allow_html=True)

run_button = st.button('🚀 비트겟 전 종목 숏 스캔 시작')

# --- 분석 로직 ---
exchange = ccxt.bitget({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})

def analyze_short(symbol):
    try:
        # 1시간 봉 데이터
        ohlcv_1h = exchange.fetch_ohlcv(symbol, '1h', limit=60)
        df_1h = pd.DataFrame(ohlcv_1h, columns=['time','open','high','low','close','volume'])
        df_1h['rsi'] = ta.rsi(df_1h['close'], length=14)
        
        last = df_1h.iloc[-1]
        prev = df_1h.iloc[-2]
        
        # 숏 진입 조건: RSI 90↑ & 거래량 감소
        if (not pd.isna(last['rsi']) and last['rsi'] >= rsi_limit and 
            last['volume'] < prev['volume']):
            
            # 하락 다이버전스
            diver = ""
            high_lookback = df_1h.iloc[-15:-2]
            if last['high'] >= high_lookback['high'].max() * 0.99 and last['rsi'] < high_lookback['rsi'].max() - 2:
                diver = "🔮"

            # 5분봉 이평선 하방 돌파
            ohlcv_5m = exchange.fetch_ohlcv(symbol, '5m', limit=15)
            df_5m = pd.DataFrame(ohlcv_5m, columns=['time','open','high','low','close','volume'])
            ma10 = df_5m['close'].rolling(window=10).mean().iloc[-1]
            entry = "✅" if df_5m['close'].iloc[-1] < ma10 else "⏳" 

            # --- 손절가(SL) 및 목표가(TP) 계산 ---
            # SL: 최근 고점 대비 약 0.7% 위
            # TP: 손익비 1:1.5 적용 (진입가 - (SL - 진입가) * 1.5)
            entry_price = last['close']
            stop_loss = last['high'] * 1.007 
            risk = stop_loss - entry_price
            take_profit = entry_price - (risk * 1.5)

            return {
                "코인": symbol.split(':')[0].replace('/USDT', ''),
                "RSI": round(last['rsi'], 1),
                "전봉대비": f"-{round((1 - last['volume']/prev['volume'])*100, 1)}%",
                "신호": f"{diver}{entry}",
                "손절가": f"{stop_loss:g}",
                "목표가": f"{take_profit:g}",
                "is_vip": True if (diver == "🔮" and entry == "✅") else False
            }
    except: return None
    return None

if run_button:
    try:
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get('linear') and m.get('quote') == 'USDT' and m.get('active')]
        with st.spinner('폭락 예상 종목 분석 중...'):
            with ThreadPoolExecutor(max_workers=30) as executor:
                results = [r for r in list(executor.map(analyze_short, symbols)) if r is not None]
        
        if results:
            df = pd.DataFrame(results)
            vip = df[df['is_vip'] == True].drop(columns=['is_vip'])
            others = df[df['is_vip'] == False].drop(columns=['is_vip'])

            if not vip.empty:
                st.error("🏆 VIP SHORT (강력 권장)")
                st.dataframe(vip, hide_index=True, use_container_width=True)
            else:
                st.warning("⚠️ 현재 조건에 일치하는 VIP 숏 종목이 없습니다.")
            
            if not others.empty:
                st.write("📋 숏 대기 후보군")
                st.dataframe(others.sort_values("RSI", ascending=False), hide_index=True, use_container_width=True)
            
            st.markdown(f'<div class="update-time">마지막 스캔: {datetime.now().strftime("%H:%M:%S")}</div>', unsafe_allow_html=True)
        else:
            st.info("조건 일치 코인 없음")
    except Exception as e:
        st.error(f"오류: {e}")