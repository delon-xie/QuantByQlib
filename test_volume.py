"""测试 qlib 成交量数据"""
import sys
sys.path.insert(0, '.')

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from qlib.data import D
from qlib.config import REG_CN
from datetime import date, timedelta

# 设置区域
os.environ["REGION"] = "cn"

# 初始化 qlib
import qlib
qlib.init(provider_uri="/Users/admin/.qlib/qlib_data/cn_data", region=REG_CN)

def test_qlib_volume():
    print("Testing qlib volume data...")
    
    # 尝试获取数据
    ticker = 'SH600208'
    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=30)).isoformat()
    
    try:
        df = D.features([ticker], ['$open', '$high', '$low', '$close', '$volume'], 
                       start_time=start_date, end_time=end_date)
        
        print(f"\n=== {ticker} ===")
        print(f"Columns: {df.columns.tolist()}")
        print(f"Shape: {df.shape}")
        
        if not df.empty:
            print(f"\nFirst 5 rows:")
            print(df.head())
            
            if '$volume' in df.columns:
                vol_min = df['$volume'].min()
                vol_max = df['$volume'].max()
                vol_mean = df['$volume'].mean()
                
                print(f"\nVolume stats:")
                print(f"  Min: {vol_min}")
                print(f"  Max: {vol_max}")
                print(f"  Mean: {vol_mean:.2f}")
                print(f"  First 5 values: {df['$volume'].head().tolist()}")
                
                if vol_max == 0:
                    print("\n⚠️ WARNING: All volume values are 0!")
                else:
                    print("\n✅ Volume data is OK")
            else:
                print("\n❌ Volume column NOT found!")
        else:
            print("\n❌ Dataframe is empty!")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_qlib_volume()
