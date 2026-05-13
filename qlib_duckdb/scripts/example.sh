# 1. 检查系统状态
python -m qlib_duckdb.scripts.admin_cli check-status --reg cn

# 2. 创建所有表
python -m qlib_duckdb.scripts.admin_cli create-tables --reg cn --table-type all

# 3. 创建指定频率的特征表
python -m qlib_duckdb.scripts.admin_cli create-tables --reg cn --table-type feature --freq day 5m 1h

# 4. 列出所有表
python -m qlib_duckdb.scripts.admin_cli list-tables --reg cn

# 5. 获取表详细信息
python -m qlib_duckdb.scripts.admin_cli table-info --reg cn --table-name feature_day --sample

# 6. 执行 SQL 查询
python -m qlib_duckdb.scripts.admin_cli execute-sql --reg cn --sql "SELECT COUNT(*) FROM feature_day"

# 7. 清除缓存
python -m qlib_duckdb.scripts.admin_cli clear-cache --reg cn

# 8. 优化数据库
python -m qlib_duckdb.scripts.admin_cli vacuum-db --reg cn

# 9. 导出表结构
python -m qlib_duckdb.scripts.admin_cli export-schema --reg cn --output schema.json

# 1. 从 CSV 文件更新数据
python -m qlib_duckdb.scripts.update_cli from-csv \
  --reg cn \
  --freq day \
  --csv-path data.csv \
  --symbol-col symbol \
  --datetime-col datetime

# 2. 更新单个标的
python -m qlib_duckdb.scripts.update_cli single-symbol \
  --reg cn \
  --symbol SH600000 \
  --freq day \
  --data-file sh600000.csv

# 3. 从目录批量更新
python -m qlib_duckdb.scripts.update_cli from-dir \
  --reg cn \
  --freq day \
  --directory ./daily_data/ \
  --pattern "*.csv" \
  --output update_results.json

# 4. 检查缺失数据
python -m qlib_duckdb.scripts.update_cli check-missing \
  --reg cn \
  --symbol SH600000 \
  --freq day \
  --start-time 2023-01-01 \
  --end-time 2023-12-31

# 5. 从 API 同步数据
python -m qlib_duckdb.scripts.update_cli from-api \
  --reg cn \
  --symbol SH600000 \
  --freq day \
  --days 30 \
  --data-source akshare

# 6. 自动确认模式 (跳过所有确认提示)
python -m qlib_duckdb.scripts.update_cli from-csv \
  --reg cn \
  --freq day \
  --csv-path data.csv \
  --yes