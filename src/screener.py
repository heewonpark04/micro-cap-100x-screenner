#!/usr/bin/env python3
"""
Microcap 100x Screener
마이크로캡 ($50M-$500M) 고성장 종목 자동 스크리닝 시스템

섹터: 바이오텍, 우주/위성, AI 인프라
촉매: 임상 데이터, 계약 발표, 수익 인식
"""

import yfinance as yf
import pandas as pd
import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== 1. 데이터 수집 ====================

class MicrocapScreener:
    def __init__(self, min_mcap=50e6, max_mcap=500e6):
        self.min_mcap = min_mcap
        self.max_mcap = max_mcap
        self.candidates = pd.DataFrame()
        
    def get_nasdaq_tickers(self) -> List[str]:
        """
        NASDAQ 전체 종목 리스트 가져오기
        (실제로는 Finnhub, Polygon, 또는 CSV 다운로드 사용)
        
        Demo: 수동으로 주요 마이크로캡 샘플 반환
        """
        # 실제 환경: Finnhub API 사용
        # url = "https://finnhub.io/api/v1/stock/symbol?exchange=NASDAQ&token=API_KEY"
        
        sample_tickers = [
            'ABUS', 'IREN', 'RKLB',  # 알려진 것
            # 더 많은 마이크로캡 추가 필요
        ]
        
        logger.info(f"Fetching {len(sample_tickers)} NASDAQ tickers")
        return sample_tickers
    
    def get_market_cap(self, ticker: str) -> float:
        """종목의 현재 시가총액 가져오기"""
        try:
            data = yf.Ticker(ticker)
            info = data.info
            market_cap = info.get('marketCap', 0)
            
            if market_cap is None:
                # 대안: 가격 * 발행주식수
                price = info.get('currentPrice', 0)
                shares = info.get('sharesOutstanding', 0)
                market_cap = price * shares if price and shares else 0
            
            return float(market_cap) if market_cap else 0
        
        except Exception as e:
            logger.warning(f"Failed to get market cap for {ticker}: {e}")
            return 0
    
    def filter_by_market_cap(self, tickers: List[str]) -> List[str]:
        """시가총액 필터링"""
        filtered = []
        
        for ticker in tickers:
            mcap = self.get_market_cap(ticker)
            
            if self.min_mcap <= mcap <= self.max_mcap:
                filtered.append(ticker)
                logger.info(f"{ticker}: ${mcap/1e9:.2f}B ✓")
            else:
                logger.debug(f"{ticker}: ${mcap/1e9:.2f}B ✗ (out of range)")
        
        logger.info(f"Market cap filter: {len(tickers)} → {len(filtered)}")
        return filtered
    
    # ==================== 2. 섹터 분류 ====================
    
    def classify_sector(self, ticker: str) -> str:
        """종목의 섹터 분류"""
        try:
            data = yf.Ticker(ticker)
            info = data.info
            
            # 공식 섹터
            sector = info.get('sector', '')
            
            # 상세 분류를 위해 industry + 키워드 검색
            industry = info.get('industry', '').lower()
            description = (info.get('longBusinessSummary', '') or '').lower()
            
            keywords = {
                'biotech': ['biotech', 'biopharmaceutical', 'clinical', 'drug', 'therapy', 'pharmaceutical'],
                'space': ['space', 'launch', 'satellite', 'rocket', 'orbital', 'aerospace'],
                'ai_compute': ['gpu', 'data center', 'semiconductor', 'chip', 'cuda', 'infrastructure']
            }
            
            combined_text = f"{industry} {description}"
            
            for sector_name, words in keywords.items():
                if any(word in combined_text for word in words):
                    return sector_name
            
            return 'other'
        
        except Exception as e:
            logger.warning(f"Failed to classify {ticker}: {e}")
            return 'other'
    
    # ==================== 3. 바이너리 촉매 점수화 ====================
    
    def get_biotech_catalysts(self, ticker: str) -> Dict:
        """
        바이오텍 촉매 점수 (0-5)
        
        주요 가중치:
        - 임상 단계 (2상 이상 +2)
        - 데이터 리딩 타이밍 (12개월 이내 +2)
        - 현금 상태 (+1)
        """
        score = 0
        details = {}
        
        try:
            data = yf.Ticker(ticker)
            info = data.info
            
            # 간단한 휴리스틱: 임상 키워드 검색
            description = (info.get('longBusinessSummary', '') or '').lower()
            
            if 'phase 3' in description or '3a' in description or '3b' in description:
                score += 2
                details['clinical_phase'] = 'Phase 3'
            elif 'phase 2' in description or '2a' in description or '2b' in description:
                score += 1
                details['clinical_phase'] = 'Phase 2'
            else:
                details['clinical_phase'] = 'Phase 1 or Early'
            
            # 현금 (balance sheet)
            try:
                balance_sheet = data.quarterly_balance_sheet
                if balance_sheet is not None and not balance_sheet.empty:
                    # 현금 구하기
                    if 'Cash And Cash Equivalents' in balance_sheet.index:
                        cash = balance_sheet.loc['Cash And Cash Equivalents'].iloc[0]
                    else:
                        cash = 0
                    
                    if cash > 100e6:  # $100M 이상
                        score += 1
                        details['cash_position'] = f"${cash/1e6:.0f}M"
                    else:
                        details['cash_position'] = f"${cash/1e6:.0f}M ⚠"
            except:
                pass
            
            details['catalyst_score'] = score
            
        except Exception as e:
            logger.warning(f"Failed biotech analysis for {ticker}: {e}")
        
        return details
    
    def get_space_catalysts(self, ticker: str) -> Dict:
        """
        우주/위성 촉매 점수 (0-5)
        
        주요 가중치:
        - 계약 / 정부 자금 (+3)
        - 발사/배포 일정 있음 (+2)
        """
        score = 0
        details = {}
        
        try:
            data = yf.Ticker(ticker)
            info = data.info
            
            description = (info.get('longBusinessSummary', '') or '').lower()
            
            # 계약 키워드
            if 'contract' in description or 'nasa' in description or 'spacex' in description:
                score += 3
                details['contracts'] = 'Detected'
            
            # 발사 일정
            if 'launch' in description or 'orbital' in description:
                score += 1
                details['launch_timeline'] = 'In progress or planned'
            
            details['catalyst_score'] = score
            
        except Exception as e:
            logger.warning(f"Failed space analysis for {ticker}: {e}")
        
        return details
    
    def get_ai_compute_catalysts(self, ticker: str) -> Dict:
        """
        AI 인프라 촉매 점수 (0-5)
        
        주요 가중치:
        - 수익/계약 ($100M+ ARR) (+3)
        - 첫 프로덕션 시스템 (+2)
        """
        score = 0
        details = {}
        
        try:
            data = yf.Ticker(ticker)
            info = data.info
            
            description = (info.get('longBusinessSummary', '') or '').lower()
            
            # GPU/데이터센터 키워드
            if 'gpu' in description or 'data center' in description or 'infrastructure' in description:
                score += 1
                details['ai_infrastructure'] = 'Confirmed'
                
                # 수익 규모 (매우 간단한 휴리스틱)
                revenue = info.get('totalRevenue', 0)
                if revenue and revenue > 100e6:  # $100M+
                    score += 2
                    details['revenue_scale'] = f"${revenue/1e9:.1f}B"
                else:
                    details['revenue_scale'] = 'Below $100M'
            
            details['catalyst_score'] = score
            
        except Exception as e:
            logger.warning(f"Failed AI compute analysis for {ticker}: {e}")
        
        return details
    
    def score_catalysts(self, ticker: str, sector: str) -> Dict:
        """섹터별 촉매 점수 계산"""
        if sector == 'biotech':
            return self.get_biotech_catalysts(ticker)
        elif sector == 'space':
            return self.get_space_catalysts(ticker)
        elif sector == 'ai_compute':
            return self.get_ai_compute_catalysts(ticker)
        else:
            return {'catalyst_score': 0, 'note': 'Unknown sector'}
    
    # ==================== 4. 최종 필터링 ====================
    
    def run_full_screen(self) -> pd.DataFrame:
        """전체 스크리닝 파이프라인"""
        logger.info("=" * 60)
        logger.info("Starting Microcap 100x Screener")
        logger.info("=" * 60)
        
        # Step 1: 종목 리스트
        tickers = self.get_nasdaq_tickers()
        
        # Step 2: 시총 필터
        filtered_tickers = self.filter_by_market_cap(tickers)
        
        if not filtered_tickers:
            logger.warning("No tickers passed market cap filter")
            return pd.DataFrame()
        
        # Step 3: 데이터 수집 & 분류
        results = []
        
        for ticker in filtered_tickers:
            try:
                mcap = self.get_market_cap(ticker)
                sector = self.classify_sector(ticker)
                catalysts = self.score_catalysts(ticker, sector)
                catalyst_score = catalysts.get('catalyst_score', 0)
                
                # 기본 정보
                data = yf.Ticker(ticker)
                info = data.info
                
                result = {
                    'ticker': ticker,
                    'market_cap': mcap,
                    'sector': sector,
                    'catalyst_score': catalyst_score,
                    'price': info.get('currentPrice', 0),
                    'pe_ratio': info.get('trailingPE', None),
                    'industry': info.get('industry', ''),
                    'details': catalysts
                }
                
                results.append(result)
                
            except Exception as e:
                logger.error(f"Error processing {ticker}: {e}")
                continue
        
        df = pd.DataFrame(results)
        
        # Step 4: 최종 필터 (촉매 점수 >= 1)
        final = df[df['catalyst_score'] >= 1].sort_values('catalyst_score', ascending=False)
        
        logger.info(f"\nResults:")
        logger.info(f"Total candidates: {len(df)}")
        logger.info(f"Qualified (catalyst_score >= 1): {len(final)}")
        logger.info("\n" + final.to_string())
        
        return final
    
    def export_results(self, df: pd.DataFrame, filename: str = 'watchlist.csv'):
        """결과를 CSV로 저장"""
        if df.empty:
            logger.warning("No results to export")
            return
        
        # details 칼럼은 JSON으로 변환
        df['details_json'] = df['details'].apply(json.dumps)
        export_cols = ['ticker', 'market_cap', 'sector', 'catalyst_score', 
                      'price', 'pe_ratio', 'industry', 'details_json']
        
        df[export_cols].to_csv(filename, index=False)
        logger.info(f"Results exported to {filename}")


