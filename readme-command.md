``` bash
# 构建虚拟环境 3.10.20
~/.pyenv/versions/3.10.20/bin/python -m venv .venv
# 激活虚拟环境
source .venv/bin/activate
# 验证版本
python --version

python -m pip install --upgrade pip
pip install -r requirements.txt

# 运行 QuantByQLib
python main.py 

# 安装依赖
# 基本安装
pip install -r requirements.txt

# 如果需要升级 pip
python -m pip install --upgrade pip
pip install -r requirements.txt

# 创建镜像
chmod +x scripts/build_docker_deepseek.sh
./scripts/build_docker_deepseek.sh

chmod +x scripts/run_docker.sh
./scripts/run_docker.sh

#使用挂载保持 py 是最新状态
#容器缺 run_factor_discovery.py
#cp /Users/admin/codes/trading/QuantByQlib/scripts/run_factor_discovery.py discovered_factors.json

# CN 数据源
# https://github.com/chenditc/investment_data/releases/latest/download/qlib_bin.tar.gz

# CN 数据源
# https://api.github.com/repos/chenditc/investment_data/releases/latest

# 安装机器学习库
brew install libomp
pip install catboost xgboost

# 安装
brew install duckdb
# 连接数据库
duckdb ~/.quantbyqlib/portfolio.duckdb
.tables
.schema positions
SELECT COUNT(*) FROM positions;
select * from goals;
select * from corporate_actions;
SELECT * FROM transactions LIMIT 5;
.exit

# 安装测试依赖
pip install pytest pytest-cov

# 运行所有测试
pytest dbtest.py  -v

# 运行特定测试类
pytest dbtest.py::TestPortfolioDatabase -v

# 生成覆盖率报告
pytest dbtest.py --cov=portfolio.db --cov-report=html
```