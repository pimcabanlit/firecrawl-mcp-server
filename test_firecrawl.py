#!/usr/bin/env python3
"""
Simple test script for Firecrawl MCP
"""

import asyncio
import os
from firecrawl_client import FirecrawlMCPClient

async def quick_test():
    """Quick test of basic functionality"""
    
    print("🔥 Starting Firecrawl MCP Test")
    print("-" * 40)
    
    # Check API key
    api_key = os.getenv('FIRECRAWL_API_KEY')
    if not api_key:
        print("❌ FIRECRAWL_API_KEY not found!")
        print("Set it with: export FIRECRAWL_API_KEY='your_key_here'")
        return
    
    print(f"✅ API Key found: {api_key[:8]}...")
    
    try:
        # Initialize and connect
        client = FirecrawlMCPClient()
        await client.connect()
        
        # Test 1: List available capabilities
        print("\n🧪 Test 1: Listing tools...")
        tools = await client.list_tools()
        
        # Test 2: Simple scrape
        print("\n🧪 Test 2: Scraping a simple webpage...")
        result = await client.firecrawl_scrape("https://en.volleyballworld.com/volleyball/competitions/volleyball-nations-league/standings/men/")
        
        if result:
            print("✅ Scrape successful!")
            print(f"Result type: {type(result)}")
            print(f"Content type: {type(result.content)}")
            
            # Handle different content types
            if hasattr(result, 'content'):
                if hasattr(result.content, '__iter__') and not isinstance(result.content, str):
                    # Handle list of content items
                    print(f"Number of content items: {len(result.content)}")
                    for i, item in enumerate(result.content[:2]):  # Show first 2 items
                        print(f"  Item {i+1}: {type(item)}")
                        if hasattr(item, 'text'):
                            print(f"    Text preview: {item.text[:200]}...")
                        elif hasattr(item, 'content'):
                            print(f"    Content preview: {str(item.content)[:200]}...")
                        else:
                            print(f"    Raw preview: {str(item)[:200]}...")
                else:
                    # Handle single content item
                    if hasattr(result.content, 'text'):
                        print(f"Text content: {result.content.text[:300]}...")
                    else:
                        print(f"Content: {str(result.content)[:300]}...")
            else:
                print(f"Raw result: {str(result)[:300]}...")
        else:
            print("❌ Scrape failed")
        
        # Test 3: Try to scrape a news site (if tools support it)
        print("\n🧪 Test 3: Scraping a real website...")
        news_result = await client.firecrawl_scrape(
            "https://news.ycombinator.com",
            formats=["markdown"]
        )
        
        if news_result:
            print("✅ News site scrape successful!")
            if hasattr(news_result, 'content'):
                if hasattr(news_result.content, '__iter__') and not isinstance(news_result.content, str):
                    print(f"Got {len(news_result.content)} content items")
                    if len(news_result.content) > 0:
                        first_item = news_result.content[0]
                        if hasattr(first_item, 'text'):
                            print(f"First item preview: {first_item.text[:200]}...")
                else:
                    if hasattr(news_result.content, 'text'):
                        print(f"Content preview: {news_result.content.text[:200]}...")
                    else:
                        print(f"Content preview: {str(news_result.content)[:200]}...")
        else:
            print("❌ News site scrape failed")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if 'client' in locals():
            await client.disconnect()
    
    print("\n🏁 Test completed!")

if __name__ == "__main__":
    asyncio.run(quick_test())