"""
Tavily Search utility for Teams AI Agent
Provides web search functionality using Tavily API
"""

import json
from typing import List, Dict, Any, Optional
from tavily import TavilyClient
from agent_logger import get_agent_logger
from config import Config

# Initialize colored logging
logger, log_blue, log_green, log_yellow, log_red, log_cyan = get_agent_logger("TavilySearch")

class TavilySearchTool:
    """Tavily search tool for web searches"""
    
    def __init__(self, api_key: Optional[str] = None, max_results: int = 3):
        """
        Initialize Tavily search tool
        
        Args:
            api_key: Tavily API key (optional, will use config if not provided)
            max_results: Maximum number of search results to return
        """
        self.api_key = api_key or Config.TAVILY_API_KEY
        self.max_results = max_results
        self.client = None
        
        if self.api_key:
            try:
                self.client = TavilyClient(api_key=self.api_key)
                log_green("✅ Tavily search client initialized successfully")
            except Exception as e:
                log_red(f"❌ Failed to initialize Tavily client: {str(e)}")
                self.client = None
        else:
            log_yellow("⚠️ Tavily API key not provided - search functionality disabled")
    
    def is_available(self) -> bool:
        """Check if Tavily search is available"""
        return self.client is not None
    
    def search(self, query: str, max_results: Optional[int] = None) -> Dict[str, Any]:
        """
        Perform a web search using Tavily
        
        Args:
            query: Search query string
            max_results: Override default max results for this search
            
        Returns:
            Dictionary containing search results and metadata
        """
        log_cyan(f"🔍 Performing Tavily search: '{query}'")
        
        if not self.is_available():
            log_red("❌ Tavily search not available")
            return {
                "success": False,
                "error": "Tavily search not configured or API key missing",
                "results": []
            }
        
        try:
            # Use provided max_results or default
            results_limit = max_results or self.max_results
            log_blue(f"📊 Searching with max results: {results_limit}")
            
            # Perform the search
            response = self.client.search(
                query=query,
                max_results=results_limit,
                include_answer=True,
                include_raw_content=False
            )
            
            log_green(f"✅ Search completed successfully")
            log_blue(f"📄 Found {len(response.get('results', []))} results")
            
            # Format the response
            formatted_results = []
            for idx, result in enumerate(response.get('results', []), 1):
                formatted_result = {
                    "position": idx,
                    "title": result.get('title', 'No title'),
                    "url": result.get('url', ''),
                    "content": result.get('content', ''),
                    "score": result.get('score', 0)
                }
                formatted_results.append(formatted_result)
                log_blue(f"  {idx}. {formatted_result['title'][:60]}...")
            
            return {
                "success": True,
                "query": query,
                "answer": response.get('answer', ''),
                "results": formatted_results,
                "total_results": len(formatted_results)
            }
            
        except Exception as e:
            log_red(f"❌ Tavily search error: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "query": query,
                "results": []
            }
    
    def search_summary(self, query: str) -> str:
        """
        Get a concise summary of search results
        
        Args:
            query: Search query string
            
        Returns:
            Formatted string summary of search results
        """
        search_result = self.search(query)
        
        if not search_result["success"]:
            return f"Search failed: {search_result.get('error', 'Unknown error')}"
        
        # Build summary
        summary_parts = []
        
        # Add answer if available
        if search_result.get("answer"):
            summary_parts.append(f"**Answer:** {search_result['answer']}")
        
        # Add top results
        if search_result["results"]:
            summary_parts.append("\n**Top Results:**")
            for result in search_result["results"][:3]:  # Top 3 results
                summary_parts.append(
                    f"• **{result['title']}**\n  {result['content'][:150]}...\n  Source: {result['url']}"
                )
        
        if summary_parts:
            return "\n\n".join(summary_parts)
        else:
            return f"No results found for: {query}"
    
    def get_search_suggestions(self, query: str) -> List[str]:
        """
        Get search suggestions based on a query
        
        Args:
            query: Base query for suggestions
            
        Returns:
            List of suggested search queries
        """
        # Simple suggestions based on common search patterns
        suggestions = []
        
        # Add "how to" variations
        if not query.lower().startswith(("how", "what", "why", "when", "where")):
            suggestions.extend([
                f"how to {query}",
                f"what is {query}",
                f"why {query}"
            ])
        
        # Add current year for time-sensitive queries
        import datetime
        current_year = datetime.datetime.now().year
        suggestions.append(f"{query} {current_year}")
        
        # Add "best" and "latest" variations
        suggestions.extend([
            f"best {query}",
            f"latest {query}",
            f"{query} tutorial",
            f"{query} guide"
        ])
        
        return suggestions[:5]  # Return top 5 suggestions

# Global instance
tavily_search = TavilySearchTool()

def search_web(query: str, max_results: int = 3) -> Dict[str, Any]:
    """
    Convenience function for web search
    
    Args:
        query: Search query
        max_results: Maximum number of results
        
    Returns:
        Search results dictionary
    """
    return tavily_search.search(query, max_results)

def search_web_summary(query: str) -> str:
    """
    Convenience function for web search summary
    
    Args:
        query: Search query
        
    Returns:
        Formatted search summary
    """
    return tavily_search.search_summary(query)