#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GitBook to PDF Converter
------------------------
This script scrapes a GitBook website and converts it to a single PDF file,
preserving the directory structure and including images.
"""

import os
import re
import sys
import argparse
import requests
import urllib.parse
import concurrent.futures
from threading import Lock
from bs4 import BeautifulSoup
from weasyprint import HTML, CSS
import tempfile
import shutil
import logging
import time
from urllib.parse import urljoin, urlparse

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('gitbook2pdf')

class GitbookScraper:
    """负责抓取GitBook网站内容的类"""
    
    def __init__(self, base_url, output_dir=None, delay=1, proxy=None, max_workers=3):
        """
        初始化GitBook抓取器
        
        Args:
            base_url (str): GitBook网站的基础URL
            output_dir (str, optional): 临时输出目录
            delay (int, optional): 请求之间的延迟（秒）
            proxy (dict, optional): 代理设置，格式为:
                {
                    'http': 'http://proxy_ip:proxy_port',
                    'https': 'https://proxy_ip:proxy_port'
                }
            max_workers (int, optional): 最大线程数，默认为3
        """
        self.max_workers = max_workers
        self.base_url = base_url.rstrip('/')
        self.delay = delay
        self.proxy = proxy
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        
        # 创建临时目录用于存储下载的内容
        if output_dir:
            self.output_dir = output_dir
            os.makedirs(self.output_dir, exist_ok=True)
        else:
            self.output_dir = tempfile.mkdtemp(prefix='gitbook_')
            
        self.img_dir = os.path.join(self.output_dir, 'images')
        os.makedirs(self.img_dir, exist_ok=True)
        
        # 存储已访问的URL，避免重复抓取
        self.visited_urls = set()
        # 存储页面内容和结构
        self.pages = []
        # 存储目录结构
        self.toc = []
        
        logger.info(f"初始化GitBook抓取器，基础URL: {self.base_url}")
        logger.info(f"输出目录: {self.output_dir}")
    
    def get_page(self, url):
        """
        获取页面内容
        
        Args:
            url (str): 页面URL
            
        Returns:
            BeautifulSoup: 解析后的页面内容
        """
        if not url.startswith('http'):
            url = urljoin(self.base_url, url)
            
        # 如果已经访问过，则跳过
        if url in self.visited_urls:
            return None
            
        logger.info(f"抓取页面: {url}")
        
        try:
            response = self.session.get(url, proxies=self.proxy)
            response.raise_for_status()
            self.visited_urls.add(url)
            
            # 添加延迟，避免请求过于频繁
            time.sleep(self.delay)
            
            return BeautifulSoup(response.text, 'html.parser')
        except requests.exceptions.RequestException as e:
            logger.error(f"抓取页面 {url} 时出错: {e}")
            return None
    
    def download_image(self, img_url):
        """
        下载图片并保存到本地
        
        Args:
            img_url (str): 图片URL
            
        Returns:
            str: 本地图片路径
        """
        if not img_url.startswith('http'):
            img_url = urljoin(self.base_url, img_url)
            
        # 提取图片文件名
        img_filename = os.path.basename(urlparse(img_url).path)
        if not img_filename:
            img_filename = f"img_{hash(img_url)}.png"
            
        local_path = os.path.join(self.img_dir, img_filename)
        
        # 如果图片已经下载，则跳过
        if os.path.exists(local_path):
            return local_path
            
        logger.info(f"下载图片: {img_url}")
        
        try:
            # 使用代理设置（如果配置了代理）
            kwargs = {'stream': True}
            if self.proxy:
                kwargs['proxies'] = self.proxy
                logger.debug(f"使用代理下载图片: {self.proxy}")
            
            response = self.session.get(img_url, **kwargs)
            response.raise_for_status()
            
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            # 添加延迟，避免请求过于频繁
            time.sleep(self.delay)
            
            return local_path
        except requests.exceptions.ProxyError as e:
            logger.error(f"代理错误 - 下载图片 {img_url} 失败: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"下载图片 {img_url} 失败: {e}")
            return None
    
    def process_page_content(self, soup, page_url, title=None):
        """
        处理页面内容，下载图片并更新链接
        
        Args:
            soup (BeautifulSoup): 解析后的页面内容
            page_url (str): 页面URL
            title (str, optional): 页面标题，用于移除重复标题
            
        Returns:
            str: 处理后的HTML内容
        """
        # 处理图片
        for img in soup.find_all('img'):
            if img is None:
                continue
            src = img.get('src')
            if src:
                local_path = self.download_image(src)
                if local_path:
                    img['src'] = os.path.relpath(local_path, self.output_dir)
        
        # 处理内部链接
        for a in soup.find_all('a'):
            if a is None:
                continue
            href = a.get('href')
            if href and not href.startswith(('http', '#', 'mailto:')):
                a['href'] = urljoin(page_url, href)
        
        # 移除导航和目录元素
        for nav in soup.find_all(['nav', 'div'], class_=['summary', 'book-summary', 'table-of-contents']):
            nav.decompose()
        
        if not soup:
            logger.warning("传入的soup对象为None")
            return "<p>无法处理页面内容</p>"

        # 尝试提取主要内容区域
        content_selectors = [
            ('article', {}),
            ('main', {}),
            ('div', {'class': 'content'}),
            ('div', {'class': 'article-content'}),
            ('div', {'class': 'markdown-section'}),
            ('div', {'role': 'main'}),
            ('body', {})
        ]

        main_content = None
        for tag, attrs in content_selectors:
            main_content = soup.find(tag, attrs)
            if main_content:
                break

        if not main_content:
            logger.warning(f"在页面 {page_url} 中未找到主要内容区域")
            return "<p>未找到页面内容</p>"

        try:
            # 移除不需要的元素
            for element in main_content.find_all(['nav', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                if not element:
                    continue
                
                try:
                    classes = element.get('class', [])
                    if classes:
                        class_str = ' '.join(classes)
                        if any(c in class_str for c in ['summary', 'book-summary', 'table-of-contents', 'header', 'heading']):
                            element.decompose()
                            continue
                except AttributeError:
                    continue

                if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    try:
                        if title and self._similar_text(element.get_text(strip=True), title):
                            element.decompose()
                    except AttributeError:
                        continue

            return str(main_content)

        except Exception as e:
            logger.error(f"处理页面内容时出错: {e}")
            return "<p>处理页面内容时出错</p>"
    
    def _similar_text(self, text1, text2):
        """
        检查两个文本是否相似（支持中文数字和阿拉伯数字的匹配）
        
        Args:
            text1 (str): 第一个文本
            text2 (str): 第二个文本
            
        Returns:
            bool: 如果文本相似则返回True
        """
        try:
            if not text1 or not text2:
                return False
                
            # 转换为字符串（以防是其他类型）
            text1 = str(text1)
            text2 = str(text2)
            
            # 中文数字到阿拉伯数字的映射
            cn_nums = {
                '零': '0', '一': '1', '二': '2', '三': '3', '四': '4',
                '五': '5', '六': '6', '七': '7', '八': '8', '九': '9',
                '十': '10', '百': '100', '千': '1000', '万': '10000'
            }
            
            def normalize_text(text):
                # 移除所有空白字符并转为小写
                text = ''.join(text.lower().split())
                
                # 替换中文数字为阿拉伯数字
                for cn, ar in cn_nums.items():
                    text = text.replace(cn, ar)
                
                # 移除常见的标题前缀
                prefixes = ['第', '章', 'chapter', 'section', 'part']
                for prefix in prefixes:
                    text = text.replace(prefix, '')
                
                return text.strip()
            
            # 标准化两个文本
            norm_text1 = normalize_text(text1)
            norm_text2 = normalize_text(text2)
            
            # 如果处理后的文本为空，返回False
            if not norm_text1 or not norm_text2:
                return False
            
            # 检查标准化后的文本是否相等
            return norm_text1 == norm_text2
            
        except Exception as e:
            logger.debug(f"文本相似度检查出错: {e}")
            return False
            
    def extract_toc(self, soup):
        """
        从页面中提取目录结构
        
        Args:
            soup (BeautifulSoup): 解析后的页面内容
            
        Returns:
            list: 目录结构
        """
        if not soup:
            logger.warning("提取目录时收到空的页面内容")
            return []
            
        toc = []
        seen_hrefs = set()  # 用于跟踪已经添加的链接
        
        try:
            # 尝试查找目录元素
            nav = soup.find('nav') or soup.find('div', class_='summary') or soup.find('ul', class_='summary')
            
            if nav:
                for a in nav.find_all('a'):
                    try:
                        if not a or not a.get('href'):
                            continue
                            
                        href = a['href']
                        if href.startswith(('#', 'http', 'javascript:', 'mailto:')):
                            continue
                            
                        title = a.get_text(strip=True)
                        if not title or href in seen_hrefs:
                            continue
                            
                        seen_hrefs.add(href)
                        
                        # 计算层级
                        level = 0
                        parent = a.parent
                        while parent and parent.name != 'nav':
                            if parent.name in ['li', 'ul']:
                                level += 1
                            parent = parent.parent
                        
                        toc.append({
                            'title': title,
                            'href': href,
                            'level': level
                        })
                    except Exception as e:
                        logger.debug(f"处理目录项时出错: {e}")
                        continue
            
            if not toc:
                logger.warning("未找到有效的目录结构")
                
            return toc
            
        except Exception as e:
            logger.error(f"提取目录时出错: {e}")
            return []
    
    def extract_toc(self, soup):
        """
        从页面中提取目录结构
        
        Args:
            soup (BeautifulSoup): 解析后的页面内容
            
        Returns:
            list: 目录结构
        """
        toc = []
        seen_hrefs = set()  # 用于跟踪已经添加的链接
        
        # 尝试查找目录元素
        nav = soup.find('nav') or soup.find('div', class_='summary') or soup.find('ul', class_='summary')
        
        if nav:
            for a in nav.find_all('a'):
                if a.get('href') and not a['href'].startswith(('#', 'http')):
                    title = a.get_text(strip=True)
                    href = a['href']
                    
                    # 跳过空标题或已经添加的链接
                    if not title or href in seen_hrefs:
                        continue
                    
                    seen_hrefs.add(href)
                    
                    # 计算层级
                    level = 0
                    parent = a.parent
                    while parent and parent.name != 'nav':
                        if parent.name == 'li' or parent.name == 'ul':
                            level += 1
                        parent = parent.parent
                    
                    toc.append({
                        'title': title,
                        'href': href,
                        'level': level
                    })
        
        return toc
    
    def _download_page(self, item):
        """线程安全的页面下载方法"""
        try:
            if 'title' not in item or 'href' not in item:
                logger.debug(f"跳过无效的目录项: {item}")
                return

            title = item['title'].strip() if item['title'] else ""
            href = item['href'].strip() if item['href'] else ""
            
            # 跳过空标题或空链接
            if not title or not href:
                return
            
            # 构建完整URL并获取页面
            page_url = urljoin(self.base_url, href)
            logger.info(f"抓取页面: {title} ({page_url})")
            
            page_soup = self.get_page(page_url)
            if not page_soup:
                logger.warning(f"无法获取页面内容: {page_url}")
                # 添加一个空内容页面，以保持目录结构完整
                with self.pages_lock:
                    self.pages.append({
                        'title': title,
                        'url': page_url,
                        'content': f"<p>无法获取页面内容: {page_url}</p>",
                        'level': item.get('level', 0)
                    })
                return
            
            # 处理页面内容
            try:
                if page_soup:
                    # 始终使用目录中的标题，不处理页面中的标题
                    content = self.process_page_content(page_soup, page_url, None)
                else:
                    logger.warning(f"页面 {page_url} 的soup对象为None")
                    content = f"<p>无法获取页面内容: {page_url}</p>"
            except Exception as e:
                logger.error(f"处理页面 {os.path.basename(href)} 时出错: {e}")
                content = f"<p>处理页面内容时出错: {e}</p>"
            
            # 线程安全地添加到页面列表
            with self.pages_lock:
                self.pages.append({
                    'title': title,  # 使用目录中的标题
                    'url': page_url,
                    'content': content,
                    'level': item.get('level', 0)
                })
                
        except Exception as e:
            logger.error(f"处理页面 {item.get('href', '未知')} 时出错: {e}")

    def scrape(self):
        """
        开始抓取GitBook网站（使用多线程）
        
        Returns:
            tuple: (pages, toc) 页面内容和目录结构
        """
        logger.info("开始抓取GitBook网站")
        
        try:
            # 获取首页
            soup = self.get_page(self.base_url)
            if not soup:
                logger.error("无法获取首页内容")
                return [], []
            
            # 提取目录结构
            self.toc = self.extract_toc(soup)
            
            # 创建线程安全的列表和锁
            self.pages = []
            self.pages_lock = Lock()
            
            if not self.toc:
                logger.warning("无法从首页提取目录结构，尝试使用其他方法")
                # 如果无法从首页提取目录，尝试查找常见的目录页
                for summary_path in ['SUMMARY.md', 'summary.html', 'toc.html']:
                    try:
                        summary_url = urljoin(self.base_url, summary_path)
                        summary_soup = self.get_page(summary_url)
                        if summary_soup:
                            self.toc = self.extract_toc(summary_soup)
                            if self.toc:
                                logger.info(f"从 {summary_path} 成功提取目录")
                                break
                    except Exception as e:
                        logger.debug(f"尝试从 {summary_path} 提取目录时出错: {e}")
            
            # 如果仍然无法提取目录，则尝试从首页链接构建
            if not self.toc:
                logger.warning("无法找到目录结构，将从首页链接构建")
                try:
                    for a in soup.find_all('a'):
                        if a and a.get('href') and not a['href'].startswith(('#', 'http', 'mailto:', 'javascript:')):
                            title = a.get_text(strip=True)
                            href = a['href']
                            if title and href:
                                self.toc.append({
                                    'title': title,
                                    'href': href,
                                    'level': 0
                                })
                except Exception as e:
                    logger.error(f"从首页链接构建目录时出错: {e}")
            
            if not self.toc:
                logger.error("无法构建目录结构，抓取失败")
                return [], []
                
            logger.info(f"找到 {len(self.toc)} 个目录项")
            
            # 过滤重复的目录项
            seen_titles = set()
            seen_urls = set()
            filtered_toc = []
            
            for item in self.toc:
                title = item.get('title', '').strip()
                href = item.get('href', '').strip()
                
                if not title or not href:
                    continue
                    
                if title in seen_titles or href in seen_urls:
                    continue
                    
                seen_titles.add(title)
                seen_urls.add(href)
                filtered_toc.append(item)
            
            # 使用线程池下载页面
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = [executor.submit(self._download_page, item) for item in filtered_toc]
                concurrent.futures.wait(futures)
            
            # 更新过滤后的目录
            self.toc = filtered_toc
            
            if not self.pages:
                logger.warning("未能抓取到任何页面内容")
            else:
                # 根据目录顺序对页面进行排序
                logger.info("根据目录顺序对页面进行排序...")
                
                # 创建URL到目录索引的映射
                url_to_index = {}
                for i, item in enumerate(filtered_toc):
                    url = urljoin(self.base_url, item['href'])
                    url_to_index[url] = i
                
                # 根据URL在目录中的位置对页面进行排序
                self.pages.sort(key=lambda page: url_to_index.get(page['url'], float('inf')))
                
                logger.info(f"抓取完成，共获取 {len(self.pages)} 个页面")
                
            return self.pages, self.toc
            
        except Exception as e:
            logger.exception(f"抓取过程中发生错误: {e}")
            return self.pages, self.toc  # 返回已抓取的内容
    
    def cleanup(self):
        """清理临时文件"""
        if os.path.exists(self.output_dir) and not os.path.samefile(self.output_dir, os.getcwd()):
            shutil.rmtree(self.output_dir)
            logger.info(f"已清理临时目录: {self.output_dir}")


class PDFGenerator:
    """负责将抓取的内容转换为PDF的类"""
    
    def __init__(self, pages, toc, output_dir):
        """
        初始化PDF生成器
        
        Args:
            pages (list): 页面内容列表
            toc (list): 目录结构
            output_dir (str): 输出目录
        """
        self.pages = pages
        self.toc = toc
        self.output_dir = output_dir
        
        logger.info("初始化PDF生成器")
    
    def generate_html(self):
        """
        生成完整的HTML文档
        
        Returns:
            str: HTML文档路径
        """
        html_path = os.path.join(self.output_dir, 'gitbook.html')
        
        # 创建HTML文档
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write('<!DOCTYPE html>\n')
            f.write('<html>\n<head>\n')
            f.write('<meta charset="UTF-8">\n')
            f.write('<meta name="viewport" content="width=device-width, initial-scale=1.0">\n')
            f.write('<title>GitBook PDF</title>\n')
            f.write('<style>\n')
            f.write('body { font-family: Arial, sans-serif; line-height: 1.6; }\n')
            f.write('h1 { page-break-before: always; }\n')
            f.write('h1:first-of-type { page-break-before: avoid; }\n')
            f.write('img { max-width: 100%; height: auto; }\n')
            f.write('a { color: #4183C4; text-decoration: none; }\n')
            f.write('pre { background-color: #f8f8f8; border: 1px solid #ddd; padding: 10px; overflow-x: auto; }\n')
            f.write('code { background-color: #f8f8f8; padding: 2px 4px; }\n')
            f.write('table { border-collapse: collapse; width: 100%; }\n')
            f.write('table, th, td { border: 1px solid #ddd; padding: 8px; }\n')
            f.write('</style>\n')
            f.write('</head>\n<body>\n')
            
            # 添加目录
            f.write('<h1>目录</h1>\n<ul>\n')
            for item in self.toc:
                indent = '  ' * item['level']
                f.write(f'{indent}<li><a href="#{self._make_id(item["title"])}">{item["title"]}</a></li>\n')
            f.write('</ul>\n')
            
            # 添加页面内容
            for page in self.pages:
                # 创建页面锚点和标题的div容器
                f.write(f'<div class="chapter" id="{self._make_id(page["title"])}">\n')
                
                # 检查内容是否已包含标题
                content_has_title = False
                if page['content']:
                    # 查找第一个<h1>标签
                    h1_start = page['content'].find('<h1')
                    if h1_start >= 0:
                        h1_end = page['content'].find('</h1>', h1_start)
                        if h1_end >= 0:
                            content_title = page['content'][h1_start:h1_end+5]
                            # 检查是否与目录标题相似
                            soup = BeautifulSoup(content_title, 'html.parser')
                            if soup.h1 and self._similar_text(soup.h1.get_text(), page['title']):
                                content_has_title = True
                
                # 只有当内容中没有标题时才添加
                if not content_has_title:
                    f.write(f'<h1>{page["title"]}</h1>\n')
                
                # 写入内容
                f.write(page['content'])
                f.write('</div>\n')
                
                # 添加章节分隔线（最后一页除外）
                if page != self.pages[-1]:
                    f.write('\n<hr style="page-break-after: always;">\n')
                
            f.write('</body>\n</html>')
        
        logger.info(f"已生成HTML文档: {html_path}")
        return html_path
    
    def _make_id(self, text):
        """
        将文本转换为有效的HTML ID
        
        Args:
            text (str): 原始文本
            
        Returns:
            str: 有效的HTML ID
        """
        # 移除非字母数字字符，并将空格替换为下划线
        return re.sub(r'[^\w\s]', '', text).replace(' ', '_').lower()
        
    def _similar_text(self, text1, text2):
        """
        检查两个文本是否相似（支持中文数字和阿拉伯数字的匹配）
        
        Args:
            text1 (str): 第一个文本
            text2 (str): 第二个文本
            
        Returns:
            bool: 如果文本相似则返回True
        """
        try:
            if not text1 or not text2:
                return False
                
            # 转换为字符串（以防是其他类型）
            text1 = str(text1)
            text2 = str(text2)
            
            # 中文数字到阿拉伯数字的映射
            cn_nums = {
                '零': '0', '一': '1', '二': '2', '三': '3', '四': '4',
                '五': '5', '六': '6', '七': '7', '八': '8', '九': '9',
                '十': '10', '百': '100', '千': '1000', '万': '10000'
            }
            
            def normalize_text(text):
                # 移除所有空白字符并转为小写
                text = ''.join(text.lower().split())
                
                # 替换中文数字为阿拉伯数字
                for cn, ar in cn_nums.items():
                    text = text.replace(cn, ar)
                
                # 移除常见的标题前缀
                prefixes = ['第', '章', 'chapter', 'section', 'part']
                for prefix in prefixes:
                    text = text.replace(prefix, '')
                
                return text.strip()
            
            # 标准化两个文本
            norm_text1 = normalize_text(text1)
            norm_text2 = normalize_text(text2)
            
            # 如果处理后的文本为空，返回False
            if not norm_text1 or not norm_text2:
                return False
            
            # 检查标准化后的文本是否相等
            return norm_text1 == norm_text2
            
        except Exception as e:
            logger.debug(f"文本相似度检查出错: {e}")
            return False
    
    def generate_pdf(self, output_path):
        """
        生成PDF文件
        
        Args:
            output_path (str): PDF输出路径
            
        Returns:
            str: PDF文件路径
        """
        html_path = self.generate_html()
        
        logger.info(f"开始生成PDF: {output_path}")
        
        try:
            # 使用WeasyPrint生成PDF
            logger.debug(f"正在加载HTML文件: {html_path}")
            html = HTML(filename=html_path)
            
            logger.debug("正在创建CSS样式")
            css = CSS(string='''
                @page {
                    margin: 1cm;
                    @top-center {
                        content: string(chapter);
                    }
                    @bottom-center {
                        content: counter(page);
                    }
                }
                h1 {
                    string-set: chapter content();
                    page-break-before: always;
                }
                h1:first-of-type {
                    page-break-before: avoid;
                }
            ''')
            
            logger.debug(f"正在生成PDF文件: {output_path}")
            html.write_pdf(output_path, stylesheets=[css])
            
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                logger.info(f"PDF生成成功: {output_path} (大小: {file_size/1024:.1f}KB)")
                return output_path
            else:
                logger.error("PDF文件未能成功创建")
                return None
                
        except Exception as e:
            logger.error(f"生成PDF时出错: {str(e)}")
            logger.debug("错误详情:", exc_info=True)
            return None


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='将GitBook网站转换为PDF')
    parser.add_argument('url', help='GitBook网站URL')
    parser.add_argument('-o', '--output', help='输出PDF文件路径', default='gitbook.pdf')
    parser.add_argument('-d', '--delay', type=float, help='请求之间的延迟（秒）', default=1.0)
    parser.add_argument('-t', '--temp', help='临时文件目录', default=None)
    parser.add_argument('-w', '--workers', type=int, default=3, help='并发下载线程数（默认：3）')
    parser.add_argument('-v', '--verbose', action='store_true', help='显示详细日志')
    parser.add_argument('-k', '--keep-temp', action='store_true', help='保留临时文件（用于调试）')
    parser.add_argument('-p', '--proxy', help='代理服务器设置，格式为 http://proxy_ip:proxy_port')
    
    args = parser.parse_args()
    
    # 设置日志级别
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # 创建临时目录
    temp_dir = args.temp or tempfile.mkdtemp(prefix='gitbook_')
    logger.info(f"使用临时目录: {temp_dir}")
    
    # 初始化pdf_path为None
    pdf_path = None
    success = False
    
    try:
        # 准备代理配置
        proxy = None
        if args.proxy:
            proxy = {
                'http': args.proxy,
                'https': args.proxy
            }
            logger.info(f"使用代理服务器: {args.proxy}")
        
        # 抓取GitBook网站
        logger.info(f"开始抓取GitBook网站: {args.url}")
        scraper = GitbookScraper(args.url, temp_dir, args.delay, proxy)
        pages, toc = scraper.scrape()
        
        if not pages:
            logger.error("未能抓取到任何页面内容")
            return 1
        
        logger.info(f"成功抓取 {len(pages)} 个页面")
        
        # 生成PDF
        logger.info(f"开始生成PDF: {args.output}")
        pdf_generator = PDFGenerator(pages, toc, temp_dir)
        output_path = os.path.abspath(args.output)
        pdf_path = pdf_generator.generate_pdf(output_path)
        
        if pdf_path:
            logger.info(f"PDF已成功生成: {pdf_path}")
            success = True
            return 0
        else:
            logger.error("PDF生成失败")
            return 1
            
    except KeyboardInterrupt:
        logger.info("操作被用户中断")
        return 130
    except Exception as e:
        logger.exception(f"发生错误: {e}")
        return 1
    finally:
        # 处理临时目录
        if os.path.exists(temp_dir):
            if success and not args.keep_temp and not args.temp:
                # 只有在成功生成PDF且未指定保留临时文件时才清理
                try:
                    shutil.rmtree(temp_dir)
                    logger.debug(f"已清理临时目录: {temp_dir}")
                except Exception as e:
                    logger.warning(f"清理临时目录时出错: {e}")
            else:
                # 在失败的情况下或指定保留临时文件时，显示临时文件位置
                logger.info(f"临时文件保留在: {temp_dir}")
                if os.path.exists(os.path.join(temp_dir, 'gitbook.html')):
                    logger.info("您可以查看生成的HTML文件: " + os.path.join(temp_dir, 'gitbook.html'))


if __name__ == '__main__':
    sys.exit(main())