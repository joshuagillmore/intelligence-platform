"""Source connectors — auto-registered via @register_connector decorator."""
# Import all connector modules to trigger registration
from intel_platform.connectors.flat_file import FlatFileConnector  # noqa: F401
from intel_platform.connectors.web_scrape import WebScrapeConnector  # noqa: F401
from intel_platform.connectors.rss_feed import RSSFeedConnector  # noqa: F401
from intel_platform.connectors.api_feed import APIFeedConnector  # noqa: F401
