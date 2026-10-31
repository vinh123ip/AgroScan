"""Service layer for AgroScan.

During the UI-shell phase every service here is a mock that keeps data in
memory. Real implementations (PostgreSQL, YOLO, Qwen-VL, SMB storage) will
replace them behind the same method names.
"""
