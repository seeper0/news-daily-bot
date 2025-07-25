#!/usr/bin/env python3
import feedparser
from openai import OpenAI
import requests
import os
from datetime import datetime
import time

# API 설정
client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

# RSS 피드 목록
RSS_FEEDS = {
    "스토어 정책": [
        "https://android-developers.googleblog.com/feeds/posts/default",
        "https://developer.apple.com/news/rss/news.rss",
    ],
    "AI 생성": [
        "https://openai.com/blog/rss.xml",
        "https://www.anthropic.com/blog/rss.xml",
        "https://huggingface.co/blog/feed.xml",
    ],
    "3D/언리얼": [
        "https://www.unrealengine.com/en-US/blog/feed",
        "https://80.lv/feed/",
    ]
}

def fetch_feeds():
    """RSS 피드에서 최신 기사 수집"""
    all_articles = {}
    
    for category, feeds in RSS_FEEDS.items():
        articles = []
        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)
                # 최근 24시간 이내 기사만
                for entry in feed.entries[:5]:  # 피드당 최대 5개
                    published = entry.get('published_parsed', None)
                    if published:
                        # 24시간 이내 체크 (간단히 하기 위해 생략 가능)
                        pass
                    
                    articles.append({
                        'title': entry.get('title', 'No title'),
                        'link': entry.get('link', ''),
                        'summary': entry.get('summary', '')[:200] + '...' if entry.get('summary') else '',
                        'source': feed.feed.get('title', feed_url)
                    })
            except Exception as e:
                print(f"Error fetching {feed_url}: {e}")
                
        all_articles[category] = articles
    
    return all_articles

def summarize_with_gpt(articles):
    """GPT-4로 한국어 요약 생성"""
    # 입력 텍스트 준비
    content = "오늘의 AI/게임 개발 동향을 한국어로 요약해주세요:\n\n"
    
    for category, items in articles.items():
        if items:
            content += f"\n【{category}】\n"
            for item in items:
                content += f"- {item['title']} (출처: {item['source']})\n"
                if item['summary']:
                    content += f"  요약: {item['summary']}\n"
    
    # GPT API 호출
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "당신은 AI와 게임 개발 동향을 전문적으로 요약하는 어시스턴트입니다. 한국어로 간결하고 명확하게 요약해주세요."},
                {"role": "user", "content": content}
            ],
            max_tokens=1500,
            temperature=0.7
        )
        
        summary = response.choices[0].message.content
        
        # 포맷팅
        today = datetime.now().strftime("%Y년 %m월 %d일")
        final_message = f"📅 {today} AI/게임 동향\n\n{summary}\n\n"
        
        # 원문 링크 추가
        final_message += "\n📎 주요 링크:\n"
        for category, items in articles.items():
            if items and len(items) > 0:
                final_message += f"\n{category}:\n"
                for item in items[:2]:  # 카테고리당 상위 2개 링크만
                    final_message += f"• {item['title']}\n  {item['link']}\n"
        
        return final_message
        
    except Exception as e:
        return f"❌ 요약 생성 중 오류 발생: {str(e)}"

def send_telegram_message(message):
    """텔레그램으로 메시지 전송"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # 텔레그램 메시지 길이 제한 (4096자)
    if len(message) > 4000:
        message = message[:3997] + "..."
    
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, json=data)
        response.raise_for_status()
        print("✅ 텔레그램 메시지 전송 성공")
        return True
    except Exception as e:
        print(f"❌ 텔레그램 전송 실패: {str(e)}")
        return False

def main():
    """메인 실행 함수"""
    print("🚀 뉴스 수집 시작...")
    
    # 1. RSS 피드 수집
    articles = fetch_feeds()
    
    if not any(articles.values()):
        send_telegram_message("📭 오늘은 새로운 뉴스가 없습니다.")
        return
    
    print(f"📰 수집된 기사 수: {sum(len(items) for items in articles.values())}")
    
    # 2. GPT로 요약
    print("🤖 AI 요약 생성 중...")
    summary = summarize_with_gpt(articles)
    
    # 3. 텔레그램 전송
    print("📤 텔레그램 전송 중...")
    send_telegram_message(summary)
    
    print("✅ 완료!")

if __name__ == "__main__":
    main()
