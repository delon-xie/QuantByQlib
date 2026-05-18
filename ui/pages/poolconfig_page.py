"""
股票池配置页面
- 从 Qlib instruments/ 目录读取股票列表
- LLM 智能筛选股票
- 管理自定义股票池
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Optional, Pattern
from re import Pattern as re_Pattern

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QPlainTextEdit, QGroupBox, QLineEdit,
    QMessageBox, QScrollArea, QFrame, QProgressBar, QSplitter
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from core.app_state import get_state
from ui.components.instrument_combobox import InstrumentComboBox
from loguru import logger

# 导入注册表名称映射
try:
    from core.qlibhelper import (
        REG_CN_NAME, REG_US_NAME, REG_TW_NAME, REG_HK_NAME,
        REG_JP_NAME, REG_KR_NAME, REG_BT_NAME
    )
    
    # 注册表代码到名称的映射
    REG_NAME_MAP = {
        "cn": REG_CN_NAME,
        "us": REG_US_NAME,
        "tw": REG_TW_NAME,
        "hk": REG_HK_NAME,
        "jp": REG_JP_NAME,
        "kr": REG_KR_NAME,
        "bt": REG_BT_NAME
    }
except ImportError:
    # 如果无法导入，使用默认映射
    REG_NAME_MAP = {
        "cn": "A股",
        "us": "美股",
        "tw": "台股",
        "hk": "港股",
        "jp": "日股",
        "kr": "韩股",
        "bt": "Crypto"
    }

# 市场代码格式验证规则
MARKET_RULES: dict[str, Pattern] = {
    "cn": re.compile(r"^(sh|sz|bj)\d{6}$"),           # A 股: sh600000, sz000001, bj430090
    "hk": re.compile(r"^\d{4,5}\.HK$"),               # 港股: 0700.HK, 09988.HK
    "tw": re.compile(r"^\d{4}\.TW$"),                 # 台股: 2330.TW
    "jp": re.compile(r"^\d{4}\.T$"),                  # 日股: 6758.T
    "kr": re.compile(r"^\d{6}\.(KS|KQ)$"),           # 韩股: 005930.KS, 035720.KQ
    "us": re.compile(r"^[A-Z]+([-.][A-Z0-9]+)?$"),    # 美股: AAPL, MSFT, BRK-B
    "bt": re.compile(r"^[A-Z]+$"),                    # Crypto: BTC, ETH, SOL
}


class LLMTicksGenerator(QThread):
    """LLM 股票代码生成器线程"""
    
    progress = pyqtSignal(str)
    result_ready = pyqtSignal(list)
    error_occured = pyqtSignal(str)
    
    def __init__(self, prompt: str, all_tickers: List[str], reg_code: str):
        super().__init__()
        self.prompt = prompt
        self.all_tickers = all_tickers
        self.reg_code = reg_code
        self.reg_name = REG_NAME_MAP.get(reg_code, reg_code.upper())
        self._cancelled = False
        self.reg = get_state().reg
        
    def run(self):
        """调用 LLM 生成股票代码"""
        try:
            self.progress.emit(f"正在连接 LLM 生成 {self.reg_name} 股票清单...")
            
            # 限制处理数量
            max_tickers = 5000
            if len(self.all_tickers) > max_tickers:
                tickers_sample = self.all_tickers[:max_tickers]
            else:
                tickers_sample = self.all_tickers
                
            # 构建 LLM 提示
            llm_prompt = self._build_llm_prompt(tickers_sample)
            
            # 调用 LLM API
            generated_tickers = self._call_llm_api(llm_prompt)
            
            if self._cancelled:
                return
                
            if generated_tickers:
                # 验证生成的股票代码是否符合格式规范
                valid_tickers = self._validate_and_format_tickers(generated_tickers)
                
                if valid_tickers:
                    self.result_ready.emit(valid_tickers)
                    self.progress.emit(f"成功生成 {len(valid_tickers)} 支有效的 {self.reg_name} 股票")
                else:
                    self.error_occured.emit(f"未生成有效的 {self.reg_name} 股票代码")
            else:
                self.error_occured.emit("LLM 未返回有效股票代码")
                
        except Exception as e:
            logger.error(f"LLM生成{self.reg_name}股票失败: {e}")
            self.error_occured.emit(f"生成失败: {str(e)}")
            
    def _validate_and_format_tickers(self, tickers: List[str]) -> List[str]:
        """验证和格式化股票代码，使其符合 MARKET_RULES 格式"""
        from core.qlibhelper import _normalize_ticker
        
        valid_tickers = []
        invalid_count = 0
        
        for ticker in tickers:
            # 清理和标准化
            ticker_clean = ticker.strip().upper()
            
            # 根据市场类型进行格式化
            formatted_ticker = self._format_ticker_for_market(ticker_clean)
            
            if formatted_ticker:
                # 验证格式
                if self._validate_ticker_format(formatted_ticker):
                    # 检查是否在可用股票列表中
                    if formatted_ticker in self.all_tickers:
                        logger.warning(f"股票代码已在 {self.reg_name} 列表中: {formatted_ticker}")
                        invalid_count += 1
                    else:
                        valid_tickers.append(formatted_ticker)
                else:
                    logger.warning(f"股票代码格式不正确: {ticker_clean} -> {formatted_ticker}")
                    invalid_count += 1
            else:
                invalid_count += 1
                logger.warning(f"无法格式化股票代码: {ticker_clean}")
        
        if invalid_count > 0:
            logger.info(f"过滤掉 {invalid_count} 个不符合格式规范的股票代码，有效股票数{len(valid_tickers)}")
            
        return valid_tickers
    
    def _format_ticker_for_market(self, ticker: str) -> Optional[str]:
        """根据市场类型格式化股票代码"""
        if self.reg_code == "cn":
            # A股: 标准化为小写
            ticker = ticker.lower()
            if ticker.startswith(("sh", "sz", "bj")):
                return ticker
            elif ticker.startswith(("600", "601", "603", "605", "688")):
                return f"sh{ticker}"
            elif ticker.startswith(("000", "001", "002", "003", "300")):
                return f"sz{ticker}"
            elif ticker.startswith(("430", "830", "870", "830")):
                return f"bj{ticker}"
                
        elif self.reg_code == "hk":
            # 港股: 确保有 .HK 后缀
            ticker = ticker.replace(".HK", "").replace(".hk", "")
            if ticker.isdigit() and 4 <= len(ticker) <= 5:
                return f"{ticker}.HK"
                
        elif self.reg_code == "tw":
            # 台股: 确保有 .TW 后缀
            ticker = ticker.replace(".TW", "").replace(".tw", "")
            if ticker.isdigit() and len(ticker) == 4:
                return f"{ticker}.TW"
                
        elif self.reg_code == "jp":
            # 日股: 确保有 .T 后缀
            ticker = ticker.replace(".T", "").replace(".t", "")
            if ticker.isdigit() and len(ticker) == 4:
                return f"{ticker}.T"
                
        elif self.reg_code == "kr":
            # 韩股: 确保有 .KS 或 .KQ 后缀
            if ticker.endswith((".KS", ".KQ", ".ks", ".kq")):
                return ticker.upper()
            elif ticker.isdigit() and len(ticker) == 6:
                # 默认使用 .KS 后缀
                return f"{ticker}.KS"
                
        elif self.reg_code == "us":
            # 美股: 保持原样，但确保大写
            return ticker.upper()
            
        elif self.reg_code == "bt":
            # Crypto: 保持原样，但确保大写
            return ticker.upper()
            
        return None
    
    def _validate_ticker_format(self, ticker: str) -> bool:
        """验证股票代码格式"""
        if self.reg_code in MARKET_RULES:
            return bool(MARKET_RULES[self.reg_code].match(ticker))
        return False
            
    def _build_llm_prompt(self, tickers: List[str]) -> str:
        """构建 LLM 提示词"""
        tickers_str = "\n".join(tickers[:100])  # 限制为前100个示例
        
        # 根据市场类型调整提示
        market_hint = self._get_market_hint()
        format_examples = self._get_format_examples()
        
        prompt = f"""你是一位专业的{self.reg_name}股票分析师。请根据以下需求筛选股票代码：

