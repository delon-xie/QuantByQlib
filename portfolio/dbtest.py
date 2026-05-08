"""
PortfolioDatabase DuckDB 接口测试
"""
import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta

# 导入被测试的模块
from portfolio.db import PortfolioDatabase, get_db
from core.exceptions import InsufficientSharesError


@pytest.fixture
def temp_db_path():
    """创建临时数据库路径"""
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_portfolio.duckdb"
    yield db_path
    # 清理
    shutil.rmtree(temp_dir)


@pytest.fixture
def db(temp_db_path):
    """创建测试数据库实例"""
    return PortfolioDatabase(db_path=temp_db_path)


class TestPortfolioDatabase:
    """PortfolioDatabase 基础功能测试"""

    def test_database_initialization(self, temp_db_path):
        """测试数据库初始化和表结构创建"""
        db = PortfolioDatabase(db_path=temp_db_path)
        db._init_schema()
        
        # 验证表是否存在
        with db._conn() as conn:
            tables = conn.execute("SHOW TABLES").fetchall()
            table_names = [t[0] for t in tables]
            
            assert "positions" in table_names
            assert "transactions" in table_names
            assert "corporate_actions" in table_names
            assert "goals" in table_names

    def test_buy_new_position(self, db):
        """测试买入新股票"""
        db.buy("AAPL", 10, 150.0, commission=1.0)
        
        positions = db.get_all_positions()
        assert len(positions) == 1
        
        position = positions[0]
        assert position["symbol"] == "AAPL"
        assert position["shares"] == 10
        assert abs(position["avg_cost"] - ((10 * 150.0 + 1.0) / 10)) < 0.01

    def test_buy_existing_position(self, db):
        """测试买入已持有的股票（加权平均成本）"""
        db.buy("AAPL", 10, 150.0, commission=1.0)
        db.buy("AAPL", 5, 160.0, commission=0.5)
        
        position = db.get_position("AAPL")
        expected_avg_cost = (10 * 150.0 + 1.0 + 5 * 160.0 + 0.5) / 15
        
        assert position["shares"] == 15
        assert abs(position["avg_cost"] - expected_avg_cost) < 0.01

    def test_sell_success(self, db):
        """测试成功卖出"""
        db.buy("AAPL", 10, 150.0)
        realized_pnl = db.sell("AAPL", 5, 160.0, commission=1.0)
        
        position = db.get_position("AAPL")
        assert position["shares"] == 5
        assert realized_pnl > 0  # 应该盈利

    def test_sell_insufficient_shares(self, db):
        """测试卖出数量超过持仓"""
        db.buy("AAPL", 10, 150.0)
        
        with pytest.raises(InsufficientSharesError):
            db.sell("AAPL", 15, 160.0)

    def test_sell_all_shares(self, db):
        """测试卖出全部持仓"""
        db.buy("AAPL", 10, 150.0)
        db.sell("AAPL", 10, 160.0)
        
        positions = db.get_all_positions()
        assert len(positions) == 0

    def test_get_all_positions(self, db):
        """测试获取所有持仓"""
        db.buy("AAPL", 10, 150.0)
        db.buy("GOOGL", 5, 2800.0)
        
        positions = db.get_all_positions()
        symbols = [p["symbol"] for p in positions]
        
        assert "AAPL" in symbols
        assert "GOOGL" in symbols
        assert len(positions) == 2

    def test_get_position(self, db):
        """测试获取单个持仓"""
        db.buy("AAPL", 10, 150.0)
        
        position = db.get_position("AAPL")
        assert position is not None
        assert position["symbol"] == "AAPL"
        
        # 测试不存在的股票
        position = db.get_position("NONEXISTENT")
        assert position == []

    def test_update_sector(self, db):
        """测试更新行业分类"""
        db.buy("AAPL", 10, 150.0)
        db.update_sector("AAPL", "Technology")
        
        position = db.get_position("AAPL")
        assert position["sector"] == "Technology"

    def test_delete_position(self, db):
        """测试删除持仓"""
        db.buy("AAPL", 10, 150.0)
        db.delete_position("AAPL")
        
        positions = db.get_all_positions()
        assert len(positions) == 0

    def test_delete_transaction(self, db):
        """测试删除交易记录"""
        db.buy("AAPL", 10, 150.0)
        db.buy("GOOGL", 5, 2800.0)
        
        # 获取交易记录
        transactions = db.get_transactions()
        assert len(transactions) == 2
        
        # 删除第一条
        db.delete_transaction(transactions[0]["id"])
        
        transactions = db.get_transactions()
        assert len(transactions) == 1

    def test_get_transactions(self, db):
        """测试获取交易记录"""
        db.buy("AAPL", 10, 150.0)
        db.buy("AAPL", 5, 160.0)
        db.sell("AAPL", 3, 155.0)
        
        transactions = db.get_transactions()
        assert len(transactions) == 3
        
        # 按股票筛选
        aapl_transactions = db.get_transactions(symbol="AAPL")
        assert len(aapl_transactions) == 3
        
        googl_transactions = db.get_transactions(symbol="GOOGL")
        assert len(googl_transactions) == 0

    def test_get_realized_pnl(self, db):
        """测试计算已实现盈亏"""
        db.buy("AAPL", 10, 150.0, commission=1.0)
        db.sell("AAPL", 5, 160.0, commission=0.5)
        
        realized_pnl = db.get_realized_pnl()
        assert realized_pnl > 0  # 应该盈利
        
        # 按股票计算
        aapl_pnl = db.get_realized_pnl(symbol="AAPL")
        assert aapl_pnl > 0

    def test_create_and_get_goals(self, db):
        """测试创建和获取盈利目标"""
        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        
        goal_id = db.create_goal(
            name="Test Goal",
            period_type="MONTHLY",
            target_return_pct=10.0,
            start_date=start_date,
            end_date=end_date,
            initial_capital=10000.0
        )
        
        assert goal_id > 0
        
        active_goals = db.get_active_goals()
        assert len(active_goals) == 1
        assert active_goals[0]["name"] == "Test Goal"
        
        all_goals = db.get_all_goals()
        assert len(all_goals) == 1

    def test_update_goal_status(self, db):
        """测试更新目标状态"""
        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        
        goal_id = db.create_goal(
            name="Test Goal",
            period_type="MONTHLY",
            target_return_pct=10.0,
            start_date=start_date,
            end_date=end_date,
            initial_capital=10000.0
        )
        
        db.update_goal_status(goal_id, "COMPLETED")
        
        active_goals = db.get_active_goals()
        assert len(active_goals) == 0
        
        all_goals = db.get_all_goals()
        completed_goal = [g for g in all_goals if g["id"] == goal_id][0]
        assert completed_goal["status"] == "COMPLETED"

    def test_get_portfolio_summary_empty(self, db):
        """测试空持仓的汇总"""
        summary = db.get_portfolio_summary()
        
        assert summary["total_invested"] == 0.0
        assert summary["total_market_value"] == 0.0
        assert summary["position_count"] == 0

    def test_get_portfolio_summary_with_positions(self, db):
        """测试有持仓的汇总"""
        db.buy("AAPL", 10, 150.0)
        db.buy("GOOGL", 5, 2800.0)
        
        # 不传入当前价格
        summary = db.get_portfolio_summary()
        assert summary["position_count"] == 2
        assert summary["total_invested"] > 0
        
        # 传入当前价格
        current_prices = {"AAPL": 160.0, "GOOGL": 2900.0}
        summary = db.get_portfolio_summary(current_prices=current_prices)
        assert summary["total_market_value"] > summary["total_invested"]

    def test_edge_cases(self, db):
        """测试边界情况"""
        # 测试零股买入
        db.buy("AAPL", 0.5, 150.0)
        position = db.get_position("AAPL")
        assert position["shares"] == 0.5
        
        # 测试非常小的金额
        db.buy("PENNY", 10000, 0.01)
        position = db.get_position("PENNY")
        assert position["avg_cost"] == 0.01
        
        # 测试卖出所有零股
        db.sell("PENNY", 10000, 0.02)
        position = db.get_position("PENNY")
        assert position == []

    def test_transaction_records_accuracy(self, db):
        """测试交易记录的准确性"""
        db.buy("AAPL", 10, 150.0, commission=1.0, notes="Test buy")
        db.sell("AAPL", 5, 160.0, commission=0.5, notes="Test sell")
        
        transactions = db.get_transactions()
        
        buy_transaction = [t for t in transactions if t["trans_type"] == "BUY"][0]
        assert buy_transaction["shares"] == 10
        assert buy_transaction["price"] == 150.0
        assert buy_transaction["commission"] == 1.0
        assert buy_transaction["notes"] == "Test buy"
        
        sell_transaction = [t for t in transactions if t["trans_type"] == "SELL"][0]
        assert sell_transaction["shares"] == 5
        assert sell_transaction["price"] == 160.0
        assert sell_transaction["commission"] == 0.5
        assert sell_transaction["notes"] == "Test sell"


class TestDatabaseSingleton:
    """测试数据库单例模式"""
    
    def test_get_db_singleton(self, temp_db_path):
        """测试get_db返回单例"""
        # 修改默认路径
        from portfolio import db as db_module
        db_module.DEFAULT_DB_PATH = temp_db_path
        
        db1 = get_db()
        db2 = get_db()
        
        assert db1 is db2
        assert isinstance(db1, PortfolioDatabase)


class TestConcurrentAccess:
    """测试并发访问（模拟多进程场景）"""
    
    def test_multiple_connections(self, temp_db_path):
        """测试多个连接独立工作"""
        db1 = PortfolioDatabase(db_path=temp_db_path)
        db2 = PortfolioDatabase(db_path=temp_db_path)
        
        # 两个实例操作同一个数据库
        db1.buy("AAPL", 10, 150.0)
        db2.buy("GOOGL", 5, 2800.0)
        
        # 验证两个实例都能看到对方的数据
        positions1 = db1.get_all_positions()
        positions2 = db2.get_all_positions()
        
        assert len(positions1) == 2
        assert len(positions2) == 2


# 运行测试的辅助函数
if __name__ == "__main__":
    pytest.main([__file__, "-v"])