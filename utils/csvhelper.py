import csv
import os
from pathlib import Path
from typing import List, Dict, Any

def _write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str] = None) -> None:
    """
    将数据写入 CSV 文件，如果目录或文件不存在则自动创建
    
    参数:
        path: 文件路径
        rows: 要写入的数据行列表
        fieldnames: CSV 文件的列名，如果不提供则从第一行数据中提取
    
    返回:
        None
    """
    # 确保路径是 Path 对象
    if not isinstance(path, Path):
        path = Path(path)
    
    # 如果目录不存在，则创建目录
    if not path.parent.exists():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            print(f"目录已创建: {path.parent}")
        except Exception as e:
            raise OSError(f"无法创建目录 {path.parent}: {e}")
    
    # 确定字段名
    if fieldnames is None:
        if rows:
            # 从第一行数据中提取字段名
            fieldnames = list(rows[0].keys())
        else:
            # 如果没有数据，使用默认字段名
            fieldnames = []
    
    # 写入 CSV 文件
    try:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            if rows:
                writer.writerows(rows)
        
        print(f"CSV 文件已成功写入: {path}")
        print(f"写入 {len(rows)} 行数据")
        
    except PermissionError:
        raise PermissionError(f"没有写入权限: {path}")
    except Exception as e:
        raise IOError(f"写入文件时出错 {path}: {e}")

def _read_csv(path: Path) -> List[Dict[str, Any]]:
    """
    从 CSV 文件读取数据
    
    参数:
        path: 文件路径
    
    返回:
        数据行列表
    """
    # 确保路径是 Path 对象
    if not isinstance(path, Path):
        path = Path(path)
    
    # 检查文件是否存在
    if not path.exists():
        print(f"文件不存在: {path}")
        return []
    
    # 读取 CSV 文件
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        print(f"从 CSV 文件读取 {len(rows)} 行数据: {path}")
        return rows
        
    except FileNotFoundError:
        print(f"文件未找到: {path}")
        return []
    except Exception as e:
        raise IOError(f"读取文件时出错 {path}: {e}")

def _append_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str] = None) -> None:
    """
    追加数据到 CSV 文件，如果文件不存在则创建
    
    参数:
        path: 文件路径
        rows: 要追加的数据行列表
        fieldnames: CSV 文件的列名，仅在创建新文件时使用
    
    返回:
        None
    """
    # 确保路径是 Path 对象
    if not isinstance(path, Path):
        path = Path(path)
    
    # 如果文件不存在，则创建新文件
    if not path.exists():
        _write_csv(path, rows, fieldnames)
        return
    
    # 确定字段名
    if fieldnames is None:
        if rows:
            fieldnames = list(rows[0].keys())
        else:
            fieldnames = []
    
    # 追加数据到 CSV 文件
    try:
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if rows:
                writer.writerows(rows)
        
        print(f"向 CSV 文件追加 {len(rows)} 行数据: {path}")
        
    except PermissionError:
        raise PermissionError(f"没有写入权限: {path}")
    except Exception as e:
        raise IOError(f"追加数据时出错 {path}: {e}")

def _check_csv_integrity(path: Path, fieldnames: List[str] = None) -> bool:
    """
    检查 CSV 文件的完整性
    
    参数:
        path: 文件路径
        fieldnames: 期望的字段名列表，用于验证
    
    返回:
        文件是否完整有效
    """
    if not isinstance(path, Path):
        path = Path(path)
    
    if not path.exists():
        print(f"文件不存在: {path}")
        return False
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            # 检查文件头
            file_fieldnames = reader.fieldnames
            if file_fieldnames is None:
                print(f"CSV 文件缺少表头: {path}")
                return False
            
            # 验证字段名
            if fieldnames is not None:
                if set(file_fieldnames) != set(fieldnames):
                    print(f"字段名不匹配。文件字段: {file_fieldnames}，期望字段: {fieldnames}")
                    return False
            
            # 读取并计算行数
            row_count = 0
            for row in reader:
                row_count += 1
            
            print(f"CSV 文件检查通过: {path}")
            print(f"字段: {file_fieldnames}")
            print(f"数据行数: {row_count}")
            return True
            
    except Exception as e:
        print(f"检查 CSV 文件时出错 {path}: {e}")
        return False

