# ui/components/md_preview_only.py
"""
Markdown 纯预览器组件
只显示渲染结果，不包含编辑器
支持全部 6 种主题
"""

import markdown
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import pyqtSignal

# 延迟导入 WebEngine
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    WEBENGINE_AVAILABLE = True
except ImportError:
    WEBENGINE_AVAILABLE = False


class MDPreviewOnly(QWidget):
    """
    Markdown 纯预览器
    只显示渲染结果，适合显示生成的报告
    """
    
    # 主题定义
    THEMES = {
        "GitHub Light": "github-light",
        "GitHub Dark": "github-dark", 
        "VuePress Light": "vuepress-light",
        "VuePress Dark": "vuepress-dark",
        "Ant Design Light": "antd-light",
        "Ant Design Dark": "antd-dark"
    }
    
    def __init__(self, parent=None, initial_theme: str = "GitHub Light"):
        super().__init__(parent)
        self.current_theme = initial_theme
        
        # 初始化 UI
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        if WEBENGINE_AVAILABLE:
            self.web_view = QWebEngineView()
            self._setup_webengine_settings()
            layout.addWidget(self.web_view)
        else:
            self.web_view = None
            placeholder = QLabel("WebEngine 不可用")
            layout.addWidget(placeholder)
    
    def _setup_webengine_settings(self):
        if self.web_view is not None:
            try:
                settings = self.web_view.settings()
                settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
                settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
            except:
                pass
    
    def render_markdown(self, md_text: str):
        """渲染 Markdown 文本"""
        if self.web_view is None:
            return
            
        try:
            html_content = markdown.markdown(
                md_text,
                extensions=[
                    'extra',           # 额外功能
                    'codehilite',      # 代码高亮
                    'tables',          # 表格支持
                    'fenced_code',     # 代码块
                    'nl2br',           # 换行转 <br>
                    'sane_lists'       # 智能列表
                ],
                extension_configs={
                    'codehilite': {
                        'css_class': 'highlight',
                        'guess_lang': True,
                        'use_pygments': True
                    }
                }
            )
            
            full_html = self._generate_html(html_content, self.current_theme)
            self.web_view.setHtml(full_html)
        except Exception as e:
            print(f"Markdown 渲染错误: {e}")
    
    def _generate_html(self, content: str, theme_name: str) -> str:
        """生成完整的 HTML 页面"""
        css = self._get_theme_css(theme_name)
        highlight_css = self._get_highlight_css(theme_name)
        
        return f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                {css}
                {highlight_css}
            </style>
        </head>
        <body>
            <div class="markdown-container">{content}</div>
        </body>
        </html>
        """
    
    def _get_theme_css(self, theme_name: str) -> str:
        """获取主题 CSS"""
        is_dark = "Dark" in theme_name
        
        if "GitHub" in theme_name:
            if is_dark:
                return """
                .markdown-container {
                    font-family: -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif;
                    font-size: 16px;
                    line-height: 1.6;
                    word-wrap: break-word;
                    box-sizing: border-box;
                    min-width: 200px;
                    max-width: 980px;
                    margin: 0 auto;
                    padding: 20px;
                    background: #0d1117;
                    color: #c9d1d9;
                }
                .markdown-container h1, .markdown-container h2 {
                    padding-bottom: 0.3em;
                    border-bottom: 1px solid #30363d;
                }
                .markdown-container h1 { font-size: 2em; }
                .markdown-container h2 { font-size: 1.5em; }
                .markdown-container a { color: #58a6ff; text-decoration: none; }
                .markdown-container a:hover { text-decoration: underline; }
                .markdown-container code { 
                    padding: 0.2em 0.4em; 
                    margin: 0; 
                    font-size: 85%; 
                    background-color: rgba(110,118,129,0.4); 
                    border-radius: 6px; 
                }
                .markdown-container pre { 
                    padding: 16px; 
                    overflow: auto; 
                    font-size: 85%; 
                    line-height: 1.45; 
                    border-radius: 6px; 
                    background-color: #161b22; 
                }
                .markdown-container pre code { padding: 0; background: transparent; }
                .markdown-container blockquote { 
                    padding: 0 1em; 
                    color: #8b949e; 
                    border-left: 0.25em solid #30363d; 
                    margin: 0; 
                }
                .markdown-container table { 
                    border-spacing: 0; 
                    border-collapse: collapse; 
                    display: block; 
                    width: 100%; 
                    overflow: auto; 
                }
                .markdown-container table th, 
                .markdown-container table td { 
                    padding: 6px 13px; 
                    border: 1px solid #30363d; 
                }
                .markdown-container table th { font-weight: 600; }
                .markdown-container table tr { 
                    background-color: #0d1117; 
                    border-top: 1px solid #30363d; 
                }
                .markdown-container table tr:nth-child(2n) { 
                    background-color: #161b22; 
                }
                .markdown-container img { max-width: 100%; }
                """
            else:
                return """
                .markdown-container {
                    font-family: -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif;
                    font-size: 16px;
                    line-height: 1.6;
                    word-wrap: break-word;
                    box-sizing: border-box;
                    min-width: 200px;
                    max-width: 980px;
                    margin: 0 auto;
                    padding: 20px;
                    background: #ffffff;
                    color: #24292f;
                }
                .markdown-container h1, .markdown-container h2 {
                    padding-bottom: 0.3em;
                    border-bottom: 1px solid #d0d7de;
                }
                .markdown-container h1 { font-size: 2em; }
                .markdown-container h2 { font-size: 1.5em; }
                .markdown-container a { color: #0969da; text-decoration: none; }
                .markdown-container a:hover { text-decoration: underline; }
                .markdown-container code { 
                    padding: 0.2em 0.4em; 
                    margin: 0; 
                    font-size: 85%; 
                    background-color: #f6f8fa; 
                    border-radius: 6px; 
                }
                .markdown-container pre { 
                    padding: 16px; 
                    overflow: auto; 
                    font-size: 85%; 
                    line-height: 1.45; 
                    border-radius: 6px; 
                }
                .markdown-container pre code { padding: 0; background: transparent; }
                .markdown-container blockquote { 
                    padding: 0 1em; 
                    color: #57606a; 
                    border-left: 0.25em solid #d0d7de; 
                    margin: 0; 
                }
                .markdown-container table { 
                    border-spacing: 0; 
                    border-collapse: collapse; 
                    display: block; 
                    width: 100%; 
                    overflow: auto; 
                }
                .markdown-container table th, 
                .markdown-container table td { 
                    padding: 6px 13px; 
                    border: 1px solid #d0d7de; 
                }
                .markdown-container table th { font-weight: 600; }
                .markdown-container table tr { 
                    background-color: #ffffff; 
                    border-top: 1px solid #d0d7de; 
                }
                .markdown-container table tr:nth-child(2n) { 
                    background-color: #f6f8fa; 
                }
                .markdown-container img { max-width: 100%; }
                """
        
        elif "VuePress" in theme_name:
            if is_dark:
                return """
                .markdown-container {
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, sans-serif;
                    font-size: 16px;
                    line-height: 1.6;
                    color: #adbac7;
                    background-color: #1c2128;
                    margin: 0;
                    padding: 20px;
                }
                .markdown-container h1, .markdown-container h2, .markdown-container h3, .markdown-container h4, .markdown-container h5, .markdown-container h6 {
                    font-weight: 600;
                    line-height: 1.25;
                    margin-top: 1.5em;
                    margin-bottom: 0.5em;
                    color: #adbac7;
                }
                .markdown-container h1 { font-size: 2.2rem; border-bottom: 2px solid #373e47; padding-bottom: 0.3em; }
                .markdown-container h2 { font-size: 1.65rem; border-bottom: 1px solid #373e47; padding-bottom: 0.3em; }
                .markdown-container a { color: #539bf5; text-decoration: none; font-weight: 500; }
                .markdown-container a:hover { text-decoration: underline; color: #6cb6ff; }
                .markdown-container code { 
                    background-color: rgba(99,110,123,0.4); 
                    border-radius: 3px; 
                    color: #f47067; 
                    padding: 2px 4px; 
                    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace; 
                    font-size: 0.85em; 
                }
                .markdown-container pre { 
                    background-color: #2d333b; 
                    border-radius: 8px; 
                    padding: 16px; 
                    overflow: auto; 
                    border: 1px solid #444c56; 
                    line-height: 1.45; 
                }
                .markdown-container pre code { background: none; color: #cdd9e5; padding: 0; }
                .markdown-container blockquote { 
                    background-color: rgba(65,132,228,0.1); 
                    border-left: 4px solid #539bf5; 
                    margin: 1em 0; 
                    padding: 1em 1.5em; 
                    border-radius: 0 4px 4px 0; 
                    color: #768390; 
                }
                .markdown-container table { 
                    border-collapse: collapse; 
                    width: 100%; 
                    margin: 1em 0; 
                    border-radius: 4px; 
                    overflow: hidden; 
                }
                .markdown-container table th, 
                .markdown-container table td { 
                    border: 1px solid #444c56; 
                    padding: 0.75em 1em; 
                    text-align: left; 
                }
                .markdown-container table th { 
                    background-color: #2d333b; 
                    font-weight: 600; 
                }
                .markdown-container table tr:nth-child(even) { 
                    background-color: rgba(99,110,123,0.1); 
                }
                .markdown-container img { max-width: 100%; border-radius: 4px; }
                """
            else:
                return """
                .markdown-container {
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, sans-serif;
                    font-size: 16px;
                    line-height: 1.6;
                    color: #2c3e50;
                    background-color: #fff;
                    margin: 0;
                    padding: 20px;
                }
                .markdown-container h1, .markdown-container h2, .markdown-container h3, .markdown-container h4, .markdown-container h5, .markdown-container h6 {
                    font-weight: 600;
                    line-height: 1.25;
                    margin-top: 1.5em;
                    margin-bottom: 0.5em;
                    color: #2c3e50;
                }
                .markdown-container h1 { font-size: 2.2rem; border-bottom: 2px solid #eaecef; padding-bottom: 0.3em; }
                .markdown-container h2 { font-size: 1.65rem; border-bottom: 1px solid #eaecef; padding-bottom: 0.3em; }
                .markdown-container a { color: #3eaf7c; text-decoration: none; font-weight: 500; }
                .markdown-container a:hover { text-decoration: underline; color: #4abf8a; }
                .markdown-container code { 
                    background-color: #f8f8f8; 
                    border-radius: 3px; 
                    color: #e96900; 
                    padding: 2px 4px; 
                    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace; 
                    font-size: 0.85em; 
                }
                .markdown-container pre { 
                    background-color: #f6f8fa; 
                    border-radius: 8px; 
                    padding: 16px; 
                    overflow: auto; 
                    border: 1px solid #e1e4e8; 
                    line-height: 1.45; 
                }
                .markdown-container pre code { background: none; color: #24292e; padding: 0; }
                .markdown-container blockquote { 
                    background-color: #f3f5f7; 
                    border-left: 4px solid #3eaf7c; 
                    margin: 1em 0; 
                    padding: 1em 1.5em; 
                    border-radius: 0 4px 4px 0; 
                    color: #5d6d7e; 
                }
                .markdown-container table { 
                    border-collapse: collapse; 
                    width: 100%; 
                    margin: 1em 0; 
                    border-radius: 4px; 
                    overflow: hidden; 
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1); 
                }
                .markdown-container table th, 
                .markdown-container table td { 
                    border: 1px solid #dfe2e5; 
                    padding: 0.75em 1em; 
                    text-align: left; 
                }
                .markdown-container table th { 
                    background-color: #f6f8fa; 
                    font-weight: 600; 
                }
                .markdown-container table tr:nth-child(even) { 
                    background-color: #fafafa; 
                }
                .markdown-container img { 
                    max-width: 100%; 
                    border-radius: 4px; 
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
                }
                """
        
        else:  # Ant Design
            if is_dark:
                return """
                .markdown-container {
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
                    font-size: 14px;
                    line-height: 1.6;
                    color: rgba(255, 255, 255, 0.85);
                    background-color: #141414;
                    margin: 0;
                    padding: 20px;
                }
                .markdown-container h1, .markdown-container h2, .markdown-container h3, .markdown-container h4, .markdown-container h5, .markdown-container h6 {
                    color: rgba(255, 255, 255, 0.85);
                    font-weight: 500;
                    margin-top: 1.2em;
                    margin-bottom: 0.6em;
                }
                .markdown-container h1 { font-size: 28px; border-bottom: 1px solid #303030; padding-bottom: 0.2em; }
                .markdown-container h2 { font-size: 22px; }
                .markdown-container a { color: #177ddc; text-decoration: none; }
                .markdown-container a:hover { color: #3c9ae8; }
                .markdown-container code { 
                    background-color: rgba(255, 255, 255, 0.08); 
                    border: 1px solid rgba(255, 255, 255, 0.15); 
                    border-radius: 3px; 
                    color: #ff7875; 
                    padding: 1px 4px; 
                    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo; 
                    font-size: 0.9em; 
                }
                .markdown-container pre { 
                    background-color: #1f1f1f; 
                    border: 1px solid #303030; 
                    border-radius: 4px; 
                    padding: 12px 16px; 
                    overflow: auto; 
                }
                .markdown-container pre code { 
                    background: none; 
                    border: none; 
                    color: #d9d9d9; 
                    padding: 0; 
                }
                .markdown-container blockquote { 
                    background-color: rgba(24, 144, 255, 0.1); 
                    border-left: 3px solid #177ddc; 
                    margin: 1em 0; 
                    padding: 1em 1.5em; 
                    color: rgba(255, 255, 255, 0.65); 
                }
                .markdown-container table { 
                    border: 1px solid #303030; 
                    border-collapse: collapse; 
                    width: 100%; 
                    margin: 1em 0; 
                    border-radius: 4px; 
                    overflow: hidden; 
                }
                .markdown-container table th, 
                .markdown-container table td { 
                    border: 1px solid #303030; 
                    padding: 12px; 
                    text-align: left; 
                }
                .markdown-container table th { 
                    background-color: #1f1f1f; 
                    font-weight: 500; 
                }
                .markdown-container table tr:nth-child(even) { 
                    background-color: rgba(255, 255, 255, 0.03); 
                }
                .markdown-container img { max-width: 100%; border-radius: 4px; }
                """
            else:
                return """
                .markdown-container {
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
                    font-size: 14px;
                    line-height: 1.6;
                    color: rgba(0, 0, 0, 0.85);
                    background-color: #fafafa;
                    margin: 0;
                    padding: 20px;
                }
                .markdown-container h1, .markdown-container h2, .markdown-container h3, .markdown-container h4, .markdown-container h5, .markdown-container h6 {
                    color: rgba(0, 0, 0, 0.85);
                    font-weight: 500;
                    margin-top: 1.2em;
                    margin-bottom: 0.6em;
                }
                .markdown-container h1 { font-size: 28px; border-bottom: 1px solid #f0f0f0; padding-bottom: 0.2em; }
                .markdown-container h2 { font-size: 22px; }
                .markdown-container a { color: #1890ff; text-decoration: none; }
                .markdown-container a:hover { color: #40a9ff; }
                .markdown-container code { 
                    background-color: rgba(150, 150, 150, 0.1); 
                    border: 1px solid rgba(100, 100, 100, 0.2); 
                    border-radius: 3px; 
                    color: #e96900; 
                    padding: 1px 4px; 
                    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo; 
                    font-size: 0.9em; 
                }
                .markdown-container pre { 
                    background-color: #f6f8fa; 
                    border: 1px solid #e8e8e8; 
                    border-radius: 4px; 
                    padding: 12px 16px; 
                    overflow: auto; 
                }
                .markdown-container pre code { 
                    background: none; 
                    border: none; 
                    color: #262626; 
                    padding: 0; 
                }
                .markdown-container blockquote { 
                    background-color: rgba(24, 144, 255, 0.04); 
                    border-left: 3px solid #1890ff; 
                    margin: 1em 0; 
                    padding: 1em 1.5em; 
                    color: rgba(0, 0, 0, 0.65); 
                }
                .markdown-container table { 
                    border: 1px solid #f0f0f0; 
                    border-collapse: collapse; 
                    width: 100%; 
                    margin: 1em 0; 
                    border-radius: 4px; 
                    overflow: hidden; 
                }
                .markdown-container table th, 
                .markdown-container table td { 
                    border: 1px solid #f0f0f0; 
                    padding: 12px; 
                    text-align: left; 
                }
                .markdown-container table th { 
                    background-color: #fafafa; 
                    font-weight: 500; 
                }
                .markdown-container table tr:nth-child(even) { 
                    background-color: #fafafa; 
                }
                .markdown-container img { max-width: 100%; border-radius: 4px; }
                """
    
    def _get_highlight_css(self, theme_name: str) -> str:
        """获取代码高亮 CSS"""
        is_dark = "Dark" in theme_name
        
        if is_dark:
            return """
            .hljs { display: block; overflow-x: auto; padding: 0.5em; background: #282c34; color: #abb2bf; }
            .hljs-comment, .hljs-quote { color: #5c6370; font-style: italic; }
            .hljs-doctag, .hljs-keyword, .hljs-formula { color: #c678dd; }
            .hljs-section, .hljs-name, .hljs-selector-tag, .hljs-deletion, .hljs-subst { color: #e06c75; }
            .hljs-literal { color: #56b6c2; }
            .hljs-string, .hljs-regexp, .hljs-addition, .hljs-attribute, .hljs-meta .hljs-string { color: #98c379; }
            .hljs-attr, .hljs-variable, .hljs-template-variable, .hljs-type, .hljs-selector-class, .hljs-selector-attr, .hljs-selector-pseudo, .hljs-number { color: #d19a66; }
            .hljs-symbol, .hljs-bullet, .hljs-link, .hljs-meta, .hljs-selector-id, .hljs-title { color: #61aeee; }
            .hljs-built_in, .hljs-title.class_, .hljs-class .hljs-title { color: #e6c07b; }
            .hljs-emphasis { font-style: italic; }
            .hljs-strong { font-weight: bold; }
            .hljs-link { text-decoration: underline; }
            """
        else:
            return """
            .hljs { display: block; overflow-x: auto; padding: 0.5em; background: #f0f0f0; }
            .hljs-comment, .hljs-quote { color: #8e908c; }
            .hljs-variable, .hljs-template-variable, .hljs-tag, .hljs-name, .hljs-selector-id, .hljs-selector-class, .hljs-regexp, .hljs-deletion { color: #c82829; }
            .hljs-number, .hljs-built_in, .hljs-builtin-name, .hljs-literal, .hljs-type, .hljs-params, .hljs-meta, .hljs-link { color: #f5871f; }
            .hljs-attribute { color: #eab700; }
            .hljs-string, .hljs-symbol, .hljs-bullet, .hljs-addition { color: #718c00; }
            .hljs-title, .hljs-section { color: #4271ae; }
            .hljs-keyword, .hljs-selector-tag { color: #8959a8; }
            .hljs-emphasis { font-style: italic; }
            .hljs-strong { font-weight: bold; }
            """
    
    # ========== 公共 API ==========
    
    def set_markdown(self, text: str):
        """
        设置 Markdown 文本并立即渲染
        
        Args:
            text: Markdown 文本
        """
        self.render_markdown(text)
    
    def set_theme(self, theme_name: str):
        """
        设置主题
        
        Args:
            theme_name: 主题名称
        """
        if theme_name in self.THEMES:
            self.current_theme = theme_name
    
    def get_theme(self) -> str:
        """
        获取当前主题
        
        Returns:
            str: 当前主题名称
        """
        return self.current_theme
    
    def set_html_directly(self, html: str):
        """
        直接设置 HTML 内容（绕过 Markdown 转换）
        
        Args:
            html: HTML 内容
        """
        if self.web_view is not None:
            self.web_view.setHtml(html)
    
    def is_webengine_available(self) -> bool:
        """
        检查 WebEngine 是否可用
        
        Returns:
            bool: 是否可用
        """
        return WEBENGINE_AVAILABLE
    
    def get_web_view(self):
        """
        获取 WebView 控件
        
        Returns:
            QWebEngineView: WebView 控件
        """
        return self.web_view
    
    def clear(self):
        """清空内容"""
        if self.web_view is not None:
            self.web_view.setHtml("")
    
    def refresh(self):
        """刷新预览"""
        if self.web_view is not None:
            # 重新加载当前页面
            self.web_view.reload()