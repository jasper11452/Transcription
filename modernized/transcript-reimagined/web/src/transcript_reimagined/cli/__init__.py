"""`transcript_reimagined.cli` —— 命令行入口。

保持空包：不要在 `__init__` 里 re-export `main`。否则
`python -m transcript_reimagined.cli.main` 会先导入包、再由 runpy 执行同一个
子模块，产生 "found in sys.modules ... may result in unpredictable behaviour"。
控制台脚本直接指向 `transcript_reimagined.cli.main:main`。
"""
