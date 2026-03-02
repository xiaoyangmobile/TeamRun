"""
Web search tool using Tavily.
"""

import os
from typing import Any


class WebSearchTool:
    """Tool for web search using Tavily API."""

    def __init__(self, api_key: str | None = None):
        """
        Initialize web search tool.

        :param api_key: Tavily API key (uses TAVILY_API_KEY env var if not provided)
        """
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        self._client = None

    @property
    def client(self) -> Any:
        """Get or create Tavily client."""
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "Tavily API key not found. "
                    "Set TAVILY_API_KEY environment variable or pass api_key parameter."
                )
            try:
                from tavily import TavilyClient
                self._client = TavilyClient(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "tavily-python is not installed. "
                    "Install it with: pip install tavily-python"
                )
        return self._client

    def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        include_answer: bool = True
    ) -> dict[str, Any]:
        """
        Perform a web search.

        :param query: Search query
        :param max_results: Maximum number of results
        :param search_depth: Search depth ("basic" or "advanced")
        :param include_answer: Include AI-generated answer
        :return: Search results
        """
        try:
            response = self.client.search(
                query=query,
                max_results=max_results,
                search_depth=search_depth,
                include_answer=include_answer
            )
            return {
                "success": True,
                "answer": response.get("answer", ""),
                "results": response.get("results", []),
                "query": query
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "query": query
            }

    def search_context(
        self,
        query: str,
        max_results: int = 5
    ) -> dict[str, Any]:
        """
        Search and return context suitable for LLM consumption.

        :param query: Search query
        :param max_results: Maximum number of results
        :return: Formatted context
        """
        try:
            context = self.client.get_search_context(
                query=query,
                max_results=max_results
            )
            return {
                "success": True,
                "context": context,
                "query": query
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "query": query
            }
