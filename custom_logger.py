import logging
import sys
from datetime import datetime


class CustomLogger(logging.Logger):
    def __init__(self, name):
        super().__init__(name)
        self.setLevel(logging.INFO)
        self.addHandler(logging.StreamHandler(sys.stdout))
        file_handler = logging.FileHandler(f"encoding_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        self.addHandler(file_handler)

    def info(self, msg, *args, **kwargs):
        super().info(msg, *args, **kwargs)
        self.handlers[-1].flush()

    def warning(self, msg, *args, **kwargs):
        super().warning(msg, *args, **kwargs)
        self.handlers[-1].flush()

    def error(self, msg, *args, **kwargs):
        super().error(msg, *args, **kwargs)
        self.handlers[-1].flush()