def test_csv_functions():
    """测试 CSV 文件功能"""
    import tempfile
    import shutil
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    print(f"测试目录: {temp_dir}")
    
    try:
        # 测试数据
        test_data = [
            {"id": 1, "name": "Alice", "age": 25, "city": "New York"},
            {"id": 2, "name": "Bob", "age": 30, "city": "London"},
            {"id": 3, "name": "Charlie", "age": 35, "city": "Tokyo"}
        ]
        
        fieldnames = ["id", "name", "age", "city"]
        
        # 测试 1: 写入不存在的目录
        print("\n=== 测试 1: 写入不存在的目录 ===")
        nested_path = Path(temp_dir) / "nested" / "deep" / "data.csv"
        _write_csv(nested_path, test_data, fieldnames)
        
        # 验证文件已创建
        assert nested_path.exists(), "文件应该被创建"
        print(f"✓ 文件已创建: {nested_path}")
        
        # 测试 2: 读取 CSV 文件
        print("\n=== 测试 2: 读取 CSV 文件 ===")
        read_data = _read_csv(nested_path)
        print(f"读取到 {len(read_data)} 行数据")
        
        # 验证数据完整性
        assert len(read_data) == len(test_data), "读取的数据行数应该匹配"
        for i, row in enumerate(read_data):
            assert int(row["id"]) == test_data[i]["id"], f"第 {i} 行 id 不匹配"
        
        # 测试 3: 追加数据
        print("\n=== 测试 3: 追加数据到 CSV 文件 ===")
        new_data = [
            {"id": 4, "name": "David", "age": 28, "city": "Paris"},
            {"id": 5, "name": "Eve", "age": 32, "city": "Berlin"}
        ]
        _append_csv(nested_path, new_data)
        
        # 验证追加后的数据
        updated_data = _read_csv(nested_path)
        assert len(updated_data) == len(test_data) + len(new_data), "追加后行数应该增加"
        print(f"✓ 追加后总行数: {len(updated_data)}")
        
        # 测试 4: 检查文件完整性
        print("\n=== 测试 4: 检查文件完整性 ===")
        is_valid = _check_csv_integrity(nested_path, fieldnames)
        assert is_valid, "文件完整性检查应该通过"
        print("✓ 文件完整性检查通过")
        
        # 测试 5: 写入空数据
        print("\n=== 测试 5: 写入空数据 ===")
        empty_path = Path(temp_dir) / "empty.csv"
        _write_csv(empty_path, [], ["col1", "col2"])
        
        # 验证空文件
        assert empty_path.exists(), "空文件应该被创建"
        empty_data = _read_csv(empty_path)
        assert len(empty_data) == 0, "空文件应该没有数据行"
        print("✓ 空文件创建成功")
        
        # 测试 6: 权限错误测试
        print("\n=== 测试 6: 权限错误测试 ===")
        if os.name != 'nt':  # 在非 Windows 系统上测试
            read_only_path = Path(temp_dir) / "readonly.csv"
            _write_csv(read_only_path, [{"test": "data"}])
            
            # 设置只读权限
            os.chmod(read_only_path, 0o444)
            
            try:
                _write_csv(read_only_path, [{"test": "new_data"}])
                print("✗ 应该抛出权限错误")
            except PermissionError as e:
                print(f"✓ 正确捕获权限错误: {e}")
        
        # 测试 7: 自动从数据推断字段名
        print("\n=== 测试 7: 自动推断字段名 ===")
        auto_path = Path(temp_dir) / "auto_fields.csv"
        _write_csv(auto_path, test_data)  # 不提供 fieldnames
        
        auto_data = _read_csv(auto_path)
        assert len(auto_data) == len(test_data), "自动推断字段名应该工作正常"
        print("✓ 自动推断字段名成功")
        
        print(f"\n✅ 所有测试通过!")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # 清理临时目录
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"\n测试目录已清理: {temp_dir}")

if __name__ == "__main__":
    test_csv_functions()
