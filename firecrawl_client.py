#!/usr/bin/env python3
import asyncio
import openpyxl
import pandas as pd
import json
import os
from pathlib import Path
from datetime import datetime
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class FirecrawlMCPClient:
    def __init__(self, server_path=None):
        """
        Initialize the Firecrawl MCP client
        
        Args:
            server_path: Path to the Firecrawl MCP server JS file
                        If None, will try to find it automatically
        """
        if server_path is None:
            # Try to find the server automatically
            possible_paths = [
                "./firecrawl/apps/mcp-server/dist/index.js",
                "../firecrawl/apps/mcp-server/dist/index.js",
                "./dist/index.js"
            ]
            
            for path in possible_paths:
                if Path(path).exists():
                    server_path = path
                    break
            
            if server_path is None:
                raise FileNotFoundError(
                    "Could not find Firecrawl MCP server. Please provide the path manually."
                )
        
        self.server_params = StdioServerParameters(
            command="node",
            args=[server_path],
            env=dict(os.environ)  # Pass current environment variables
        )
    
    async def connect(self):
        """Establish connection to the MCP server"""
        self.stdio_client = stdio_client(self.server_params)
        self.read, self.write = await self.stdio_client.__aenter__()
        self.session = ClientSession(self.read, self.write)
        await self.session.__aenter__()
        await self.session.initialize()
        print("✅ Connected to Firecrawl MCP server")
    
    async def disconnect(self):
        """Close the connection"""
        if hasattr(self, 'session'):
            await self.session.__aexit__(None, None, None)
        if hasattr(self, 'stdio_client'):
            await self.stdio_client.__aexit__(None, None, None)
        print("❌ Disconnected from Firecrawl MCP server")
    
    async def list_tools(self):
        """List all available tools"""
        try:
            tools = await self.session.list_tools()
            print("\n📋 Available Tools:")
            for tool in tools.tools:
                print(f"  • {tool.name}: {tool.description}")
            return tools.tools
        except Exception as e:
            print(f"❌ Error listing tools: {e}")
            return []
    
    async def list_resources(self):
        """List all available resources"""
        try:
            resources = await self.session.list_resources()
            print("\n📂 Available Resources:")
            for resource in resources.resources:
                print(f"  • {resource.uri}: {resource.name}")
            return resources.resources
        except Exception as e:
            if "Method not found" in str(e):
                print("\n📂 Resources: Not supported by this MCP server")
                return []
            else:
                print(f"❌ Error listing resources: {e}")
                return []
    
    def save_to_file(self, data, filename=None, output_dir="output"):
        """
        Save data to a file
        
        Args:
            data: The data to save
            filename: Optional filename. If None, will generate based on timestamp
            output_dir: Directory to save files in
        """
        # Create output directory if it doesn't exist
        Path(output_dir).mkdir(exist_ok=True)
        
        # Generate filename if not provided
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"firecrawl_result_{timestamp}"
        
        # Save as JSON
        json_path = Path(output_dir) / f"{filename}.json"
        try:
            # Convert result to serializable format
            if hasattr(data, '__dict__'):
                serializable_data = self._make_serializable(data)
            else:
                serializable_data = data
                
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(serializable_data, f, indent=2, ensure_ascii=False)
            print(f"💾 Saved JSON to: {json_path}")
        except Exception as e:
            print(f"❌ Error saving JSON: {e}")
        
        # If the data contains text content, also save as markdown/text
        text_content = self._extract_text_content(data)
        if text_content:
            md_path = Path(output_dir) / f"{filename}.md"
            try:
                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(text_content)
                print(f"📝 Saved Markdown to: {md_path}")
            except Exception as e:
                print(f"❌ Error saving Markdown: {e}")
        
        return json_path, md_path if text_content else None
    
    def _make_serializable(self, obj):
        """Convert object to JSON-serializable format"""
        if hasattr(obj, '__dict__'):
            result = {}
            for key, value in obj.__dict__.items():
                if key.startswith('_'):
                    continue
                result[key] = self._make_serializable(value)
            return result
        elif hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes)):
            return [self._make_serializable(item) for item in obj]
        else:
            return obj
    
    def save_to_table(self, result, filename: str, format: str = "excel"):
        if not hasattr(result, 'content') or not result.content:
            print("⚠️ No content to save.")
            return
        
        try:
            data = [item.text for item in result.content]
            df = pd.DataFrame(data)

            if format == "csv":
                df.to_csv(f"{filename}.csv", index=False)
            elif format == "excel":
                df.to_excel(f"{filename}.xlsx", index=False, engine='openpyxl')
            else:
                print(f"⚠️ Unsupported format: {format}")
                return
            
            print(f"✅ Saved structured table to {filename}.{format}")
        except Exception as e:
            print(f"❌ Failed to save table: {e}")

    def _extract_text_content(self, data):
        """Extract text content from the result for markdown saving"""
        text_parts = []
        
        def extract_text(obj, level=0):
            if hasattr(obj, 'text'):
                text_parts.append(obj.text)
            elif hasattr(obj, 'content'):
                if isinstance(obj.content, str):
                    text_parts.append(obj.content)
                elif hasattr(obj.content, '__iter__'):
                    for item in obj.content:
                        extract_text(item, level + 1)
            elif hasattr(obj, '__iter__') and not isinstance(obj, str):
                for item in obj:
                    extract_text(item, level + 1)
            elif isinstance(obj, str):
                text_parts.append(obj)
        
        extract_text(data)
        return '\n\n'.join(text_parts) if text_parts else None
    
    async def crawl_url(self, url, save_to_file=False, filename=None, **kwargs):
        """
        Crawl a single URL
        
        Args:
            url: The URL to crawl
            save_to_file: Whether to save results to file
            filename: Optional filename for saving
            **kwargs: Additional parameters for crawling
        """
        try:
            result = await self.session.call_tool(
                "crawl_url", 
                {
                    "url": url,
                    **kwargs
                }
            )
            print(f"✅ Successfully crawled: {url}")
            
            if save_to_file:
                if filename is None:
                    # Generate filename from URL
                    filename = url.replace("https://", "").replace("http://", "").replace("/", "_").replace(".", "_")
                    filename = f"crawl_{filename}"
                self.save_to_file(result, filename)
            
            return result
        except Exception as e:
            print(f"❌ Error crawling {url}: {e}")
            return None
    
    async def firecrawl_scrape(self, url, save_to_file=False, filename=None, **kwargs):
        """
        Scrape a single URL
        
        Args:
            url: The URL to scrape
            save_to_file: Whether to save results to file
            filename: Optional filename for saving
            **kwargs: Additional parameters for scraping
        """
        try:
            # Debug: Print the exact parameters being sent
            params = {"url": url, **kwargs}
            print(f"🔍 Scraping with params: {params}")
            
            result = await self.session.call_tool("firecrawl_scrape", params)
            
            # Debug: Print raw result structure
            print(f"📊 Raw result type: {type(result)}")
            print(f"📊 Raw result: {result}")
            
            # Check if result has expected structure
            if hasattr(result, 'content'):
                print(f"📊 Result.content type: {type(result.content)}")
                if isinstance(result.content, list):
                    print(f"📊 Content list length: {len(result.content)}")
                    for i, item in enumerate(result.content[:3]):  # Show first 3 items
                        print(f"📊 Content[{i}] type: {type(item)}")
                        print(f"📊 Content[{i}]: {item}")
                else:
                    print(f"📊 Content: {result.content}")
            
            # Check for different possible response structures
            if hasattr(result, 'data'):
                print(f"📊 Result.data: {result.data}")
            if hasattr(result, 'results'):
                print(f"📊 Result.results: {result.results}")
            if hasattr(result, 'text'):
                print(f"📊 Result.text: {result.text[:500]}...")
            
            print(f"✅ Successfully scraped: {url}")
            
            if save_to_file:
                if filename is None:
                    # Generate filename from URL
                    filename = url.replace("https://", "").replace("http://", "").replace("/", "_").replace(".", "_")
                    filename = f"scrape_{filename}"
                self.save_to_file(result, filename)
            
            return result
        except Exception as e:
            print(f"❌ Error scraping {url}: {e}")
            print(f"❌ Exception type: {type(e)}")
            import traceback
            traceback.print_exc()
            return None

    async def firecrawl_extract(self, urls, prompt, system_prompt, schema, 
                            allow_external_links=False, enable_web_search=False, 
                            include_subdomains=False, save_to_file=False,
                            save_as_excel=False, filename=None):
        try:
            params = {
                "urls": urls,
                "prompt": prompt,
                "systemPrompt": system_prompt,
                "schema": schema,
                "allowExternalLinks": allow_external_links,
                "enableWebSearch": enable_web_search,
                "includeSubdomains": include_subdomains
            }
            print(f"🧠 Extracting with params: {json.dumps(params, indent=2)}")
            result = await self.session.call_tool("firecrawl_extract", params)

            if save_as_excel:
                self.save_to_table(result, filename, format="excel")

            if save_to_file:
                if not filename:
                    filename = f"extract_{datetime.now().isoformat().replace(':', '_')}.json"
                filepath = Path(filename).resolve()
                self.save_to_file(result, str(filepath))
                print(f"✅ Result saved to: {filepath}")

            return result
        except Exception as e:
            print(f"❌ Error during extraction: {e}")
            import traceback
            traceback.print_exc()
            return None
            
    async def search(self, query, save_to_file=False, filename=None, **kwargs):
        """
        Search using Firecrawl
        
        Args:
            query: Search query
            save_to_file: Whether to save results to file
            filename: Optional filename for saving
            **kwargs: Additional search parameters
        """
        try:
            result = await self.session.call_tool(
                "search",
                {
                    "query": query,
                    **kwargs
                }
            )
            print(f"✅ Search completed for: {query}")
            
            if save_to_file:
                if filename is None:
                    filename = f"search_{query.replace(' ', '_')}"
                self.save_to_file(result, filename)
            
            return result
        except Exception as e:
            print(f"❌ Error searching for '{query}': {e}")
            return None