# ==================== 5. Telegram 알림 ====================

def send_telegram_alert(results_df: pd.DataFrame, token: str = None, chat_id: str = None):
    """
    상위 결과를 Telegram으로 전송
    
    GitHub Secrets에서 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 가져오기
    """
    if token is None or chat_id is None:
        logger.warning("Telegram credentials not provided, skipping notification")
        return
    
    if results_df.empty:
        message = "📊 Microcap Screener: No new candidates qualified"
    else:
        # 상위 5개만
        top = results_df.head(5)
        
        message = "🔍 **Microcap 100x Screener Results**\n\n"
        
        for _, row in top.iterrows():
            message += (
                f"🚀 **{row['ticker']}** (Score: {row['catalyst_score']})\n"
                f"  Market Cap: ${row['market_cap']/1e9:.2f}B\n"
                f"  Sector: {row['sector']}\n"
                f"  Details: {json.dumps(row['details'], ensure_ascii=False)}\n\n"
            )
        
        message += f"\n📈 Total qualified: {len(results_df)}"
    
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }
        requests.post(url, json=payload)
        logger.info("Telegram notification sent")
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")


# ==================== 6. 메인 실행 ====================

if __name__ == '__main__':
    # 스크리너 초기화
    screener = MicrocapScreener(min_mcap=50e6, max_mcap=500e6)
    
    # 스크리닝 실행
    results = screener.run_full_screen()
    
    # 결과 저장
    screener.export_results(results, filename='data/watchlist.csv')
    
    # Telegram 알림 (선택사항)
    # send_telegram_alert(results)
    
    logger.info("\n✓ Screener completed")
