import html2text
import pandas as pd

_text = """
<p class="MsoNormal">В РД по разделам "АР" и "ВК" Кормокухни имеются несоответствия по трапам и лоткам. В разделе "АР" указано 2 трапа и 2 лотка, в разделе "ВК" указан один трап и один лоток. Прошу откорректировать несоответствия в РД, либо сделать запись в ЖАН (с изменением в спецификации ВК).</p>
"""
from bs4 import BeautifulSoup

from html.parser import HTMLParser


def html_convert(data):
	class HTMLFilter(HTMLParser):
		text = ""

		def handle_data(self, data):
			self.text += data

	f = HTMLFilter()
	f.feed(data)
	return f.text


print(html_convert(_text))