市场：{self.reg_name}
需求：{self.prompt}
{market_hint}

请严格按照以下格式返回：
1. 只返回股票代码，每行一个
2. 使用标准格式：{format_examples}
3. 最多返回300个股票代码
4. 不要包含任何解释、说明、标点符号或其他文本
5. 只返回示例列表中存在的股票代码

请筛选出最符合需求的股票代码："""
        
        return prompt
        
    def _get_market_hint(self) -> str:
        """根据市场类型返回提示"""
        if self.reg_code == "cn":
            return "注意：这是A股市场，使用标准格式：sh600000（上证）、sz000001（深证）、bj430090（北证）"
        elif self.reg_code == "us":
            return "注意：这是美股市场，使用标准格式：AAPL、MSFT、BRK-B"
        elif self.reg_code == "hk":
            return "注意：这是港股市场，使用标准格式：0700.HK、09988.HK"
        elif self.reg_code == "tw":
            return "注意：这是台股市场，使用标准格式：2330.TW"
        elif self.reg_code == "jp":
            return "注意：这是日股市场，使用标准格式：6758.T"
        elif self.reg_code == "kr":
            return "注意：这是韩股市场，使用标准格式：005930.KS（主板）、035720.KQ（创业板）"
        elif self.reg_code == "bt":
            return "注意：这是加密货币市场，使用标准格式：BTC、ETH、SOL"
        else:
            return ""
    
    def _get_format_examples(self) -> str:
        """根据市场类型返回格式示例"""
        if self.reg_code == "cn":
            return "sh600000、sz000001、bj430090"
        elif self.reg_code == "us":
            return "AAPL、MSFT、BRK-B"
        elif self.reg_code == "hk":
            return "0700.HK、09988.HK"
        elif self.reg_code == "tw":
            return "2330.TW"
        elif self.reg_code == "jp":
            return "6758.T"
        elif self.reg_code == "kr":
            return "005930.KS、035720.KQ"
        elif self.reg_code == "bt":
            return "BTC、ETH、SOL"
        else:
            return ""
        
    def _call_llm_api(self, prompt: str) -> List[str]:
        """调用 LLM API 生成股票代码"""
        try:
            # 尝试使用 Claude API
            if "ANTHROPIC_API_KEY" in os.environ and os.environ["ANTHROPIC_API_KEY"]:
                return self._call_claude_api(prompt)
            # 尝试使用 DeepSeek API
            elif "DEEPSEEK_API_KEY" in os.environ and os.environ["DEEPSEEK_API_KEY"]:
                return self._call_deepseek_api(prompt)
            else:
                raise ValueError("未配置任何 LLM API Key")
                
        except Exception as e:
            raise Exception(f"LLM API 调用失败: {str(e)}")
            
    def _call_claude_api(self, prompt: str) -> List[str]:
        """调用 Claude API"""
        try:
            import anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key or api_key.startswith("your_"):
                raise ValueError("ANTHROPIC_API_KEY 未正确配置")
                
            client = anthropic.Anthropic(api_key=api_key)
            
            response = client.messages.create(
                model="claude-3-haiku-20240307",  # 使用轻量模型
                max_tokens=2000,
                temperature=0.1,  # 低温度确保格式准确
                system=f"你是一位专业的{self.reg_name}股票分析师，严格按照指定格式输出。",
                messages=[{"role": "user", "content": prompt}]
            )
            
            content = response.content[0].text
            return self._parse_llm_response(content)
            
        except ImportError:
            raise ImportError("请安装 anthropic: pip install anthropic")
        except Exception as e:
            raise Exception(f"Claude API 错误: {str(e)}")
            
    def _call_deepseek_api(self, prompt: str) -> List[str]:
        """调用 DeepSeek API"""
        try:
            import openai
            api_key = os.environ.get("DEEPSEEK_API_KEY")
            if not api_key or api_key.startswith("sk-") == False:
                raise ValueError("DEEPSEEK_API_KEY 未正确配置")
                
            client = openai.OpenAI(
                api_key=api_key,
                base_url="https://api.deepseek.com"
            )
            
            try:
                response = client.chat.completions.create(
                    model="deepseek-v4-flash",
                    max_tokens=5000,
                    temperature=0.1,
                    messages=[
                        {"role": "system", "content": f"你是一位专业的{self.reg_name}股票分析师，严格按照指定格式输出。"},
                        {"role": "user", "content": prompt}
                    ]
                )
            except Exception as api_error:
                logger.error(f"DeepSeek API 调用失败: {api_error}")
                raise Exception(f"API 调用失败: {str(api_error)}")
            
            # 安全地提取内容
            if not response or not hasattr(response, 'choices'):
                logger.error(f"API 返回格式异常: {response}")
                return []
                
            if not response.choices:
                logger.warning("API 返回空 choices")
                return []
                
            logger.info(f"message:{response}")
            message = response.choices[0].message
            if not message or not hasattr(message, 'content'):
                logger.error(f"API 返回消息格式异常: {message}")
                return []
                
            content = message.content
            if content is None:
                logger.warning("API 返回内容为 None")
                return []
                
            if not isinstance(content, str):
                logger.warning(f"API 返回内容类型错误: {type(content)}, 值: {content}")
                try:
                    content = str(content)
                except Exception as e:
                    logger.error(f"无法转换内容为字符串: {e}")
                    return []
            
            return self._parse_llm_response(content)
            
        except ImportError:
            raise ImportError("请安装 openai: pip install openai")
        except Exception as e:
            # 不包含内部异常详情
            raise Exception(f"DeepSeek API 错误: {str(e)}")
            
    def _parse_llm_response(self, response: str) -> List[str]:
        """解析 LLM 返回的文本，提取股票代码"""
        logger.info(response)
        tickers = []
        lines = response.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if line:
                tickers.append(line)
        
        # 限制最多200个
        if len(tickers) > 200:
            tickers = tickers[:200]
            
        return tickers
        
    def cancel(self):
        """取消生成"""
        self._cancelled = True


class PoolConfigPage(QWidget):
    """股票池配置页面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = get_state()
        self.reg = get_state().reg
        self.reg_code = self.reg.lower()  # 转换为小写以匹配注册表代码
        self.reg_name = REG_NAME_MAP.get(self.reg_code, self.reg.upper())
        self._llm_worker = None
        self._his_current_name = None
        self._current_name = None
        self._available_tickers = []
        self._setup_ui()
        #self._load_available_tickers()
        
    def _setup_ui(self) -> None:
        """设置UI界面"""
        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # 标题区域
        title_layout = QHBoxLayout()
        title = QLabel(f"📊 {self.reg_name}股票池配置")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        title_layout.addWidget(title)
        title_layout.addStretch()
        main_layout.addLayout(title_layout)
        
        # 创建分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # ── 左侧筛选区 ─────────────────────────────────
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(5, 5, 5, 5)
        left_layout.setSpacing(10)
        
        # 基础股票池选择
        source_group = QGroupBox(f"{self.reg_name}股票池模版")
        source_group.setMinimumHeight(150)
        source_layout = QVBoxLayout(source_group)
        
        source_help = QLabel(
            f"选择{self.reg_name}股票池模版文件，系统将从注册表 ({self.reg_code}) 中读取股票列表作为模版，初始化股票池编辑器。"
        )
        source_help.setStyleSheet("color: #666; font-size: 12px;")
        source_help.setWordWrap(True)
        source_layout.addWidget(source_help)
        
        # 使用 InstrumentComboBox
        self._source_combo = InstrumentComboBox()
        self._source_combo.setMinimumHeight(36)
        self._source_combo.setCurrentText("all")
        self._source_combo.currentTextChanged.connect(self._on_source_changed)
        source_layout.addWidget(self._source_combo)
        
        # 基础股票池信息
        self._source_info = QLabel("未选择股票池")
        self._source_info.setStyleSheet("color: #888; font-size: 12px;")
        source_layout.addWidget(self._source_info)
        
        # 注册表信息
        reg_label = QLabel(f"当前市场：{self.reg_name} ({self.reg_code})")
        reg_label.setStyleSheet("color: #666; font-size: 11px; font-style: italic;")
        source_layout.addWidget(reg_label)
        
        left_layout.addWidget(source_group)
        
        # LLM 智能筛选
        llm_group = QGroupBox(f"{self.reg_name} LLM 智能筛选")
        llm_group.setMinimumHeight(350)
        llm_layout = QVBoxLayout(llm_group)
        
        # 需求输入
        prompt_label = QLabel(f"{self.reg_name}筛选需求：")
        prompt_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        llm_layout.addWidget(prompt_label)
        
        # 根据市场类型提供不同的示例
        examples = self._get_market_examples()
        format_info = self._get_format_info()
        
        prompt_help = QLabel(
            f"用一句话描述您需要的{self.reg_name}股票筛选条件，例如：\n"
            f"{examples}\n\n"
            f"股票代码格式：{format_info}\n"
            f"注：LLM 将基于{self.reg_name}注册表 ({self.reg_code}) 中的股票列表进行筛选。"
        )
        prompt_help.setStyleSheet("color: #666; font-size: 12px;")
        prompt_help.setWordWrap(True)
        llm_layout.addWidget(prompt_help)
        
        self._prompt_input = QLineEdit()
        self._prompt_input.setPlaceholderText(f"请输入{self.reg_name}筛选需求描述...")
        self._prompt_input.setMinimumHeight(90)
        llm_layout.addWidget(self._prompt_input)
        
        # 生成进度
        self._generate_progress = QProgressBar()
        self._generate_progress.setVisible(False)
        llm_layout.addWidget(self._generate_progress)
        
        self._generate_status = QLabel("")
        self._generate_status.setStyleSheet("color: #666; font-size: 12px;")
        self._generate_status.setWordWrap(True)
        llm_layout.addWidget(self._generate_status)
        
        # 生成按钮
        btn_layout = QHBoxLayout()
        
        self._generate_btn = QPushButton(f"🤖 {self.reg_name} LLM 智能筛选")
        self._generate_btn.setMinimumHeight(40)
        self._generate_btn.clicked.connect(self._on_generate_clicked)
        btn_layout.addWidget(self._generate_btn)
        
        self._cancel_btn = QPushButton("⏹ 取消")
        self._cancel_btn.setObjectName("btn_danger")
        self._cancel_btn.setMinimumHeight(40)
        self._cancel_btn.setVisible(False)
        self._cancel_btn.clicked.connect(self._on_cancel_generate)
        btn_layout.addWidget(self._cancel_btn)
        
        btn_layout.addStretch()
        llm_layout.addLayout(btn_layout)
        
        left_layout.addWidget(llm_group)
        
        # 添加伸缩项，确保内容顶部对齐
        left_layout.addStretch()
        
        # ── 右侧编辑区 ───────────────────────────────────
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 5, 5, 5)
        right_layout.setSpacing(10)
        
        # 股票池编辑
        edit_group = QGroupBox(f"{self.reg_name}股票池编辑")
        edit_layout = QVBoxLayout(edit_group)
        
        # 股票池名称输入
        name_layout = QHBoxLayout()
        name_label = QLabel("股票池名称：")
        name_label.setFixedWidth(200)
        name_label.setStyleSheet("font-weight: bold;")
        name_layout.addWidget(name_label)
        
        self._pool_name_input = QLineEdit()
        self._pool_name_input.setPlaceholderText(f"输入{self.reg_name}股票池名称，将保存为 {{名称}}.txt 文件")
        self._pool_name_input.textChanged.connect(self._update_save_button_state)
        name_layout.addWidget(self._pool_name_input)
        edit_layout.addLayout(name_layout)
        
        # 股票代码编辑框
        self._ticker_edit = QPlainTextEdit()
        
        # 根据市场类型设置不同的占位符
        placeholder = self._get_edit_placeholder()
        self._ticker_edit.setPlaceholderText(placeholder)
        edit_layout.addWidget(self._ticker_edit)
        
        # 统计信息和操作按钮
        bottom_layout = QHBoxLayout()
        
        # 统计信息
        self._stats_label = QLabel(f"{self.reg_name}股票数量：0")
        self._stats_label.setStyleSheet("color: #666; font-size: 12px;")
        bottom_layout.addWidget(self._stats_label)
        
        bottom_layout.addStretch()
        
        # 操作按钮
        self._add_btn = QPushButton(f"➕ 添加{self.reg_name}股票")
        self._add_btn.setMinimumHeight(32)
        self._add_btn.clicked.connect(self._on_add_clicked)
        self._add_btn.setToolTip(f"手动添加{self.reg_name}股票代码")
        bottom_layout.addWidget(self._add_btn)
        
        self._format_btn = QPushButton(f"🔧 格式化")
        self._format_btn.setObjectName("btn_secondary")
        self._format_btn.setMinimumHeight(32)
        self._format_btn.clicked.connect(self._on_format_clicked)
        self._format_btn.setToolTip(f"格式化股票代码并验证{self.reg_name}注册表")
        bottom_layout.addWidget(self._format_btn)
        
        self._clear_btn = QPushButton("🗑️ 清空")
        self._clear_btn.setObjectName("btn_danger")
        self._clear_btn.setMinimumHeight(32)
        self._clear_btn.clicked.connect(self._on_clear_clicked)
        self._clear_btn.setToolTip("清空股票池")
        bottom_layout.addWidget(self._clear_btn)
        
        self._save_btn = QPushButton("💾 保存")
        self._save_btn.setMinimumHeight(32)
        self._save_btn.clicked.connect(self._on_save_clicked)
        self._save_btn.setEnabled(False)  # 初始禁用
        self._save_btn.setToolTip(f"保存{self.reg_name}股票池到文件")
        bottom_layout.addWidget(self._save_btn)
        
        edit_layout.addLayout(bottom_layout)
        
        right_layout.addWidget(edit_group)
        
        # 将左右部件添加到分割器
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        
        # 设置初始比例 360:640
        total_width = 1000  # 假设初始总宽度为1000
        left_width = int(total_width * 360 / 1000)
        right_width = int(total_width * 640 / 1000)
        splitter.setSizes([left_width, right_width])
        
        # 设置最小宽度
        left_widget.setMinimumWidth(200)
        right_widget.setMinimumWidth(400)
        
        main_layout.addWidget(splitter)
        
    def _get_market_examples(self) -> str:
        """根据市场类型返回示例"""
        if self.reg_code == "cn":
            return "- 沪深300指数成分股\n- 科技行业龙头股\n- 高分红价值股\n- 新能源板块股票"
        elif self.reg_code == "us":
            return "- 纳斯达克100指数成分股\n- FAANG科技股\n- 生物科技龙头股\n- 半导体行业股票"
        elif self.reg_code == "hk":
            return "- 恒生指数成分股\n- 互联网龙头股\n- 内房股\n- 金融板块股票"
        elif self.reg_code == "tw":
            return "- 台湾50指数成分股\n- 半导体龙头股\n- 电子产业股票\n- 金融股"
        elif self.reg_code == "jp":
            return "- 日经225指数成分股\n- 汽车制造业股票\n- 电子行业龙头\n- 医药股"
        elif self.reg_code == "kr":
            return "- KOSPI指数成分股\n- 三星系股票\n- 半导体板块\n- 汽车制造业"
        elif self.reg_code == "bt":
            return "- 主流加密货币\n- DeFi代币\n- Layer1公链\n- 稳定币"
        else:
            return "- 指数成分股\n- 行业龙头股\n- 价值股\n- 成长股"
    
    def _get_format_info(self) -> str:
        """返回股票代码格式信息"""
        if self.reg_code == "cn":
            return "sh600000（上证）、sz000001（深证）、bj430090（北证）"
        elif self.reg_code == "us":
            return "AAPL、MSFT、BRK-B"
        elif self.reg_code == "hk":
            return "0700.HK、09988.HK"
        elif self.reg_code == "tw":
            return "2330.TW"
        elif self.reg_code == "jp":
            return "6758.T"
        elif self.reg_code == "kr":
            return "005930.KS（主板）、035720.KQ（创业板）"
        elif self.reg_code == "bt":
            return "BTC、ETH、SOL"
        else:
            return ""
            
    def _get_edit_placeholder(self) -> str:
        """根据市场类型返回编辑框占位符"""
        format_info = self._get_format_info()
        return f"在此编辑{self.reg_name}股票代码，每行一个\n格式示例：{format_info}\n注意：股票代码会自动验证格式并去重"
        
    def _load_available_tickers(self, current_scope:str) -> None:
        """从注册表加载可用股票列表"""
        #current_scope = self._source_combo.currentText(current_scope)
        self._available_tickers = self._source_combo._get_tickers(current_scope)
        
        if self._available_tickers is None or len(self._available_tickers) < 1 or current_scope is None or len(current_scope) == 0:
            logger.info(f"从{self.reg_name}注册表加载,{current_scope}池 0 支股票，可能加载失败或没有成分股")
            self._source_info.setText("加载失败")
            return
        
        self._source_info.setText(f"已从{self.reg_name}加载 {len(self._available_tickers)} 支股票")
        
        # 自动设置股票池名称
        if current_scope and current_scope != "all":
            self._pool_name_input.setText(f"{self.reg_code}_{current_scope}")
            
    def _on_source_changed(self, text: str) -> None:
        """基础股票池变更处理"""
        
        if text and self._current_name and len(self._current_name) > 0:
            self._his_current_name = self._current_name
            self._current_name = text
            self._load_available_tickers(text)
            
            # 自动更新股票池名称
            current_name = self._pool_name_input.text().strip()
            if not current_name or current_name.startswith(f"user_{self.reg_code}_"):
                self._pool_name_input.setText(f"user_{self.reg_code}_{text}")
            
            if self._available_tickers and len(self._available_tickers) >0:
                self._ticker_edit.setPlainText("")
                self._add_tickers_to_edit(self._available_tickers)
            else:
                logger.info("模版为空")
        else:
            self._current_name = text #初次设置 all, 不加载数据
                    
    def _update_save_button_state(self) -> None:
        """更新保存按钮状态"""
        has_tickers = bool(self._ticker_edit.toPlainText().strip())
        has_name = bool(self._pool_name_input.text().strip())
        self._save_btn.setEnabled(has_tickers and has_name)
            
    def _on_generate_clicked(self) -> None:
        """点击LLM智能筛选按钮"""
        prompt = self._prompt_input.text().strip()
        if not prompt:
            QMessageBox.warning(self, "提示", f"请输入{self.reg_name}筛选需求描述")
            return
            
        if not self._available_tickers:
            QMessageBox.warning(self, "提示", f"请先选择{self.reg_name}基础股票池")
            return
            
        # 检查API Key
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")):
            QMessageBox.warning(
                self, "API Key 缺失",
                "请先在参数配置页面配置 Anthropic API Key 或 DeepSeek API Key"
            )
            return
            
        # 启动LLM生成线程
        self._set_generating(True)
        self._generate_status.setText(f"正在连接 LLM 生成{self.reg_name}股票清单...")
        self._generate_progress.setValue(0)
        
        self._llm_worker = LLMTicksGenerator(prompt, self._available_tickers, self.reg_code)
        self._llm_worker.progress.connect(self._on_generate_progress)
        self._llm_worker.result_ready.connect(self._on_generate_result)
        self._llm_worker.error_occured.connect(self._on_generate_error)
        self._llm_worker.finished.connect(lambda: self._set_generating(False))
        self._llm_worker.start()
        
    def _on_cancel_generate(self) -> None:
        """取消生成"""
        if self._llm_worker:
            self._llm_worker.cancel()
        self._set_generating(False)
        self._generate_status.setText("用户取消")
        
    def _on_generate_progress(self, msg: str) -> None:
        """更新生成进度"""
        self._generate_status.setText(msg)
        
    def _on_generate_result(self, tickers: List[str]) -> None:
        """生成结果处理"""
        if tickers:
            # 添加到编辑框
            self._add_tickers_to_edit(tickers)
            self._generate_status.setText(f"成功生成 {len(tickers)} 支{self.reg_name}股票")
            
            # 自动更新股票池名称
            current_name = self._pool_name_input.text().strip()
            if not current_name:
                prompt = self._prompt_input.text().strip()[:20]  # 截取前20个字符
                prompt_clean = re.sub(r'[^\w\s-]', '', prompt)  # 清理特殊字符
                self._pool_name_input.setText(f"{self.reg_code}_llm_{prompt_clean}")
                
        else:
            self._generate_status.setText(f"未生成有效的{self.reg_name}股票代码")
            
    def _on_generate_error(self, error: str) -> None:
        """生成错误处理"""
        QMessageBox.warning(self, f"{self.reg_name}生成失败", error)
        self._generate_status.setText(f"错误: {error}")
        
    def _set_generating(self, generating: bool) -> None:
        """设置生成状态"""
        self._prompt_input.setEnabled(not generating)
        self._generate_btn.setEnabled(not generating)
        self._cancel_btn.setVisible(generating)
        self._generate_progress.setVisible(generating)
        
    def _add_tickers_to_edit(self, new_tickers: List[str]) -> None:
        """添加股票代码到编辑框，自动去重"""
        # 获取现有文本
        current_text = self._ticker_edit.toPlainText().strip()
        current_lines = []
        if current_text:
            current_lines = [line.strip() for line in current_text.split('\n') if line.strip()]
            
        # 合并并去重
        all_tickers = set(current_lines)
        for ticker in new_tickers:
            if ticker:  # 确保非空
                all_tickers.add(ticker)
                
        # 限制数量
        all_tickers_list = list(all_tickers)
        if len(all_tickers_list) > 500:  # 限制总数量
            all_tickers_list = all_tickers_list[:500]
            QMessageBox.warning(self, "数量限制", f"{self.reg_name}股票池数量超过500支，已自动截断")
            
        # 排序
        all_tickers_list.sort()
        
        # 更新编辑框
        new_text = '\n'.join(all_tickers_list)
        self._ticker_edit.setPlainText(new_text)
        
        # 更新统计
        self._update_stats()
        
    def _on_add_clicked(self) -> None:
        """手动添加股票按钮"""
        from .dialogs.add_ticker_dialog import AddTickerDialog
        
        dialog = AddTickerDialog(self, self.reg_name, self.reg_code)
        if dialog.exec():
            tickers = dialog.get_tickers()
            if tickers:
                self._add_tickers_to_edit(tickers)
                
    def _on_clear_clicked(self) -> None:
        """清空编辑框"""
        reply = QMessageBox.question(
            self, f"确认清空{self.reg_name}股票池",
            f"确定要清空{self.reg_name}股票池吗？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._ticker_edit.clear()
            self._update_stats()
        
    def _on_format_clicked(self) -> None:
        """格式化股票代码"""
        text = self._ticker_edit.toPlainText().strip()
        if not text:
            return
            
        # 清理和格式化
        lines = text.split('\n')
        formatted = []
        invalid_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 格式化股票代码
            formatted_line = self._format_ticker_for_market(line)
            if formatted_line and self._validate_ticker_format(formatted_line):
                formatted.append(formatted_line)
            else:
                invalid_lines.append(line)
                
        # 去重
        formatted = list(dict.fromkeys(formatted))
        
        self._ticker_edit.setPlainText('\n'.join(formatted))
        
        # 显示验证结果
        if invalid_lines:
            QMessageBox.warning(
                self, f"{self.reg_name}股票代码验证",
                f"以下{len(invalid_lines)}行代码格式不正确，已被移除：\n{', '.join(invalid_lines[:10])}"
            )
        
        self._update_stats()
        
    def _format_ticker_for_market(self, ticker: str) -> Optional[str]:
        """根据市场类型格式化股票代码"""
        ticker_clean = ticker.strip().upper()
        
        if self.reg_code == "cn":
            # A股: 标准化为小写
            ticker_lower = ticker_clean.lower()
            if ticker_lower.startswith(("sh", "sz", "bj")):
                return ticker_lower
            elif ticker_clean.startswith(("600", "601", "603", "605", "688")):
                return f"sh{ticker_clean}"
            elif ticker_clean.startswith(("000", "001", "002", "003", "300")):
                return f"sz{ticker_clean}"
            elif ticker_clean.startswith(("430", "830", "870", "830")):
                return f"bj{ticker_clean}"
                
        elif self.reg_code == "hk":
            # 港股: 确保有 .HK 后缀
            ticker_clean = ticker_clean.replace(".HK", "")
            if ticker_clean.isdigit() and 4 <= len(ticker_clean) <= 5:
                return f"{ticker_clean}.HK"
                
        elif self.reg_code == "tw":
            # 台股: 确保有 .TW 后缀
            ticker_clean = ticker_clean.replace(".TW", "")
            if ticker_clean.isdigit() and len(ticker_clean) == 4:
                return f"{ticker_clean}.TW"
                
        elif self.reg_code == "jp":
            # 日股: 确保有 .T 后缀
            ticker_clean = ticker_clean.replace(".T", "")
            if ticker_clean.isdigit() and len(ticker_clean) == 4:
                return f"{ticker_clean}.T"
                
        elif self.reg_code == "kr":
            # 韩股: 确保有 .KS 或 .KQ 后缀
            if ticker_clean.endswith((".KS", ".KQ")):
                return ticker_clean
            elif ticker_clean.isdigit() and len(ticker_clean) == 6:
                # 默认使用 .KS 后缀
                return f"{ticker_clean}.KS"
                
        elif self.reg_code == "us":
            # 美股: 保持原样
            return ticker_clean
            
        elif self.reg_code == "bt":
            # Crypto: 保持原样
            return ticker_clean
            
        return None
    
    def _validate_ticker_format(self, ticker: str) -> bool:
        """验证股票代码格式"""
        if self.reg_code in MARKET_RULES:
            return bool(MARKET_RULES[self.reg_code].match(ticker))
        return True
        
    def _on_save_clicked(self) -> None:
        """保存股票池到文件"""
        # 获取股票代码列表
        text = self._ticker_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", f"{self.reg_name}股票池为空，无法保存")
            return
            
        tickers = [line.strip() for line in text.split('\n') if line.strip()]
        
        # 验证格式
        invalid = []
        for ticker in tickers:
            if not self._validate_ticker_format(ticker):
                invalid.append(ticker)
                
        if invalid:
            QMessageBox.warning(
                self, f"{self.reg_name}股票代码格式错误",
                f"以下{len(invalid)}个股票代码格式不正确：\n{', '.join(invalid[:10])}\n\n"
                f"请检查{self.reg_name}股票代码格式。"
            )
            return
            
        # 获取股票池名称
        pool_name = self._pool_name_input.text().strip()
        if not pool_name:
            QMessageBox.warning(self, "提示", f"请输入{self.reg_name}股票池名称")
            return
            
        # 清理文件名
        pool_name = re.sub(r'[<>:"/\\|?*]', '', pool_name)  # 移除非法字符
        pool_name = pool_name.replace(' ', '_')  # 空格替换为下划线
        
        # 确保以 .txt 结尾
        if not pool_name.lower().endswith('.txt'):
            pool_name += '.txt'
            
        # 保存到 custom_pools 目录
        from pathlib import Path
        save_dir = Path(f"custom_pools/{self.reg_code}")
        save_dir.mkdir(exist_ok=True, parents=True)
        
        save_path = save_dir / pool_name
        
        # 检查文件是否存在
        if save_path.exists():
            reply = QMessageBox.question(
                self, "文件已存在",
                f"文件 {pool_name} 已存在，是否覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
                
        try:
            # 写入文件
            with open(save_path, 'w', encoding='utf-8') as f:
                for ticker in tickers:
                    f.write(f"{ticker}\n")
                    
            QMessageBox.information(
                self, f"{self.reg_name}股票池保存成功", 
                f"已保存 {len(tickers)} 支{self.reg_name}股票到：\n"
                f"{save_path}\n\n"
                f"文件路径：{save_path.absolute()}"
            )
            
            logger.info(f"{self.reg_name}股票池保存成功: {pool_name}, 共 {len(tickers)} 支股票")
            
        except Exception as e:
            logger.error(f"保存{self.reg_name}股票池失败: {e}")
            QMessageBox.critical(
                self, f"{self.reg_name}股票池保存失败",
                f"保存{self.reg_name}股票池失败：\n{str(e)}"
            )
            
    def _update_stats(self) -> None:
        """更新统计信息"""
        text = self._ticker_edit.toPlainText().strip()
        if not text:
            count = 0
        else:
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            count = len(lines)
            
        self._stats_label.setText(f"{self.reg_name}股票数量：{count}")
        self._update_save_button_state()