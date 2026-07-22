from .base import Collector, CollectorResult
from .html_list import HtmlListCollector
from .official import OfficialSiteCollector
from .rss import RssCollector
from .wechat import WechatPublicCollector

__all__ = ["Collector", "CollectorResult", "HtmlListCollector", "OfficialSiteCollector", "RssCollector", "WechatPublicCollector"]
