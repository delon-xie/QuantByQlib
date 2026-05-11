# QuantByQlib RD-Agent 因子发现镜像
# 构建：bash scripts/build_docker.sh
# 标签：local_qlib:latest

FROM python:3.10-slim

# 设置环境变量 - 指定时区和编码
ENV TZ=Asia/Shanghai
ENV LANG=C.UTF-8
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ git curl ca-certificates tzdata \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && ln -fs /usr/share/zoneinfo/${TZ} /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata

WORKDIR /workspace
RUN mkdir -p /workspace/mlruns

# 分步安装，方便调试缓存层
# 升级 pip 和相关工具
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# 基础科学计算库
RUN pip install --no-cache-dir \
    numpy==1.26.4 \
    pandas==2.2.3 \
    scipy==1.13.1 \
    pyarrow==16.1.0 \
    requests==2.31.0 \
    python-dateutil==2.8.2

# 机器学习相关
RUN pip install --no-cache-dir \
    scikit-learn==1.4.2 \
    xgboost==2.0.3 \
    lightgbm==4.3.0 \
    catboost==1.2.5

# AI 模型客户端（包含 DeepSeek）
RUN pip install --no-cache-dir \
    anthropic==0.97.0 \
    openai==2.32.0 \
    deepseek==1.0.0  # DeepSeek 官方包

# 或使用 OpenAI 兼容接口（如果 DeepSeek 不支持官方包）
# RUN pip install openai==1.30.1  # OpenAI 库也支持 DeepSeek 的兼容接口

# 因子分析相关
RUN pip install --no-cache-dir \
    statsmodels==0.14.2 \
    tqdm==4.66.4 \
    loguru==0.7.2 \
    prettytable==3.10.0

# 安装 Qlib
RUN git clone --depth=1 https://github.com/microsoft/qlib.git /tmp/qlib && \
    cd /tmp/qlib && \
    # 先安装基础依赖
    pip install --no-cache-dir numpy pandas && \
    # 使用开发模式安装
    pip install --no-cache-dir -e . && \
    # 安装可选依赖
    pip install --no-cache-dir ".[all]" && \
    # 清理
    rm -rf /tmp/qlib 
    # && \
    # 验证安装
    # python -c "import qlib; print(f'Qlib version: {qlib.__version__}')"

# 可选：安装 A 股/港股数据源支持
RUN pip install --no-cache-dir \
    curl_cffi==0.15.0 \
    akshare==1.18.57 \
    tushare==1.4.29 \
    yfinance==1.3.0

# 创建工作目录
RUN mkdir -p /root/.qlib/qlib_data /workspace/logs

# 复制启动脚本，确保以下步骤不会调用缓存，必须强制执行
RUN echo "rebuild-$(date +%s)" >> /workspace/rebuild.txt
COPY scripts/run_factor_discovery.py /workspace/run_factor_discovery.py
COPY core/*.py /workspace/core/
RUN chmod +x /workspace/run_factor_discovery.py

# 健康检查
HEALTHCHECK --interval=60s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import qlib; print('Qlib imported successfully')" || exit 1

VOLUME ["/workspace", "/root/.qlib/qlib_data"]

# CMD ["python", "/workspace/run_factor_discovery.py --provider deepseek --reg cn"] 带参数 provider

#ENTRYPOINT ["python", "/workspace/run_factor_discovery.py"]
#CMD ["--provider", "deepseek", "--reg", "cn"]



# 可选：Jupyter 端口
EXPOSE 8888