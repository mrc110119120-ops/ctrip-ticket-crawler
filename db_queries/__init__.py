"""db_queries - 数据库查询封装

把高频分析查询封装成 Python 函数，避免手写 SQL：
- get_price_history        某航班在某 flight_date 的全部历史价格（趋势分析）
- get_cheapest             某航线日期区间内最便宜的航班（支持出发时段筛选）
- get_date_price_summary   航线日期区间内每天最低价（日期-价格关系）
- get_hour_price_summary   航线出发时段与价格的关系
- rows_to_dataframe        结果转 pandas DataFrame（未安装 pandas 时返回 list[dict]）
- to_csv                   结果导出 CSV
"""
