# ui/components/modern_md_viewer.py
"""
现代 Markdown 预览器组件
精简版，只包含核心预览功能
"""

import markdown
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QSplitter, QLabel
from PyQt6.QtGui import QFont, QFontDatabase
from typing import Optional

# 延迟导入 WebEngine
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    WEBENGINE_AVAILABLE = True
except ImportError:
    WEBENGINE_AVAILABLE = False


class ModernMDViewer(QWidget):
    """
    现代 Markdown 预览器（精简版）
    只包含编辑器+预览器，适合嵌入其他界面
    """
    
    # 信号
    contentChanged = pyqtSignal(str)
    
    # 主题定义
    THEMES = {
        "GitHub Light": "github-light",
        "GitHub Dark": "github-dark", 
        "VuePress Light": "vuepress-light",
        "VuePress Dark": "vuepress-dark",
        "Ant Design Light": "antd-light",
        "Ant Design Dark": "antd-dark"
    }
    
    def __init__(self, 
                 parent=None, 
                 initial_theme: str = "GitHub Light",
                 show_editor: bool = True,
                 split_ratio: tuple = (400, 600)):
        """
        初始化 Markdown 预览器
        
        Args:
            parent: 父组件
            initial_theme: 初始主题
            show_editor: 是否显示编辑器
            split_ratio: 分割比例 (编辑器, 预览器)
        """
        super().__init__(parent)
        
        # 成员变量
        self.current_theme = initial_theme
        self.show_editor = show_editor
        self.split_ratio = split_ratio
        self.monospace_font = self._get_monospace_font()
        
        # 初始化 UI
        self.setup_ui()
        
    def _get_monospace_font(self, size: int = 11) -> QFont:
        """获取可用的等宽字体"""
        font_candidates = [
            "SF Mono", "Menlo", "Monaco",  # macOS
            "Consolas", "Cascadia Code",   # Windows
            "Ubuntu Mono", "DejaVu Sans Mono",  # Linux
            "Courier New", "Courier",      # 通用
            "monospace"                    # 最后回退
        ]
        
        try:
            available_fonts = QFontDatabase.families()
        except:
            available_fonts = []
        
        for font_name in font_candidates:
            if font_name in available_fonts or font_name == "monospace":
                font = QFont(font_name, size)
                font.setStyleHint(QFont.StyleHint.TypeWriter)
                return font
        
        font = QFont()
        font.setFamily("monospace")
        font.setPointSize(size)
        return font
    
    def setup_ui(self):
        """初始化用户界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        if self.show_editor:
            # 创建分割器
            splitter = QSplitter(Qt.Orientation.Horizontal)
            
            # 左侧编辑器
            self.editor = QTextEdit()
            self.editor.setFont(self.monospace_font)
            self.editor.setStyleSheet("""
                QTextEdit {
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    padding: 8px;
                    background-color: #f8f9fa;
                }
            """)
            self.editor.textChanged.connect(self._on_content_changed)
            
            # 右侧预览
            self.preview_container = QWidget()
            preview_layout = QVBoxLayout(self.preview_container)
            preview_layout.setContentsMargins(0, 0, 0, 0)
            
            if WEBENGINE_AVAILABLE:
                self.web_view = QWebEngineView()
                self._setup_webengine_settings()
                preview_layout.addWidget(self.web_view)
            else:
                self.web_view = None
                placeholder = QLabel("WebEngine 不可用")
                placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
                preview_layout.addWidget(placeholder)
            
            splitter.addWidget(self.editor)
            splitter.addWidget(self.preview_container)
            splitter.setSizes(list(self.split_ratio))
            
            layout.addWidget(splitter)
        else:
            # 只显示预览
            if WEBENGINE_AVAILABLE:
                self.web_view = QWebEngineView()
                self._setup_webengine_settings()
                layout.addWidget(self.web_view)
            else:
                self.web_view = None
                placeholder = QLabel("WebEngine 不可用")
                placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
                layout.addWidget(placeholder)
            
            # 如果没有编辑器，创建一个隐藏的文本编辑区域
            self.editor = QTextEdit()
            self.editor.setVisible(False)
    
    def _setup_webengine_settings(self):
        """设置 WebEngine 参数"""
        if self.web_view is None:
            return
            
        try:
            settings = self.web_view.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        except:
            pass
    
    def _on_content_changed(self):
        """编辑器内容变化"""
        self.render_markdown()
        self.contentChanged.emit(self.get_markdown())
    
    def render_markdown(self):
        """渲染 Markdown"""
        if self.web_view is None:
            return
            
        try:
            md_text = self.editor.toPlainText()
            
            # 转换 Markdown
            html_content = markdown.markdown(
                md_text,
                extensions=[
                    'extra', 'codehilite', 'tables', 
                    'toc', 'fenced_code', 'nl2br'
                ],
                extension_configs={
                    'codehilite': {
                        'css_class': 'highlight',
                        'guess_lang': True,
                        'use_pygments': True
                    }
                }
            )
            
            # 生成完整 HTML
            full_html = self._generate_html(html_content, self.current_theme)
            self.web_view.setHtml(full_html)
            
        except Exception as e:
            print(f"Markdown 渲染错误: {e}")
    
    def _generate_html(self, content: str, theme_name: str) -> str:
        """生成完整的 HTML 页面"""
        css = self._get_theme_css(theme_name)
        
        return f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>{css}</style>
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
                    font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
                    font-size: 16px;
                    line-height: 1.6;
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
                .markdown-container a { color: #58a6ff; }
                .markdown-container code { 
                    background-color: rgba(110,118,129,0.4); 
                    border-radius: 6px; 
                    padding: 0.2em 0.4em; 
                }
                .markdown-container pre { 
                    background-color: #161b22; 
                    border-radius: 6px; 
                    padding: 16px; 
                    overflow: auto; 
                }
                .markdown-container table { border-collapse: collapse; }
                .markdown-container th, .markdown-container td { 
                    border: 1px solid #30363d; 
                    padding: 6px 13px; 
                }
                """
            else:
                return """
                .markdown-container {
                    font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
                    font-size: 16px;
                    line-height: 1.6;
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
                .markdown-container a { color: #0969da; }
                .markdown-container code { 
                    background-color: #f6f8fa; 
                    border-radius: 6px; 
                    padding: 0.2em 0.4em; 
                }
                .markdown-container pre { 
                    background-color: #f6f8fa; 
                    border-radius: 6px; 
                    padding: 16px; 
                    overflow: auto; 
                }
                .markdown-container table { border-collapse: collapse; }
                .markdown-container th, .markdown-container td { 
                    border: 1px solid #d0d7de; 
                    padding: 6px 13px; 
                }
                """
        
        elif "VuePress" in theme_name:
            if is_dark:
                return """
                .markdown-container {
                    font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Oxygen,Ubuntu,sans-serif;
                    font-size: 16px;
                    line-height: 1.6;
                    color: #adbac7;
                    background-color: #1c2128;
                    margin: 0;
                    padding: 20px;
                }
                .markdown-container h1, .markdown-container h2 {
                    border-bottom: 1px solid #373e47;
                    padding-bottom: 0.3em;
                }
                .markdown-container a { color: #539bf5; }
                .markdown-container code { 
                    background-color: rgba(99,110,123,0.4); 
                    color: #f47067; 
                    padding: 2px 4px; 
                }
                .markdown-container pre { 
                    background-color: #2d333b; 
                    border-radius: 8px; 
                    padding: 16px; 
                }
                """
            else:
                return """
                .markdown-container {
                    font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Oxygen,Ubuntu,sans-serif;
                    font-size: 16px;
                    line-height: 1.6;
                    color: #2c3e50;
                    background-color: #fff;
                    margin: 0;
                    padding: 20px;
                }
                .markdown-container h1, .markdown-container h2 {
                    border-bottom: 1px solid #eaecef;
                    padding-bottom: 0.3em;
                }
                .markdown-container a { color: #3eaf7c; }
                .markdown-container code { 
                    background-color: #f8f8f8; 
                    color: #e96900; 
                    padding: 2px 4px; 
                }
                .markdown-container pre { 
                    background-color: #f6f8fa; 
                    border-radius: 8px; 
                    padding: 16px; 
                }
                """
        
        else:  # Ant Design
            if is_dark:
                return """
                .markdown-container {
                    font-family: -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
                    font-size: 14px;
                    line-height: 1.6;
                    color: rgba(255,255,255,0.85);
                    background-color: #141414;
                    margin: 0;
                    padding: 20px;
                }
                .markdown-container h1, .markdown-container h2 {
                    border-bottom: 1px solid #303030;
                    padding-bottom: 0.2em;
                }
                .markdown-container a { color: #177ddc; }
                .markdown-container code { 
                    background-color: rgba(255,255,255,0.08); 
                    color: #ff7875; 
                    padding: 1px 4px; 
                }
                .markdown-container pre { 
                    background-color: #1f1f1f; 
                    border-radius: 4px; 
                    padding: 12px 16px; 
                }
                """
            else:
                return """
                .markdown-container {
                    font-family: -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
                    font-size: 14px;
                    line-height: 1.6;
                    color: rgba(0,0,0,0.85);
                    background-color: #fafafa;
                    margin: 0;
                    padding: 20px;
                }
                .markdown-container h1, .markdown-container h2 {
                    border-bottom: 1px solid #f0f0f0;
                    padding-bottom: 0.2em;
                }
                .markdown-container a { color: #1890ff; }
                .markdown-container code { 
                    background-color: rgba(150,150,150,0.1); 
                    color: #e96900; 
                    padding: 1px 4px; 
                }
                .markdown-container pre { 
                    background-color: #f6f8fa; 
                    border-radius: 4px; 
                    padding: 12px 16px; 
                }
                """
    
    # ========== 公共 API ==========
    
    def set_markdown(self, text: str):
        """
        设置 Markdown 文本
        
        Args:
            text: Markdown 文本
        """
        self.editor.setPlainText(text)
        self.render_markdown()
    
    def get_markdown(self) -> str:
        """
        获取当前 Markdown 文本
        
        Returns:
            str: Markdown 文本
        """
        return self.editor.toPlainText()
    
    def set_theme(self, theme_name: str):
        """
        设置主题
        
        Args:
            theme_name: 主题名称
        """
        if theme_name in self.THEMES:
            self.current_theme = theme_name
            self.render_markdown()
    
    def get_theme(self) -> str:
        """
        获取当前主题
        
        Returns:
            str: 当前主题名称
        """
        return self.current_theme
    
    def clear(self):
        """清空内容"""
        self.editor.clear()
        self.render_markdown()
    
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
    
    def get_editor_widget(self) -> QTextEdit:
        """
        获取编辑器控件
        
        Returns:
            QTextEdit: 编辑器控件
        """
        return self.editor
    
    def get_preview_widget(self) -> QWidget:
        """
        获取预览控件
        
        Returns:
            QWidget: 预览控件
        """
        if WEBENGINE_AVAILABLE and self.web_view is not None:
            return self.web_view
        return self.preview_container