async def debug_main():
    """Debug version to understand the response structure"""
    
    if not os.getenv('FIRECRAWL_API_KEY'):
        print("⚠️  Warning: FIRECRAWL_API_KEY environment variable not set")
        print("   Set it with: export FIRECRAWL_API_KEY='your_api_key_here'")
        return
    
    try:
        client = FirecrawlMCPClient()
        await client.connect()
        
        # First, let's see what tools are available
        print("\n🔧 Available tools:")
        tools = await client.list_tools()
        
        # Try a simple URL first
        print("\n🔍 Testing with a simple URL...")
        result = await client.firecrawl_scrape("https://example.com")
        
        # Try the Anthropic URL with different parameters
        print("\n🔍 Testing Anthropic URL with minimal params...")
        result = await client.firecrawl_scrape(
            "https://en.volleyballworld.com/volleyball/competitions/volleyball-nations-league/standings/men/"
        )
        
        print("\n🔍 Testing Anthropic URL with formats specified...")
        result = await client.firecrawl_scrape(
            "https://en.volleyballworld.com/volleyball/competitions/volleyball-nations-league/standings/men/",
            formats=["markdown"]
        )
        
        print("\n🔍 Testing Anthropic URL with different format...")
        result = await client.firecrawl_scrape(
            "https://en.volleyballworld.com/volleyball/competitions/volleyball-nations-league/standings/men/",
            format="markdown"  # singular instead of plural
        )
        
    except Exception as e:
        print(f"❌ Error in debug_main: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if 'client' in locals():
            await client.disconnect()

async def main():
    """Example usage of the Firecrawl MCP client with file saving"""
    
    # Check if API key is set
    if not os.getenv('FIRECRAWL_API_KEY'):
        print("⚠️  Warning: FIRECRAWL_API_KEY environment variable not set")
        print("   Set it with: export FIRECRAWL_API_KEY='your_api_key_here'")
    
    # Initialize client
    try:
        client = FirecrawlMCPClient()
        await client.connect()
        
        # List available tools and resources
        await client.list_resources()
        
        # # Example: Scrape a URL and save to file
        # print("\n🔍 Scraping and saving to file...")
        # result = await client.firecrawl_scrape(
        #     "https://www.tripadvisor.com.ph/Restaurant_Review-g298450-d1147837-Reviews-Italianni_s-Makati_Metro_Manila_Luzon.html",
        #     formats=["markdown", "html"],
        #     save_to_file=True,
        #     filename="sample_scraped_data"
        # )
        
        # if result:
        #     print("\n📄 Scraping Result Preview:")
        #     print(f"Result type: {type(result)}")
        #     if hasattr(result, 'content'):
        #         print(f"Content type: {type(result.content)}")
        #         if hasattr(result.content, '__iter__') and not isinstance(result.content, str):
        #             # Handle list of content items
        #             for i, item in enumerate(result.content):
        #                 print(f"  Item {i}: {type(item)}")
        #                 if hasattr(item, 'text'):
        #                     print(f"    Text preview: {item.text[:200]}...")
        #                 elif hasattr(item, 'content'):
        #                     print(f"    Content preview: {str(item.content)[:200]}...")
        #                 else:
        #                     print(f"    Raw preview: {str(item)[:200]}...")
        #         else:
        #             # Handle single content item
        #             if hasattr(result.content, 'text'):
        #                 print(f"Text preview: {result.content.text[:300]}...")
        #             else:
        #                 print(f"Content preview: {str(result.content)[:300]}...")
        #     else:
        #         print(f"Raw result preview: {str(result)[:300]}...")
        
        # Example: Use firecrawl_extract
        print("\n🧠 Extracting structured data from product/review page...")
        extraction_result = await client.firecrawl_extract(
            urls=["https://www.tripadvisor.com.ph/Restaurant_Review-g298450-d1147837-Reviews-Italianni_s-Makati_Metro_Manila_Luzon.html"],
            prompt="Extract user reviews",
            system_prompt="You are a helpful assistant extracting restaurant review information.",
            schema={
                "type": "object",
                "properties": {
                    "name": { "type": "string" },
                    "average_rating": { "type": "number" },
                    "reviews": {
                        "type": "array",
                        "items": { "type": "string" }
                    }
                },
                "required": ["reviews"]
            },
             save_as_excel=True,
            filename="structured_data"
        )
        # # Example: Search and save results
        # print("\n🔎 Searching for 'Python tutorials' and saving results...")
        # search_result = await client.search(
        #     "Python tutorials",
        #     limit=3,
        #     save_to_file=True,
        #     filename="python_tutorials_search"
        # )
        
        # if search_result:
        #     print("\n🔍 Search Results Preview:")
        #     print(f"Result type: {type(search_result)}")
        #     if hasattr(search_result, 'content'):
        #         print(f"Content preview: {str(search_result.content)[:300]}...")
        #     else:
        #         print(f"Raw result preview: {str(search_result)[:300]}...")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        # Clean up
        if 'client' in locals():
            await client.disconnect()

def interactive_mode():
    """Interactive mode for testing different operations with file saving options"""
    
    async def interactive():
        client = FirecrawlMCPClient()
        await client.connect()
        
        try:
            while True:
                print("\n" + "="*50)
                print("🔥 Firecrawl MCP Interactive Client")
                print("="*50)
                print("1. List tools")
                print("2. List resources") 
                print("3. Scrape URL")
                print("4. Crawl URL")
                print("5. Search")
                print("6. Extract")
                print("7. Exit")
                
                choice = input("\nEnter your choice (1-7): ").strip()
                
                if choice == "1":
                    await client.list_tools()
                
                elif choice == "2":
                    await client.list_resources()
                
                elif choice == "3":
                    url = input("Enter URL to scrape: ").strip()
                    if url:
                        save_choice = input("Save to file? (y/n): ").strip().lower()
                        save_to_file = save_choice == 'y'
                        filename = None
                        if save_to_file:
                            filename = input("Enter filename (or press Enter for auto-generated): ").strip()
                            if not filename:
                                filename = None
                        
                        result = await client.firecrawl_scrape(url, save_to_file=save_to_file, filename=filename)
                        if result and not save_to_file:
                            print(f"\n📄 Scrape result preview:")
                            # Show preview as before...
                            print(f"Result type: {type(result)}")
                            if hasattr(result, 'content'):
                                if hasattr(result.content, '__iter__') and not isinstance(result.content, str):
                                    for i, item in enumerate(result.content):
                                        print(f"  Content {i+1}:")
                                        if hasattr(item, 'text'):
                                            preview = item.text[:500]
                                            print(f"    {preview}{'...' if len(item.text) > 500 else ''}")
                                        else:
                                            print(f"    {str(item)[:500]}...")
                                else:
                                    if hasattr(result.content, 'text'):
                                        preview = result.content.text[:1000]
                                        print(f"Text: {preview}{'...' if len(result.content.text) > 1000 else ''}")
                                    else:
                                        print(f"Content: {str(result.content)[:1000]}...")
                            else:
                                print(f"Raw result: {str(result)[:1000]}...")
                
                elif choice == "4":
                    url = input("Enter URL to crawl: ").strip()
                    if url:
                        save_choice = input("Save to file? (y/n): ").strip().lower()
                        save_to_file = save_choice == 'y'
                        filename = None
                        if save_to_file:
                            filename = input("Enter filename (or press Enter for auto-generated): ").strip()
                            if not filename:
                                filename = None
                        
                        result = await client.crawl_url(url, save_to_file=save_to_file, filename=filename)
                        if result and not save_to_file:
                            print(f"\n🕷️ Crawl result preview:")
                            print(f"Result type: {type(result)}")
                            if hasattr(result, 'content'):
                                if hasattr(result.content, '__iter__') and not isinstance(result.content, str):
                                    for i, item in enumerate(result.content):
                                        print(f"  Content {i+1}:")
                                        if hasattr(item, 'text'):
                                            preview = item.text[:500]
                                            print(f"    {preview}{'...' if len(item.text) > 500 else ''}")
                                        else:
                                            print(f"    {str(item)[:500]}...")
                                else:
                                    if hasattr(result.content, 'text'):
                                        preview = result.content.text[:1000]
                                        print(f"Text: {preview}{'...' if len(result.content.text) > 1000 else ''}")
                                    else:
                                        print(f"Content: {str(result.content)[:1000]}...")
                            else:
                                print(f"Raw result: {str(result)[:1000]}...")
                
                elif choice == "5":
                    query = input("Enter search query: ").strip()
                    if query:
                        save_choice = input("Save to file? (y/n): ").strip().lower()
                        save_to_file = save_choice == 'y'
                        filename = None
                        if save_to_file:
                            filename = input("Enter filename (or press Enter for auto-generated): ").strip()
                            if not filename:
                                filename = None
                        
                        result = await client.search(query, save_to_file=save_to_file, filename=filename)
                        if result and not save_to_file:
                            print(f"\n🔍 Search results preview:")
                            print(f"Result type: {type(result)}")
                            if hasattr(result, 'content'):
                                if hasattr(result.content, '__iter__') and not isinstance(result.content, str):
                                    for i, item in enumerate(result.content):
                                        print(f"  Result {i+1}:")
                                        if hasattr(item, 'text'):
                                            preview = item.text[:500]
                                            print(f"    {preview}{'...' if len(item.text) > 500 else ''}")
                                        else:
                                            print(f"    {str(item)[:500]}...")
                                else:
                                    if hasattr(result.content, 'text'):
                                        preview = result.content.text[:1000]
                                        print(f"Text: {preview}{'...' if len(result.content.text) > 1000 else ''}")
                                    else:
                                        print(f"Content: {str(result.content)[:1000]}...")
                            else:
                                print(f"Raw result: {str(result)[:1000]}...")
                elif choice == "6":
                    # NEW Extract functionality
                    urls_input = input("Enter URL(s) to extract from (separate multiple URLs with commas): ").strip()
                    if urls_input:
                        urls = [url.strip() for url in urls_input.split(',')]
                        prompt = input("Enter extraction prompt: ").strip()
                        if prompt:
                            print("\nOptional parameters:")
                            system_prompt = input("System prompt (optional): ").strip()
                            
                            # Ask about schema
                            use_schema = input("Use JSON schema? (y/n): ").strip().lower() == 'y'
                            schema = None
                            if use_schema:
                                print("Enter JSON schema (or press Enter for a simple product example):")
                                schema_input = input().strip()
                                if not schema_input:
                                    schema = {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "price": {"type": "number"},
                                            "description": {"type": "string"}
                                        },
                                        "required": ["name"]
                                    }
                                    print("Using default product schema")
                                else:
                                    try:
                                        schema = json.loads(schema_input)
                                    except json.JSONDecodeError:
                                        print("Invalid JSON schema, proceeding without schema")
                            
                            save_choice = input("Save to file? (y/n): ").strip().lower()
                            save_to_file = save_choice == 'y'
                            filename = None
                            if save_to_file:
                                filename = input("Enter filename (or press Enter for auto-generated): ").strip()
                                if not filename:
                                    filename = None
                            save_as_excel = False
                            if save_to_file:
                                excel_choice = input("Save as Excel? (y/n): ").strip().lower()
                                save_as_excel = excel_choice == 'y'
                            # Final API call
                            result = await client.firecrawl_extract(
                                urls=urls,
                                prompt=prompt,
                                schema=schema,
                                system_prompt=system_prompt or None,
                                save_to_file=save_to_file,
                                filename=filename
                            )

                            if result and not save_to_file:
                                print(f"\n🧠 Extract result preview:")
                                print(f"Result type: {type(result)}")
                                if hasattr(result, 'content'):
                                    if hasattr(result.content, '__iter__') and not isinstance(result.content, str):
                                        for i, item in enumerate(result.content):
                                            print(f"  Extracted {i+1}:")
                                            if hasattr(item, 'text'):
                                                preview = str(item.text)[:500]
                                                print(f"    {preview}{'...' if len(str(item.text)) > 500 else ''}")
                                            else:
                                                print(f"    {str(item)[:500]}...")
                                    else:
                                        print(f"Content: {str(result.content)[:1000]}...")
                                else:
                                    print(f"Raw result: {str(result)[:1000]}...")
                
                elif choice == "7":
                    break
                
                else:
                    print("Invalid choice. Please try again.")
        
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
        
        finally:
            await client.disconnect()
    
    # Run the interactive session
    asyncio.run(interactive())

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--interactive":
            interactive_mode()
        elif sys.argv[1] == "--debug":
            asyncio.run(debug_main())
        else:
            asyncio.run(main())
    else:
        asyncio.run(main())