#!/usr/bin/env python3
"""
Telegram Notifier for Microcap Screener
스크리닝 결과를 Telegram 채널/봇으로 전송

사용 방법:
  1. Telegram에서 BotFather로부터 봇 토큰 생성
  2. GitHub Secrets에 저장:
     - TELEGRAM_BOT_TOKEN
     - TELEGRAM_CHAT_ID
  3. 이 스크립트가 자동으로 실행됨
"""

import os
import json
import pandas as pd
import requests
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token: str = None, chat_id: str = None):
        """
        Args:
            token: Telegram Bot Token (환경변수 TELEGRAM_BOT_TOKEN)
            chat_id: Target Chat ID (환경변수 TELEGRAM_CHAT_ID)
        """
        self.token = token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        
        if not self.token or not self.chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID required")
        
        self.api_url = f"https://api.telegram.org/bot{self.token}"
    
    def send_message(self, text: str, parse_mode: str = 'HTML') -> bool:
        """메시지 전송"""
        try:
            url = f"{self.api_url}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True
            }
            
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            logger.info("Message sent successfully")
            return True
        
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False
    
    def format_results(self, df: pd.DataFrame, top_n: int = 10) -> str:
        """
        DataFrame을 Telegram 친화적 포맷으로 변환
        """
        if df.empty:
            return "📊 No new candidates qualified today"
        
        top_df = df.head(top_n)
        
        # 헤더
        message = (
            "<b>🔍 Microcap 100x Screener Results</b>\n"
            f"<i>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</i>\n"
            f"<i>Total qualified: {len(df)}</i>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        
        # 각 종목별 상세 정보
        for idx, (_, row) in enumerate(top_df.iterrows(), 1):
            ticker = row['ticker']
            mcap = row['market_cap']
            score = row['catalyst_score']
            sector = row['sector'].upper()
            price = row.get('price', 'N/A')
            
            # 점수별 이모지
            score_emoji = {
                5: '🌟🌟🌟',
                4: '🌟🌟',
                3: '🌟',
                2: '⭐',
                1: '•'
            }.get(score, '')
            
            sector_emoji = {
                'biotech': '💊',
                'space': '🚀',
                'ai_compute': '⚡',
                'other': '❓'
            }.get(sector.lower(), '?')
            
            message += (
                f"<b>#{idx}. {ticker}</b> {score_emoji}\n"
                f"  {sector_emoji} <code>{sector}</code>\n"
                f"  💰 Market Cap: ${mcap/1e9:.2f}B\n"
                f"  📈 Price: ${price:.2f}\n"
            )
            
            # 상세 정보 (있으면)
            details = row.get('details', {})
            if isinstance(details, str):
                try:
                    details = json.loads(details)
                except:
                    pass
            
            if details:
                for key, value in details.items():
                    if key != 'catalyst_score':
                        clean_key = key.replace('_', ' ').title()
                        message += f"  • {clean_key}: {value}\n"
            
            message += "\n"
        
        # 푸터
        message += (
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<i>⚠️ 투자 자문이 아닙니다. 철저한 실사(DD) 필수</i>\n"
            "<i>30일 이상 보유 전제. 손절선: -25%</i>"
        )
        
        return message
    
    def send_daily_report(self, csv_path: str = 'data/watchlist.csv') -> bool:
        """
        스크리닝 결과 CSV를 읽어서 Telegram으로 전송
        """
        try:
            # CSV 읽기
            df = pd.read_csv(csv_path)
            
            if df.empty:
                text = "📊 Microcap Screener: No results today"
            else:
                text = self.format_results(df, top_n=10)
            
            return self.send_message(text)
        
        except FileNotFoundError:
            logger.error(f"CSV file not found: {csv_path}")
            return False
        except Exception as e:
            logger.error(f"Failed to process results: {e}")
            return False
    
    def send_alert_price_change(self, ticker: str, old_price: float, new_price: float, change_pct: float):
        """가격 변동 알림"""
        direction = "📈" if change_pct > 0 else "📉"
        message = (
            f"{direction} <b>Price Alert: {ticker}</b>\n"
            f"  Old: ${old_price:.2f}\n"
            f"  New: ${new_price:.2f}\n"
            f"  Change: {change_pct:+.2f}%"
        )
        return self.send_message(message)
    
    def send_alert_clinical_data(self, ticker: str, trial_name: str, status: str):
        """임상 데이터 알림"""
        message = (
            f"💊 <b>Clinical Data Alert: {ticker}</b>\n"
            f"  Trial: {trial_name}\n"
            f"  Status: {status}\n"
            f"  <i>Check official PR for details</i>"
        )
        return self.send_message(message)
    
    def send_alert_contract(self, ticker: str, customer: str, value: str):
        """계약 공시 알림"""
        message = (
            f"📋 <b>Contract Alert: {ticker}</b>\n"
            f"  Customer: {customer}\n"
            f"  Value: {value}\n"
            f"  <i>Check SEC filing (8-K) for full details</i>"
        )
        return self.send_message(message)


def main():
    """메인 실행"""
    logger.info("Starting Telegram Notifier...")
    
    try:
        notifier = TelegramNotifier()
        
        # 스크리닝 결과 전송
        success = notifier.send_daily_report('data/watchlist.csv')
        
        if success:
            logger.info("✓ Notification sent successfully")
        else:
            logger.error("✗ Failed to send notification")
    
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.info("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")


if __name__ == '__main__':
    main()
